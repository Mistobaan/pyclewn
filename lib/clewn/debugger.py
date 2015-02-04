# vi:set ts=8 sts=4 sw=4 et tw=72:
"""
This module provides the basic infrastructure for using Vim as a
front-end to a debugger.

The basic idea behind this infrastructure is to subclass the 'Debugger'
abstract class, list all the debugger commands and implement the
processing of these commands in 'cmd_<command_name>' methods in the
subclass. When the method is not implemented, the processing of the
command is dispatched to the 'default_cmd_processing' method. These
methods may call the 'Debugger' API methods to control Vim. For example,
'add_bp' may be called to set a breakpoint in a buffer in Vim, or
'console_print' may be called to write the output of a command in the
Vim debugger console.

The 'Simple' class in simple.py provides a simple example of a fake
debugger front-end.
"""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from io import open

import sys
import os
import re
import asyncio
import time
import logging
import string
import copy
import subprocess
from abc import ABCMeta, abstractmethod

from . import __version__, ClewnError, misc, netbeans

BCKGROUND_JOB_DELAY = .200

RE_KEY =    \
    r'^\s*(?P<key>'                                                     \
        r'(?# Fn, C-Fn, S-Fn, M-Fn, C-S-Fn, C-M-Fn, S-M-Fn,C-S-M-Fn:)'  \
        r'(?:[Cc]-)?(?:[Ss]-)?(?:[Mm]-)?[Ff]\d{1,2}'                    \
        r'(?# C-A, C-S-A, C-S-M-A, C-M-A:)'                             \
        r'|(?:[Cc]-)(?:[Ss]-)?(?:[Mm]-)?[A-Za-z]'                       \
        r'(?# S-A, S-M-A:)'                                             \
        r'|(?:[Ss]-)(?:[Mm]-)?[A-Za-z]'                                 \
        r'(?#M-A:)'                                                     \
        r'|(?:[Mm]-)[A-Za-z]'                                           \
    r')'        \
    r'\s*:\s*(?P<value>[^#]*)'                                          \
    r'# RE: key:value line in .pyclewn_keys'
RE_COMMENT = r'^\s*([#].*|\s*)$'                                    \
             r'# RE: a comment line'
RE_FILENAMELNUM = r'^(?P<name>\S+):(?P<lnum>\d+)$'                  \
                  r'# RE: pathname:lnum'

# compile regexps
re_key = re.compile(RE_KEY, re.VERBOSE)
re_comment = re.compile(RE_COMMENT, re.VERBOSE)
re_filenamelnum = re.compile(RE_FILENAMELNUM, re.VERBOSE)

