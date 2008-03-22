# vi:set ts=8 sts=4 sw=4 et tw=80:
#
# Copyright (C) 2007 Xavier de Gaye.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program (see the file COPYING); if not, write to the
# Free Software Foundation, Inc.,
# 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA
#
# $Id$
"""Pyclewn is a program that allows the use of gvim as a front end to a
debugger.

A debugger is added by implementing a new module in the debugger directory of
the clewn package. The module contains a subclass of Application.  The abstract
class Application provides the following methods to control gvim:

console_print       print on the pyclewn gvim console
show_balloon        display a balloon in gvim
add_bp              add a breakpoint sign
delete_bp           delete a breakpoint sign
update_bp           change the state of a breakpoint sign
delete_all          remove signs on one line, all lines
show_frame          show the sign of the line in the current frame
close               close the application and remove all signs

Summary of the components of a subclass of Application that must be implemented
(the simple.py module can be used as an example):

    . class attributes that describe the available command line options

    . a dictionary of the debugger commands and their first argument
      completion

    . a dictionary of the keys and their mappings

    . the implementation of the methods:
        default_cmd_processing
        pre_cmd
        post_cmd

    . the implementation of the methods cmd_<name>. When the implementation of
      a method is missing, pyclewn invokes the default_cmd_processing method
      unless it is an illegal command

      the method signature is cmd_<name>(self, buf, cmd, args)

        buf: netbeans.Buffer
            the buffer instance
        cmd: str
            the command name (equal to <name>)
        args: str
            the arguments of the command
"""


import os
import os.path
import re
import pprint
import string
import copy

import clewn
import misc
import netbeans

RE_KEY = r'^\s*(?P<key>[Ff]\d{1,2}|[A-Z]|[C-c]-[A-Za-z])\s*'    \
         r':\s*(?P<value>[^#]*)'                                \
         r'# RE: key:value line in .pyclewn_keys'
RE_COMMENT = r'^\s*([#].*|\s*)$'                                \
             r'# RE: a comment line'
RE_FILENAMELNUM = r'^(?P<name>\S+):(?P<lnum>\d+)$'              \
                  r'# RE: pathname:lnum'

# compile regexps
re_key = re.compile(RE_KEY, re.VERBOSE)
re_comment = re.compile(RE_COMMENT, re.VERBOSE)
re_filenamelnum = re.compile(RE_FILENAMELNUM, re.VERBOSE)

AUTOCOMMANDS = """
augroup clewn
    autocmd!
    autocmd BufWinEnter (clewn)_* silent! setlocal bufhidden=hide"""    \
"""                                     | setlocal buftype=nofile"""    \
"""                                     | setlocal fileformat=unix"""   \
"""                                     | setlocal expandtab"""         \
"""                                     | setlocal nowrap"""            \
"""
    autocmd BufWinEnter ${console} silent! nbkey ClewnBuffer.Console.open
    autocmd BufWinLeave ${console} silent! nbkey ClewnBuffer.Console.close
    autocmd BufWinEnter ${variables} silent! nbkey ClewnBuffer.DebuggerVarBuffer.open
    autocmd BufWinLeave ${variables} silent! nbkey ClewnBuffer.DebuggerVarBuffer.close
    autocmd BufWinEnter ${variables} silent! setlocal syntax=dbgvar
    autocmd BufNew * silent! call s:getfilevt()
augroup END

let s:nofileOpened = 1

"""

FUNCTION_GETFILEVT = """
" Vim discards nbkey requests on an unknown buffer (unknown to the netbeans
" implementation in gvim). Instead, vim sends a fileOpened event. The workaround
" is to send a fake "" nbkey request for the very first buffer: this triggers a
" fileOpened event, pyclewn in return sends a putBufferNumber command, and the
" buffer is learnt by the netbeans implementation in gvim. This takes care of
" problems to display the console with the "[No Name]" buffer, and a buffer
" opened by an argument on vim command line (and unknown to netbeans).
function s:getfilevt()
    if s:nofileOpened
        silent! nbkey ""
        let s:nofileOpened = 0
    endif
endfunction

"""