VIM_SCRIPT_FIXED = r"""
" Set 'cpo' option to its vim default value.
let s:cpo_save=&cpo
set cpo&vim

function <SID>goto_line()
    let l:line = getline(".")
    let l:regexp = '^\(.*\) at \(\d\+\):\(.\+\)$'
    let l:lnum = substitute(l:line, l:regexp , '\2', "")
    if l:line != l:lnum
        let l:fname = substitute(l:line, l:regexp , '\3', "")
        if ! filereadable(l:fname)
            echohl ErrorMsg
            echo l:fname . " does not exist."
            echohl None
            return
        endif

        if winnr() ==  bufwinnr("(clewn)_breakpoints")
            let l:nr = bufwinnr(l:fname)
            if l:nr == -1
                exe &previewheight . "split"
                wincmd w
                exe "edit " . l:fname
            else
                exe l:nr . "wincmd w"
            endif
            call cursor(l:lnum, 0)
        endif

    endif
endfunction

function <SID>goto_frame()
    let l:line = getline(".")
    let l:regexp = '^\([ *] \)#\(\d\+\).*$'
    let l:num = substitute(l:line, l:regexp , '\2', "")
    if l:line != l:num
        exe "Cframe " . l:num
    endif
endfunction

function <SID>goto_thread()
    let l:line = getline(".")
    let l:regexp = '^\([ *] \)\(\d\+\).*$'
    let l:thread = substitute(l:line, l:regexp , '\2', "")
    if l:line != l:thread
        exe "Cthread " . l:thread
    endif
endfunction

" Split a window and display a buffer with previewheight.
function s:winsplit(bufname, lnum, location)
    if a:location == "none"
        return
    endif

    " The window does not exist.
    let l:nr = bufwinnr(a:bufname)
    if l:nr == -1
        call s:split(a:bufname, a:lnum, a:location)
    elseif a:lnum != ""
        let l:prevbuf_winnr = bufwinnr(bufname("%"))
        exe l:nr . "wincmd w"
        call cursor(a:lnum, 0)
        exe l:prevbuf_winnr . "wincmd w"
    endif

    " Split the window (when the only window)
    " this is required to prevent Vim display toggling between
    " clewn console and the last buffer where the cursor was
    " positionned (clewn does not know that this buffer is not
    " anymore displayed).
    if winnr("$") == 1
        call s:split("", "", a:location)
    endif
endfunction

" Split a window and return to the initial window,
" if 'location' is not ''
"   'location' may be: '', 'top', 'bottom', 'left' or 'right'.
function s:split(bufname, lnum, location)
    let nr = 1
    let split = "split"
    let spr = &splitright
    let sb = &splitbelow
    set nosplitright
    set nosplitbelow
    let prevbuf_winnr = bufwinnr(bufname("%"))
    if winnr("$") == 1 && (a:location == "right" || a:location == "left")
	let split = "vsplit"
	if a:location == "right"
	    set splitright
        else
            let prevbuf_winnr = 2
	endif
    else
	if a:location == "bottom"
 	    let nr = winnr("$")
	    set splitbelow
        else
            let prevbuf_winnr = prevbuf_winnr + 1
	endif
	if a:location != ""
	    exe nr . "wincmd w"
	endif
    endif
    let nr = bufnr(a:bufname)
    if nr != -1
        exe &previewheight . split
        exe nr . "buffer"
    else
        exe &previewheight . split . " " . a:bufname
    endif
    if a:lnum != ""
        call cursor(a:lnum, 0)
    endif
    let &splitright = spr
    let &splitbelow = sb
    exe prevbuf_winnr . "wincmd w"
endfunc

let s:bufList = {}
let s:bufLen = 0

" Build the list as an hash of active buffers
" This is the list of buffers loaded on startup,
" that must be advertized to pyclewn
function s:BuildList()
    let wincount = winnr("$")
    let index = 1
    while index <= wincount
        let s:bufList[expand("#". winbufnr(index) . ":p")] = 1
        let index = index + 1
    endwhile
    let s:bufLen = len(s:bufList)
endfunction

" Return true when the buffer is in the list, and remove it
function s:InBufferList(pathname)
    if s:bufLen && has_key(s:bufList, a:pathname)
        unlet s:bufList[a:pathname]
        let s:bufLen = len(s:bufList)
        return 1
    endif
    return 0
endfunction

" Function that can be used for testing
" Remove 's:' to expand function scope to runtime
function! s:PrintBufferList()
    for key in keys(s:bufList)
       echo key
    endfor
endfunction

" Popup gdb console on pyclewn mapped keys.
function s:mapkeys()
    call s:nbcommand("mapkeys")
endfunction

"""

AUTOCOMMANDS = """
augroup clewn
    autocmd!
    autocmd BufWinEnter (clewn)_* silent! setlocal bufhidden=hide"""    \
"""                                     | setlocal buftype=nofile"""    \
"""                                     | setlocal noswapfile"""        \
"""                                     | setlocal fileformat=unix"""   \
"""                                     | setlocal expandtab"""         \
"""                                     | setlocal nowrap"""            \
"""
    ${bufferlist_autocmd}
    autocmd BufWinEnter (clewn)_console silent! nbkey ClewnBuffer.Console.open
    autocmd BufWinLeave (clewn)_console silent! nbkey ClewnBuffer.Console.close
    autocmd BufWinEnter (clewn)_variables silent! setlocal syntax=clewn_variables
    autocmd BufEnter (clewn)_variables nnoremap <buffer> <silent> <CR> :exe "Cfoldvar " . line(".")<CR>
    autocmd BufEnter (clewn)_variables nnoremap <buffer> <silent> <2-Leftmouse> :exe "Cfoldvar " . line(".")<CR>
    autocmd BufEnter (clewn)_breakpoints nnoremap <buffer> <silent> <CR> :call <SID>goto_line()<CR>
    autocmd BufEnter (clewn)_breakpoints nnoremap <buffer> <silent> <2-Leftmouse> :call <SID>goto_line()<CR>
    autocmd BufEnter (clewn)_backtrace nnoremap <buffer> <silent> <CR> :call <SID>goto_frame()<CR>
    autocmd BufEnter (clewn)_backtrace nnoremap <buffer> <silent> <2-Leftmouse> :call <SID>goto_frame()<CR>
    autocmd BufEnter (clewn)_threads nnoremap <buffer> <silent> <CR> :call <SID>goto_thread()<CR>
    autocmd BufEnter (clewn)_threads nnoremap <buffer> <silent> <2-Leftmouse> :call <SID>goto_thread()<CR>
    ${list_buffers_autocmd}
augroup END

"""

LIST_BUFFERS_AUTOCMD = """
    autocmd BufWinEnter ${bufname} silent! nbkey ClewnBuffer.${name}.open
    autocmd BufWinLeave ${bufname} silent! nbkey ClewnBuffer.${name}.close
"""

BUFFERLIST_AUTOCMD = """
    autocmd VimEnter * silent! call s:BuildList()
    autocmd BufWinEnter * silent! call s:InBufferList(expand("<afile>:p"))
"""

FUNCTION_NBCOMMAND = """
" Run the nbkey netbeans Vim command.
function s:nbcommand(...)
    if !has("netbeans_enabled")
        echohl ErrorMsg
        echo "Error: netbeans is not connected."
        echohl None
        return
    endif

    " Allow '' as first arg: the 'C' command followed by a mandatory parameter
    if a:0 != 0
        if a:1 != "" || (a:0 > 1 && a:2 != "")
            if bufname("%") == ""
                edit ${console}
            else
                call s:winsplit("${console}", "", "${location}")
            endif
            ${split_vars_buf}
            let cmd = "nbkey " . join(a:000, ' ')
            exe cmd
            ${split_bt_buf}
        endif
    endif
endfunction

"""

FUNCTION_NBCOMMAND_RESTRICT = """
" Run the nbkey netbeans Vim command.
function s:nbcommand(...)
    if bufname("%") == ""
        echohl ErrorMsg
        echo "Cannot run a pyclewn command on the '[No Name]' buffer."
        echo "Please edit a file first."
        echohl None
        return
    endif

    " Allow '' as first arg: the 'C' command followed by a mandatory parameter
    if a:0 != 0
        if a:1 != "" || (a:0 > 1 && a:2 != "")
            " edit the buffer that was loaded on startup and call input() to
            " give a chance for vim72 to process the putBufferNumber netbeans
            " message in the idle loop before the call to nbkey
            let l:currentfile = expand("%:p")
            if s:InBufferList(l:currentfile)
                exe "edit " . l:currentfile
                echohl WarningMsg
                echo "Files loaded on Vim startup must be registered with pyclewn."
                echo "Registering " . l:currentfile . " with pyclewn."
                call inputsave()
                call input("Press the <Enter> key to continue.")
                call inputrestore()
                echohl None
            endif
            call s:winsplit("${console}", "", "${location}")
            ${split_vars_buf}
            let cmd = "nbkey " . join(a:000, ' ')
            exe cmd
            ${split_bt_buf}
        endif
    endif
endfunction

"""

SPLIT_VARS_BUF = """
            if a:1 == "dbgvar"
                call s:winsplit("(clewn)_variables", "", "")
            endif
"""

SPLIT_BT_BUF = """
            " <CR> in the backtrace list buffer may cause the backtrace
            " window to be replaced by another window. So wait for this
            " to happen and split this window in this case.
            if a:1 == "frame" && bufwinnr("(clewn)_backtrace") != -1
                sleep 500m
                call s:winsplit("(clewn)_backtrace", "", "")
            endif
"""

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('dbg')

def name_lnum(name_lnum):
    """Parse name_lnum as the string 'name:lnum'.

    Return the tuple (full_pathname, lnum) if success, (None, lnum)
    when name is the name of a clewn buffer, and ('', -1) after
    failing to parse name_lnum.

    """
    name = ''
    lnum = -1
    matchobj = re_filenamelnum.match(name_lnum)
    if matchobj:
        name = matchobj.group('name')
        name = netbeans.full_pathname(name)
        lnum = int(matchobj.group('lnum'))
    return name, lnum