FUNCTION_CONSOLE = """
" Split the window that is on top and display the console.
" When the console is already displayed, show the last line.
function s:console(file)
    let name = bufname("%")
    let n = bufwinnr(name)

    if bufwinnr(a:file) == -1
	" horizontal split on top, set at previewheight
	1wincmd w
	exe &pvh . "split " . a:file
	let n = n + 1
	normal G
    endif

    " return to the previous buffer
    if name != "" && name != a:file
        exe n . "wincmd w"
    endif
endfunction

"""

FUNCTION_NBCOMMAND = """
" run the nbkey netbeans Vim command
function s:nbcommand(...)
    if bufname("%") == ""
        echohl ErrorMsg
        echo "You cannot use pyclewn on a '[No Name]' file, please load a file first."
        echohl None
        return
    endif

    " allow '' first arg: the 'C' command followed by a mandatory parameter
    if a:0 != 0
        if a:1 != "" || (a:0 > 1 && a:2 != "")
            call s:console("${console}")

            let cmd = "nbkey " . join(a:000, ' ')
            exe cmd
        endif
    endif
endfunction

"""

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('app')


class BufferSet(dict):
    """The Vim buffer set is a dictionary of {pathname: Buffer instance}.

    BufferSet is a singleton.

    Instance attributes:
        nbsock: netbeans.Netbeans
            the netbeans socket
        buf_list: python list
            the list of Buffer instances indexed by netbeans 'bufID'
        anno_dict: dictionary
            global dictionary of all annotations {anno_id: Buffer instance}

    A Buffer instance is never removed from BufferSet.

    """

    # defeating pychecker check on non-initialized data members
    _buf_list = None
    _anno_dict = None

    def __new__(cls, *args, **kwds):
        """A singleton."""
        unused = args
        unused = kwds
        it = cls.__dict__.get("__it__")
        if it is not None:
            return it
        # cannot subclass netbeans.Singleton, this gives the following error msg:
        # TypeError: object.__new__(BufferSet) is not safe, use dict.__new__()
        cls.__it__ = it = dict.__new__(cls)
        it.init()
        return it

    def init(self):
        """Initialize once."""
        self._buf_list = []
        self._anno_dict = {}

    def __init__(self, nbsock):
        """Constructor."""
        self.nbsock = nbsock
        self.buf_list = self._buf_list
        self.anno_dict = self._anno_dict

    def add_anno(self, anno_id, pathname, lnum):
        """Add the annotation to the global list and to the buffer annotation list."""
        assert lnum > 0
        assert not anno_id in self.anno_dict.keys()
        assert os.path.isabs(pathname), \
                'absolute pathname required for: "%s"' % pathname
        buf = self[pathname]
        self.anno_dict[anno_id] = buf
        buf.add_anno(anno_id, lnum)

    def update_anno(self, anno_id, disabled=False):
        """Update the annotation."""
        assert anno_id in self.anno_dict.keys()
        self.anno_dict[anno_id].update(anno_id, disabled)

    def delete_anno(self, anno_id):
        """Delete the annotation from the global list and from the buffer
        annotation list.

        """
        assert anno_id in self.anno_dict.keys()
        self.anno_dict[anno_id].delete_anno(anno_id)
        del self.anno_dict[anno_id]

    def show_frame(self, pathname=None, lnum=1):
        """Show the frame annotation.

        The frame annotation is unique.
        Remove the frame annotation when pathname is None.

        """
        assert lnum > 0
        if netbeans.FRAME_ANNO_ID in self.anno_dict.keys():
            self.delete_anno(netbeans.FRAME_ANNO_ID)
        if pathname:
            self.add_anno(netbeans.FRAME_ANNO_ID, pathname, lnum)

    def add_bp(self, bp_id, pathname, lnum):
        """Add the breakpoint to the global list and to the buffer annotation list."""
        assert lnum > 0
        if not bp_id in self.anno_dict.keys():
            self.add_anno(bp_id, pathname, lnum)
        else:
            error('attempt to add a breakpoint that already exists')

    def update_bp(self, bp_id, disabled=False):
        """Update the breakpoint.

        Return True when successful.

        """
        if bp_id in self.anno_dict.keys():
            self.update_anno(bp_id, disabled)
            return True
        else:
            error('attempt to update an unknown annotation')
            return False

    def getbuf(self, buf_id):
        """Return the Buffer at idx in list."""
        assert isinstance(buf_id, int)
        if buf_id <= 0 or buf_id > len(self.buf_list):
            return None
        return self.buf_list[buf_id - 1]

    def delete_all(self, pathname=None, lnum=None):
        """Delete all annotations.

        Delete all annotations in pathname at lnum.
        Delete all annotations in pathname if lnum is None.
        Delete all annotations in all buffers if pathname is None.
        The anno_dict dictionary is updated accordingly.
        Return the list of deleted anno_id.

        """
        if pathname is None:
            lnum = None
        else:
            assert os.path.isabs(pathname), \
                    'absolute pathname required for: "%s"' % pathname

        deleted = []
        for buf in self.buf_list:
            if pathname is None or buf.name == pathname:
                # remove annotations from the buffer
                buf.removeall(lnum)

                # delete annotations from anno_dict
                anno_list = []
                for (anno_id, anno) in buf.iteritems():
                    if lnum is None or anno.lnum == lnum:
                        del self.anno_dict[anno_id]
                        anno_list.append(anno_id)

                # delete annotations from the buffer
                for anno_id in anno_list:
                    del buf[anno_id]

                deleted.extend(anno_list)

        return deleted

    def get_lnum_list(self, pathname):
        """Return the list of line numbers of all enabled breakpoints.

        A line number may be duplicated in the list.

        """
        lnum_list = []
        if pathname in self:
            lnum_list = [anno.lnum for anno in self[pathname].values()
                        if not anno.disabled
                        and not isinstance(anno, netbeans.FrameAnnotation)]
        return lnum_list

    #-----------------------------------------------------------------------
    #   Dictionary methods
    #-----------------------------------------------------------------------
    def __getitem__(self, pathname):
        """Get Buffer with pathname as key, instantiate one when not found.

        The pathname parameter must be an absolute path name.

        """
        assert isinstance(pathname, str)
        assert os.path.isabs(pathname)                          \
                or netbeans.is_clewnbuf(pathname),              \
                'absolute pathname required: "%s"' % pathname
        if not pathname in self:
            # netbeans buffer numbers start at one
            buf = netbeans.Buffer(pathname, len(self.buf_list) + 1, self.nbsock)
            self.buf_list.append(buf)
            dict.__setitem__(self, pathname, buf)
        return dict.__getitem__(self, pathname)

    def __setitem__(self, pathname, item):
        """Mapped to __getitem__."""
        unused = item
        self.__getitem__(pathname)

    def setdefault(self, pathname, failobj=None):
        """Mapped to __getitem__."""
        unused = failobj
        return self.__getitem__(pathname)

    def __delitem__(self, key):
        """A key is never removed."""
        pass

    def popitem(self):
        """A key is never removed."""
        pass

    def pop(self, key, *args):
        """A key is never removed."""
        pass

    def update(self, dict=None, **kwargs):
        """Not implemented."""
        unused = self
        unused = dict
        unused = kwargs
        assert False, 'not implemented'

    def copy(self):
        """Not implemented."""
        unused = self
        assert False, 'not implemented'