class Debugger(object):
    """Abstract base class for pyclewn debuggers.

    The debugger commands received through netbeans 'keyAtPos' events
    are dispatched to methods whose name starts with the 'cmd_' prefix.

    The signature of the cmd_<command_name> methods are:

        cmd_<command_name>(self, str cmd, str args)
            cmd: the command name
            args: the arguments of the command

    The '__init__' method of the subclass must call the '__init__'
    method of 'Debugger' as its first statement and forward the method
    parameters as an opaque list. The __init__ method must update the
    'cmds' and 'mapkeys' dict attributes with its own commands and key
    mappings.

    Instance attributes:
        cmds: dict
            The debugger command names are the keys. The values are the
            sequence of available completions on the command first
            argument. The sequence is possibly empty, meaning no
            completion. When the value is not a sequence (for example
            None), this indicates file name completion.
        mapkeys: dict
            Key names are the dictionary keys. See the 'keyCommand'
            event in Vim netbeans documentation for the definition of a
            key name. The values are a tuple made of two strings
            (command, comment):
                'command' is the debugger command mapped to this key
                'comment' is an optional comment
            One can use template substitution on 'command', see the file
            runtime/.pyclewn_keys.template for a description of this
            feature.
        started: boolean
            True when the debugger is started.
        closed: boolean
            True when the debugger is closed.
        pyclewn_cmds: dict
            The subset of 'cmds' that are pyclewn specific commands.
        bg_jobs: list
            list of background jobs
        proc_inftty: asyncio.subprocess
            the inferiortty subprocess
        __nbsock: netbeans.Netbeans
            The netbeans protocol.
        _delayed_call: delayed call
            run jobs in the background
        _last_balloon: str
            The last balloonText event received.
        prompt: str
            The prompt printed on the console.
        _consbuffered: boolean
            True when output to the vim debugger console is buffered

    """

    __metaclass__ = ABCMeta

    def __init__(self, vim):
        """Initialize instance variables and the prompt."""
        self.vim = vim
        self.cmds = {
            'dumprepr': (),
            'help': (),
            'loglevel': misc.LOG_LEVELS,
            'mapkeys': (),
            'unmapkeys': (),
            'ballooneval': (),
        }
        self.vim_implementation = ['unmapkeys']
        self.pyclewn_cmds = self.cmds
        self.mapkeys = {}
        self.cmds[''] = []
        self.started = False
        self.closed = False
        self._last_balloon = ''
        self.prompt = '(%s) ' % self.__class__.__name__.lower()
        self._consbuffered = False
        self.__nbsock = None
        self._read_keysfile()
        self.bg_jobs = []
        self.proc_inftty = None
        self._delayed_call = None
        self.ballooneval_enabled = True

    def set_nbsock(self, nbsock):
        """Set the netbeans socket."""
        self.__nbsock = nbsock

    #-----------------------------------------------------------------------
    #   Overidden methods by the Debugger subclass.
    #-----------------------------------------------------------------------

    @abstractmethod
    def pre_cmd(self, cmd, args):
        """The method called before each invocation of a 'cmd_<name>'
        method.

        This method must be implemented in a subclass.

        Method parameters:
            cmd: str
                The command name.
            args: str
                The arguments of the command.

        """

    @abstractmethod
    def default_cmd_processing(self, cmd, args):
        """Fall back method for commands not handled by a 'cmd_<name>'
        method.

        This method must be implemented in a subclass.

        Method parameters:
            cmd: str
                The command name.
            args: str
                The arguments of the command.

        """

    @abstractmethod
    def post_cmd(self, cmd, args):
        """The method called after each invocation of a 'cmd_<name>'
        method.

        This method must be implemented in a subclass.

        Method parameters:
            cmd: str
                The command name.
            args: str
                The arguments of the command.

        """

    def vim_script_custom(self, prefix):
        """Return debugger specific Vim statements as a string.

        A Vim script is run on Vim start-up, for example to define all
        the debugger commands in Vim. This method may be overriden to
        add some debugger specific Vim statements or functions to this
        script.

        Method parameter:
            prefix: str
                The prefix used for the debugger commands in Vim.

        """
        return ''

    #-----------------------------------------------------------------------
    #   The Debugger API.
    #-----------------------------------------------------------------------

    def add_bp(self, bp_id, pathname, lnum):
        """Add a breakpoint to a Vim buffer at lnum.

        Load the buffer in Vim and set an highlighted sign at 'lnum'.

        Method parameters:
            bp_id: object
                The debugger breakpoint id.
            pathname: str
                The absolute pathname to the Vim buffer.
            lnum: int
                The line number in the Vim buffer.

        """
        self.__nbsock.add_bp(bp_id, pathname, lnum)

    def update_bp(self, bp_id, disabled=False):
        """Update the enable/disable state of a breakpoint.

        The breakpoint must have been already set in a Vim buffer with
        'add_bp'.
        Return True when successful.

        Method parameters:
            bp_id: object
                The debugger breakpoint id.
            disabled: bool
                When True, set the breakpoint as disabled.

        """
        return self.__nbsock.update_bp(bp_id, disabled)

    def delete_bp(self, bp_id):
        """Delete a breakpoint.

        The breakpoint must have been already set in a Vim buffer with
        'add_bp'.

        Method parameter:
            bp_id: object
                The debugger breakpoint id.

        """
        self.__nbsock.delete_bp(bp_id)

    def remove_all(self):
        """Remove all annotations.

        Vim signs are unplaced.
        Annotations are not deleted.

        """
        if self.__nbsock:
            self.__nbsock.remove_all()

    def get_lnum_list(self, pathname):
        """Return a list of line numbers of all enabled breakpoints in a
        Vim buffer.

        A line number may be duplicated in the list.
        This is used by Simple and may not be useful to other debuggers.

        Method parameter:
            pathname: str
                The absolute pathname to the Vim buffer.

        """
        return self.__nbsock.get_lnum_list(pathname)

    def update_listbuffer(self, bufname, getdata, dirty, lnum=None):
        """Update a list buffer in Vim.

        Update the list buffer in Vim when one the following conditions
        is True:
            * 'dirty' is True
            * the content of the Vim buffer and the content of the
            pyclewn list buffer are not consistent after an error in the
            netbeans protocol occured
        Set the Vim cursor at 'lnum' after the buffer has been updated.

        Method parameters:
            bufname: str
                The key to self.__nbsock.list_buffers dictionary.
            getdata: callable
                A callable that returns the content of the variables
                buffer as a string.
            dirty: bool
                When True, force updating the buffer.
            lnum: int
                The line number in the Vim buffer.

        """
        if not self.__nbsock:
            return

        lbuf = self.__nbsock.list_buffers[bufname]
        if dirty and not lbuf.buf.registered:
            lbuf.register()

        # Race condition: must note the state of the buffer before
        # updating the buffer, since this will change its visible state
        # temporarily.
        if dirty or lbuf.dirty:
            lbuf.update(getdata())
            # Set the cursor on the current fold when visible.
            if lnum is not None:
                lbuf.setdot(lnum=lnum)

    def show_frame(self, pathname=None, lnum=1):
        """Show the frame highlighted sign in a Vim buffer.

        The frame sign is unique.
        Remove the frame sign when 'pathname' is None.

        Method parameters:
            pathname: str
                The absolute pathname to the Vim buffer.
            lnum: int
                The line number in the Vim buffer.

        """
        self.__nbsock.show_frame(pathname, lnum)

    def balloon_text(self, text):
        """Process a netbeans balloonText event.

        Used when 'ballooneval' is set and the mouse pointer rests on
        some text for a moment.

        Method parameter:
            text: str
                The text under the mouse pointer.

        """
        self._last_balloon = text

    def show_balloon(self, text):
        """Show 'text' in the Vim balloon.

        Method parameter:
            text: str
                The text to show in the balloon.

        """
        if self.ballooneval_enabled:
            self.__nbsock.show_balloon(text)

    def print_prompt(self):
        """Print the prompt in the Vim debugger console."""
        # no buffering until the first prompt:
        # workaround to a bug in netbeans/Vim that does not redraw the
        # console on the first 'insert'
        self._consbuffered = True
        self.console_print(self.prompt)
        console = self.__nbsock.console
        if self.started and console.buf.registered:
            console.flush()

    def get_console(self):
        """Return the console."""
        return self.__nbsock.console

    def console_print(self, format, *args):
        """Print a format string and its arguments to the console.

        Method parameters:
            format: str
                The message format string.
            args: str
                The arguments which are merged into 'format' using the
                python string formatting operator.

        """
        console = self.__nbsock.console
        if self.started and console.buf.registered:
            console.append(format, *args)
            if not self._consbuffered:
                console.flush()

    def console_flush(self):
        """Flush the console."""
        self.__nbsock.console.flush()

    def inferiortty(self, set_inferior_tty_cb):
        """Spawn the inferior terminal."""
        @asyncio.coroutine
        def _set_inferior_tty():
            if self.proc_inftty:
                if self.proc_inftty.returncode is None:
                    self.proc_inftty.terminate()
                self.proc_inftty = None
            try:
                self.proc_inftty = proc = yield from(
                                        asyncio.create_subprocess_exec(*args))
                info('inferiortty: {}'.format(args))
            except OSError as e:
                self.console_print('Cannot spawn terminal: {}\n'.format(e))
            else:
                start = time.time()
                while time.time() - start < 2:
                    try:
                        with open(result_file.name) as f:
                            lines = f.readlines()
                            # Commands found in the result file.
                            if len(lines) == 2:
                                set_inferior_tty_cb(lines[0])
                                set_inferior_tty_cb(lines[1])
                                break
                    except IOError as e:
                        self.console_print(
                            'Cannot set the inferior tty: {}\n'.format(e))
                        proc.terminate()
                        break
                    yield from(asyncio.sleep(.100, loop=self.vim.loop))
                else:
                    self.console_print('Failed to start inferior_tty.py.\n')
                    proc.terminate()

        args = self.vim.options.terminal.split(',')
        result_file = misc.tmpfile('dbg')
        args.extend([sys.executable, '-m', 'clewn.inferiortty',
                     result_file.name])
        asyncio.Task(_set_inferior_tty(), loop=self.vim.loop)

    def close(self):
        """Close the debugger and remove all signs in Vim."""
        info('enter Debugger.close')
        if self.proc_inftty:
            if self.proc_inftty.returncode is None:
                self.proc_inftty.terminate()
            self.proc_inftty = None
        if not self.closed:
            self.started = False
            self.closed = True
            self.vim.signal(self)
            if self._delayed_call:
                self._delayed_call.cancel()
            info('in close: remove all annotations')
            self.remove_all()

    def netbeans_detach(self):
        """Request vim to close the netbeans session."""
        if self.__nbsock:
            self.__nbsock.detach()

    #-----------------------------------------------------------------------
    #   Internally used methods.
    #-----------------------------------------------------------------------

    def _start(self):
        """Start the debugger and print the banner.

        The debugger is automatically started on the first received keyAtPos
        event.

        """
        if not self.started:
            self.started = True

            # Schedule the first '_background_jobs' method.
            self.bg_jobs.append([self.flush_console])
            self._delayed_call = self.vim.loop.call_later(BCKGROUND_JOB_DELAY,
                                            self._background_jobs)

            # Print the banner only with the first netbeans instance.
            if not self.closed:
                self.console_print(
                    'Pyclewn version %s starting a new instance of %s.\n',
                            __version__, self.__class__.__name__.lower())
            else:
                self.console_print(
                    'Pyclewn restarting the %s debugger.\n',
                            self.__class__.__name__.lower())
            self.closed = False
            self.start()

    def start(self):
        """This method must be implemented in a subclass."""

    def _background_jobs(self):
        """Flush the console buffer."""
        self._delayed_call = self.vim.loop.call_later(BCKGROUND_JOB_DELAY,
                                        self._background_jobs)
        for job in self.bg_jobs:
            callback = job[0]
            args = job[1:]
            callback(*args)

    def flush_console(self):
        if not self.__nbsock:
            return
        console = self.__nbsock.console
        if self.started and console.buf.registered and self._consbuffered:
            console.flush(time.time())

    def _get_cmds(self):
        """Return the commands dictionary."""
        # the 'C' command by itself has the whole list of commands
        # as its 1st arg completion list, excluding the '' command
        # and pure vim commands
        self.cmds[''] += [x for x in self.cmds.keys()
                            if x and x not in self.vim_implementation]

        return self.cmds

    def vim_script(self):
        """Build the vim script.

        Each clewn vim command can be invoked as 'prefix' + 'cmd' with optional
        arguments.  The command with its arguments is invoked with ':nbkey' and
        received by pyclewn in a keyAtPos netbeans event.

        Return the file object of the vim script.

        """
        # Create the vim script in a temporary file.
        options = self.vim.options
        prefix = options.prefix.capitalize()
        f = None
        try:
            if not options.editor:
                # pyclewn is started from within vim and the vim
                # argument is the name of the temporary file.
                if options.cargs:
                    f = open(options.cargs[0], 'w')
                else:
                    return None
            else:
                f = misc.TmpFile('vimscript')

            f.write(VIM_SCRIPT_FIXED)

            # Vim autocommands.
            list_buffers_autocmd = ''
            for n in netbeans.LIST_BUFFERS:
                list_buffers_autocmd += (string.Template(LIST_BUFFERS_AUTOCMD)
                                         .substitute(
                                         bufname='(clewn)_%s' % n.lower(),
                                         name=n
                                         ))
            bufferlist_autocmd = (BUFFERLIST_AUTOCMD if
                                  options.noname_fix == '0' else '')
            f.write(string.Template(AUTOCOMMANDS).substitute(
                                    list_buffers_autocmd=list_buffers_autocmd,
                                    bufferlist_autocmd=bufferlist_autocmd))

            # unmapkeys function.
            f.write('function s:unmapkeys()\n')
            for key in self.mapkeys:
                f.write('   try\n')
                f.write('      unmap <%s>\n' % key)
                f.write('   catch /.*/\n')
                f.write('   endtry\n')
            f.write('endfunction\n')

            # Setup pyclewn vim user defined commands.
            if options.noname_fix != '0':
                function_nbcommand = FUNCTION_NBCOMMAND
            else:
                function_nbcommand = FUNCTION_NBCOMMAND_RESTRICT

            split_vars_buf = (SPLIT_VARS_BUF if
                              netbeans.Netbeans.getLength_fix != '0' else '')
            split_bt_buf = (SPLIT_BT_BUF if
                              netbeans.Netbeans.getLength_fix != '0' else '')
            f.write(string.Template(function_nbcommand).substitute(
                                        console=netbeans.CONSOLE,
                                        location=options.window,
                                        split_vars_buf=split_vars_buf,
                                        split_bt_buf=split_bt_buf))
            noCompletion = string.Template('command! -bar -nargs=* ${pre}${cmd} '
                                    'call s:nbcommand("${cmd}", <f-args>)\n')
            fileCompletion = string.Template('command! -bar -nargs=* '
                                    '-complete=file ${pre}${cmd} '
                                    'call s:nbcommand("${cmd}", <f-args>)\n')
            listCompletion = string.Template('command! -bar -nargs=* '
                                    '-complete=custom,s:Arg_${cmd} ${pre}${cmd} '
                                    'call s:nbcommand("${cmd}", <f-args>)\n')
            argsList = string.Template('function s:Arg_${cmd}(A, L, P)\n'
                                    '\treturn "${args}"\n'
                                    'endfunction\n')
            for cmd, completion in self._get_cmds().items():
                if cmd in ('mapkeys', 'unmapkeys'):
                    f.write(string.Template('command! -bar ${pre}${cmd} call '
                            's:${cmd}()\n').substitute(cmd=cmd, pre=prefix))
                    continue

                try:
                    iter(completion)
                except TypeError:
                    f.write(fileCompletion.substitute(pre=prefix, cmd=cmd))
                else:
                    if not completion:
                        f.write(noCompletion.substitute(pre=prefix, cmd=cmd))
                    else:
                        f.write(listCompletion.substitute(pre=prefix, cmd=cmd))
                        args = '\\n'.join(completion)
                        f.write(argsList.substitute(args=args, cmd=cmd))

            # Add debugger specific vim statements.
            f.write(self.vim_script_custom(prefix))

            # Reset 'cpo' option.
            f.write('let &cpo = s:cpo_save\n')

            # Delete the vim script after it has been sourced.
            f.write('\ncall delete(expand("<sfile>"))\n')
        finally:
            if f:
                f.close()

        return f

    def _do_cmd(self, method, cmd, args):
        """Process 'cmd' and its 'args' with 'method'."""
        self.pre_cmd(cmd, args)
        method(cmd, args)
        self.post_cmd(cmd, args)

    def _dispatch_keypos(self, cmd, args, buf, lnum):
        """Dispatch the keyAtPos event to the proper cmd_xxx method."""
        if not self.started:
            self._start()

        # do key mapping substitution
        mapping = self._keymaps(cmd, buf, lnum)
        if mapping:
            cmd, args = (lambda a, b='': (a, b))(*mapping.split(None, 1))

        try:
            method = getattr(self, 'cmd_%s' % cmd)
        except AttributeError:
            method = self.default_cmd_processing

        self._do_cmd(method, cmd, args)

    def _keymaps(self, key, buf, lnum):
        """Substitute a key with its mapping."""
        cmdline = ''
        if key in self.mapkeys.keys():
            t = string.Template(self.mapkeys[key][0])
            cmdline = t.substitute(fname=buf.name, lnum=lnum,
                                            text=self._last_balloon)
            assert len(cmdline) != 0
        return cmdline

    def _read_keysfile(self):
        """Read the keys mappings file.

        An empty entry deletes the key in the mapkeys dictionary.

        """
        path = os.environ.get('CLEWNDIR')
        if not path:
            path = os.environ.get('HOME')
        if not path:
            return
        path = os.path.join(path,
                    '.pyclewn_keys.' + self.__class__.__name__.lower())
        if not os.path.exists(path):
            return

        info('reading %s', path)
        try:
            with open(path) as f:
                for line in f:
                    matchobj = re_key.match(line)
                    if matchobj:
                        k = matchobj.group('key').upper()
                        v = matchobj.group('value')
                        # delete key when empty value
                        if not v:
                            if k in self.mapkeys:
                                del self.mapkeys[k]
                        else:
                            self.mapkeys[k] = (v.strip(),)
                    elif not re_comment.match(line):
                        raise ClewnError('invalid line in %s: %s' %
                                         (path, line))
        except IOError:
            critical('reading %s', path); raise

    def cmd_help(self, *args):
        """Print help on all pyclewn commands in the Vim debugger
        console."""
        for cmd in sorted(self.pyclewn_cmds):
            if cmd:
                method = getattr(self, 'cmd_%s' % cmd, None)
                if method is not None:
                    doc = ''
                    if method.__doc__ is not None:
                        doc = method.__doc__.split('\n')[0]
                    self.console_print('%s -- %s\n', cmd, doc)

    def cmd_dumprepr(self, cmd, args):
        """Print debugging information on netbeans and the debugger."""
        # dumprepr is used by the testsuite to detect the end of
        # processing by pyclewn of all commands, so as to parse the
        # results and check the test
        if not (self.vim.testrun and args):
            self.console_print(
                'netbeans:\n%s\n' % misc.pformat(self.__nbsock.__dict__)
                + '%s:\n%s\n' % (self.__class__.__name__.lower(), self))
            self.print_prompt()

    def cmd_loglevel(self, cmd, level):
        """Get or set the pyclewn log level."""
        if not level:
            level = logging.getLevelName(logging.getLogger().level).lower()
            self.console_print("The pyclewn log level is currently '%s'.\n"
                                                                    % level)
        elif level.lower() in misc.LOG_LEVELS:
            if level.lower() == misc.NBDEBUG_LEVEL_NAME:
                logging.getLogger().setLevel(misc.NBDEBUG)
            else:
                logging.getLogger().setLevel(getattr(logging, level.upper()))
            self.console_print('Pyclewn log level is set to %s.\n' % level)
        else:
            self.console_print("'%s' is not a valid log level.\n" % level)
        self.print_prompt()

    def cmd_mapkeys(self, *args):
        """Map the pyclewn keys."""
        for k in sorted(self.mapkeys):
            self.__nbsock.special_keys(k)

        text = ''
        for k in sorted(self.mapkeys):
            if len(self.mapkeys[k]) == 2:
                comment = ' # ' + self.mapkeys[k][1]
                text += '  %s%s\n' %                        \
                            (('%s : %s' %                   \
                                    (k, self.mapkeys[k][0])).ljust(30), comment)
            else:
                text += '  %s : %s\n' % (k, self.mapkeys[k][0])

        self.console_print(text)
        self.print_prompt()

    def not_a_pyclewn_method(self, cmd):
        """"Warn that 'cmd' cannot be used as 'C' parameter."""
        table = {'cmd': cmd, 'C': self.vim.options.prefix}
        self.console_print("'%(cmd)s' cannot be used as '%(C)s' parameter,"
                " use '%(C)s%(cmd)s' instead.\n" % table)
        self.print_prompt()

    def cmd_unmapkeys(self, cmd, *args):
        """Unmap the pyclewn keys.

        This is actually a Vim command and it does not involve pyclewn.

        """
        self.not_a_pyclewn_method(cmd)

    def cmd_ballooneval(self, *args):
        """Enable or disable showing text in Vim balloon."""
        self.ballooneval_enabled = False if self.ballooneval_enabled else True
        setting = 'en' if self.ballooneval_enabled else 'dis'
        self.console_print('ballooneval has been %sabled.\n' % setting)
        self.print_prompt()

    def __str__(self):
        """Return the string representation."""
        shallow = copy.copy(self.__dict__)
        for name in list(shallow):
            if name in ('cmds', 'pyclewn_cmds', 'mapkeys'):
                del shallow[name]
        return misc.pformat(shallow)