class Application(object):
    """Abstract base class for pyclewn applications.

    An Application subclass is registered with the Dispatcher instance. The
    application commands received in keyAtPos events are handled by methods
    whose names start with the 'cmd_' prefix.

    Class attributes:
        opt: str
            command line short option
        long_opt: str
            command line long option
        help: str
            command line help
        param: boolean
            when True, a parameter is required to opt and long_opt
        metavar: str
            see the python standard optparse module: 'Generating help'

    Instance attributes:
        cmds: dict
            dictionary of commands: first argument completion value
            a command value can be:
                () or []: no completion
                a non empty list or tuple: first argument list
                anything else: file name completion on the first argument
        pyclewn_cmds: dict
            the subset of 'cmds' that are pyclewn specific commands
        mapkeys: dict
            dictionary of vim key: tuple (command, comment):
                command is the command mapped to the key
                comment is an optional comment
        pgm: str or None
            the application command or pathname
        arglist: list or None
            the application command line arguments
        nbsock: netbeans.Netbeans
            the netbeans socket
        daemon: boolean
            True when run as a daemon
        _bset: BufferSet
            the buffer list
        closed: boolean
            application is closed
        started: boolean
            True when the application is started
        last_balloon: str
            last balloonText event received
        prompt_str: str
            prompt printed on the console

    """

    # the debugger options
    # one of opt or long_opt is mandatory
    opt = None          # command line short option
    long_opt = None     # command line long option
    help = None         # command line help
    param = False       # no parameter
    metavar = None      # see the optparse python module

    def __init__(self, nbsock, daemon=False, pgm=None, arglist=None):
        """Initialize instance variables and the prompt."""
        self.cmds = {
            'dbgvar':(),
            'delvar':(),
            'dumprepr':(),
            'help':(),
            'mapkeys':(),
            'sigint':(),
            'symcompletion':(),
            'unmapkeys':(),
        }
        self.pyclewn_cmds = self.cmds
        self.mapkeys = {}

        self.pgm = pgm
        self.arglist = arglist
        self.nbsock = nbsock
        self.daemon = daemon
        self._bset = BufferSet(nbsock)
        self.cmds[''] = []
        self.closed = False
        self.started = False
        self.last_balloon = ''
        self.prompt_str = '(%s) ' % self.__class__.__name__.lower()

    def get_cmds(self):
        """Return the commands dictionary."""
        # the 'C' command by itself has the whole list of commands
        # as its 1st arg completion list, excluding the '' command
        self.cmds[''] += [x for x in self.cmds.keys() if x]

        return self.cmds

    def vim_script_custom(self, prefix):
        """Return application specific vim statements to add to the vim script."""
        return ''

    def vim_script(self, prefix):
        """Build the vim script.

        Argument:
            prefix: str
                the clewn command prefix

        Each clewn vim command can be invoked as 'prefix' + 'cmd' with optional
        arguments.  The command with its arguments is invoked with ':nbkey' and
        received by pyclewn in a keyAtPos netbeans event.

        Return the file object of the vim script.

        """
        # create the vim script in a temporary file
        prefix = prefix.capitalize()
        f = None
        try:
            f = misc.TmpFile('vimscript')

            # set 'cpo' option to its vim default value
            f.write('let s:cpo_save=&cpo\n')
            f.write('set cpo&vim\n')

            # vim autocommands
            f.write(string.Template(AUTOCOMMANDS).substitute(
                                        console=netbeans.CONSOLE,
                                        variables=netbeans.VARIABLES_BUFFER))

            # popup gdb console on pyclewn mapped keys
            f.write(string.Template(
                'cnoremap nbkey call <SID>console("${console}") <Bar> nbkey'
                ).substitute(console=netbeans.CONSOLE))

            # utility vim functions
            f.write(FUNCTION_GETFILEVT)
            f.write(FUNCTION_CONSOLE)

            # unmapkeys script
            f.write('function s:unmapkeys()\n')
            for key in self.mapkeys:
                f.write('unmap <%s>\n' % key)
            f.write('endfunction\n')

            # setup pyclewn vim user defined commands
            f.write(string.Template(FUNCTION_NBCOMMAND).substitute(
                                                    console=netbeans.CONSOLE))
            noCompletion = string.Template('command -bar -nargs=* ${pre}${cmd} '
                                    'call s:nbcommand("${cmd}", <f-args>)\n')
            fileCompletion = string.Template('command -bar -nargs=* '
                                    '-complete=file ${pre}${cmd} '
                                    'call s:nbcommand("${cmd}", <f-args>)\n')
            listCompletion = string.Template('command -bar -nargs=* '
                                    '-complete=custom,s:Arg_${cmd} ${pre}${cmd} '
                                    'call s:nbcommand("${cmd}", <f-args>)\n')
            argsList = string.Template('function s:Arg_${cmd}(A, L, P)\n'
                                    '\treturn "${args}"\n'
                                    'endfunction\n')
            unmapkeys = string.Template('command -bar ${pre}unmapkeys '
                                        'call s:unmapkeys()\n')
            for cmd, completion in self.get_cmds().iteritems():
                if cmd == 'unmapkeys':
                    f.write(unmapkeys.substitute(pre=prefix))
                elif not completion:
                    f.write(noCompletion.substitute(pre=prefix, cmd=cmd))
                elif isinstance(completion, (list, tuple)):
                    f.write(listCompletion.substitute(pre=prefix, cmd=cmd))
                    args = '\\n'.join(completion)
                    f.write(argsList.substitute(args=args, cmd=cmd))
                else:
                    f.write(fileCompletion.substitute(pre=prefix, cmd=cmd))

            # add application specific vim statements
            f.write(self.vim_script_custom(prefix))

            # reset 'cpo' option
            f.write('let &cpo = s:cpo_save\n')

            # delete the vim script after it has been sourced
            f.write('\ncall delete(expand("<sfile>"))\n')
        finally:
            if f:
                f.close()

        return f

    def start(self):
        """Start the application and print the banner.

        The application is automatically started on the first received keyAtPos
        event.

        """
        if not self.started:
            self.started = True
            self.console_print(
                'Pyclewn version %s starting a new instance of %s.\n\n',
                        clewn.__version__, self.__class__.__name__.lower())

    def prompt(self):
        """Print the prompt."""
        self.console_print(self.prompt_str)

    def timer(self):
        """Handle a timer event sent from the dispatch loop."""
        pass

    #-----------------------------------------------------------------------
    #   commands
    #-----------------------------------------------------------------------

    def default_cmd_processing(self, cmd, args):
        """Default method for cmds not handled by a 'cmd_xxx' method.

            cmd: str
                the command name
            args: str
                the arguments of the command

        """
        unused = self
        unused = cmd
        unused = args
        raise NotImplementedError('must be implemented in subclass')

    def pre_cmd(self, cmd, args):
        """The method called before each invocation of a 'cmd_xxx' method."""
        unused = self
        unused = cmd
        unused = args
        raise NotImplementedError('must be implemented in subclass')

    def post_cmd(self, cmd, args):
        """The method called after each invocation of a 'cmd_xxx' method."""
        unused = self
        unused = cmd
        unused = args
        raise NotImplementedError('must be implemented in subclass')

    def cmd_dbgvar(self, cmd, args):
        """Add a variable to the debugger variable buffer."""
        unused = self
        unused = cmd
        unused = args
        raise NotImplementedError('must be implemented in subclass')

    def cmd_delvar(self, cmd, args):
        """Delete a variable from the debugger variable buffer."""
        unused = self
        unused = cmd
        unused = args
        raise NotImplementedError('must be implemented in subclass')

    def cmd_dumprepr(self, *args):
        """Print debugging information on netbeans and the application."""
        unused = args
        self.console_print(
                'netbeans:\n%s\n' % pprint.pformat(self.nbsock.__dict__)
                + '%s:\n%s\n' % (self.__class__.__name__.lower(), self))
        self.prompt()

    def cmd_help(self, *args):
        """Print help on the pyclewn specific commands."""
        unused = args
        for cmd in sorted(self.pyclewn_cmds):
            if cmd:
                method = getattr(self, 'cmd_%s' % cmd)
                self.console_print('%s -- %s\n', cmd,
                                    method.__doc__.split('\n')[0])

    def cmd_mapkeys(self, *args):
        """Map the pyclewn keys."""
        unused = args
        for k in sorted(self.mapkeys):
            self.nbsock.special_keys(k)

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
        self.prompt()

    def cmd_sigint(self, *args):
        """Send a <C-C> character to the debugger (not implemented)."""
        unused = self
        unused = args
        assert False, 'not implemented'

    def cmd_symcompletion(self, *args):
        """Populate the break and clear commands with symbols completion (not implemented)."""
        unused = self
        unused = args
        assert False, 'not implemented'

    def cmd_unmapkeys(self, *args):
        """Unmap the pyclewn keys, this vim command does not invoke pyclewn."""
        pass

    #-----------------------------------------------------------------------
    #   interface
    #-----------------------------------------------------------------------
    def close(self):
        """Close the application and remove all signs in gvim."""
        if not self.closed:
            # delete all annotations
            self.delete_all()
            self.closed = True

    def console_print(self, format, *args):
        """Print a format string and its arguments to the console.

        Argument format is the message format string, and the args are the
        arguments which are merged into format using the python string
        formatting operator.

        """
        console = self.nbsock.console
        if self.started and console.buf.registered:
            console.eofprint(format, *args)

    def add_bp(self, bp_id, pathname, lnum):
        """Add a breakpoint to pathname at lnum."""
        self._bset.add_bp(bp_id, pathname, lnum)

    def delete_bp(self, bp_id):
        """Delete the breakpoint."""
        self._bset.delete_anno(bp_id)

    def delete_all(self, pathname=None, lnum=None):
        """Delete all breakpoints.

        Delete all breakpoints in pathname at lnum.
        Delete all breakpoints in pathname if lnum is None.
        Delete all breakpoints in all buffers if pathname is None.

        """
        return self._bset.delete_all(pathname, lnum)

    def update_bp(self, bp_id, disabled=False):
        """Update the breakpoint state.

        Return True when successful.

        """
        return self._bset.update_bp(bp_id, disabled)

    def show_frame(self, pathname=None, lnum=1):
        """Show the frame annotation.

        The frame annotation is unique.
        Remove the frame annotation when pathname is None.

        """
        self._bset.show_frame(pathname, lnum)

    def show_balloon(self, text):
        """Show the vim balloon."""
        self.nbsock.show_balloon(text)

    def get_lnum_list(self, pathname):
        """Return the list of line numbers of all enabled breakpoints.

        A line number may be duplicated in the list.
        This is used by Simple and may not be useful to other debuggers.

        """
        return self._bset.get_lnum_list(pathname)

    #-----------------------------------------------------------------------
    #   process received netbeans events
    #-----------------------------------------------------------------------

    def balloon_text(self, text):
        """Process a netbeans balloonText event.

        Used when 'ballooneval' is set and the mouse pointer rests on
        some text for a moment. "text" is a string, the text under
        the mouse pointer.

        """
        self.last_balloon = text

    def do_cmd(self, method, cmd, args):
        """Process 'cmd' and its 'args' with 'method'."""
        self.pre_cmd(cmd, args)
        method(cmd, args)
        self.post_cmd(cmd, args)

    def dispatch_keypos(self, cmd, args, buf, lnum):
        """Dispatch the keyAtPos event to the proper cmd_xxx method."""
        if not self.started:
            self.start()

        # do key mapping substitution
        mapping = self.keymaps(cmd, buf, lnum)
        if mapping:
            cmd, args = (lambda a, b='': (a, b))(*mapping.split(None, 1))

        try:
            method = getattr(self, 'cmd_%s' % cmd)
        except AttributeError:
            method = self.default_cmd_processing

        self.do_cmd(method, cmd, args)

    #-----------------------------------------------------------------------
    #   utilities
    #-----------------------------------------------------------------------

    def full_pathname(self, name):
        """Return the full pathname or None if name is a clewn buffer name."""
        unused = self
        if netbeans.is_clewnbuf(name):
            name = None
        elif not os.path.isabs(name):
            name = os.path.abspath(name)
        return name

    def name_lnum(self, name_lnum):
        """Parse name_lnum as the string 'name:lnum'.

        Return the tuple (full_pathname, lnum) if success, (None, '')
        when name is the name of a clewn buffer, and ('', '') after
        failing to parse name_lnum.

        """
        name = lnum = ''
        matchobj = re_filenamelnum.match(name_lnum)
        if matchobj:
            name = matchobj.group('name')
            name = self.full_pathname(name)
            lnum = int(matchobj.group('lnum'))
        return name, lnum

    def keymaps(self, key, buf, lnum):
        """Substitute a key with its mapping."""
        cmdline = ''
        if key in self.mapkeys.keys():
            t = string.Template(self.mapkeys[key][0])
            cmdline = t.substitute(fname=buf.name, lnum=lnum,
                                            text=self.last_balloon)
            assert len(cmdline) != 0
        return cmdline

    def read_keysfile(self):
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
            f = open(path)
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
                    raise misc.Error('invalid line in %s: %s' % (path, line))
            f.close()
        except IOError:
            critical('reading %s', path); raise

    def __str__(self):
        """Return the string representation."""
        shallow = copy.copy(self.__dict__)
        for name in ('cmds', 'pyclewn_cmds', 'mapkeys'):
            if shallow.has_key(name):
                del shallow[name]
        return pprint.pformat(shallow)

