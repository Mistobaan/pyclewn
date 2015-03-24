# vi:set ts=8 sts=4 sw=4 et tw=80:
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
import pkgutil
import copy
import subprocess
from abc import ABCMeta, abstractmethod

from . import __version__, ClewnError, misc, netbeans, runtime_version

BCKGROUND_JOB_DELAY = .200
COMPLETION_SUFFIX = ' %(pre)s%(cmd)s call s:nbcommand("%(cmd)s", <f-args>)'
NOCOMPLETION = 'command! -bar -nargs=*' + COMPLETION_SUFFIX
FILECOMPLETION = 'command! -bar -nargs=* -complete=file' + COMPLETION_SUFFIX
LISTCOMPLETION = \
'command! -bar -nargs=* -complete=custom,s:Arg_%(cmd)s' + COMPLETION_SUFFIX
ARGSLIST = '''
function s:Arg_%(cmd)s(A, L, P)
    return "%(args)s"
endfunction
'''

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
        if not self.__nbsock or not self.__nbsock.list_buffers:
            return

        # Only update if the tabpage contains list buffers or the console.
        if not netbeans.ClewnBuffer.clewn_tabpage and bufname != 'variables':
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

    def update_tabpage_buffers(self):
        """Update all the list buffers that may be located in a tab page."""

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
        args.append('%s -m clewn.inferiortty %s' %
                    (sys.executable, result_file.name))
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
        options = self.vim.options
        prefix = options.prefix.capitalize()

        commands = []
        substitute = {'pre': prefix}
        for cmd, completion in self._get_cmds().items():
            substitute['cmd'] = cmd
            if cmd in ('mapkeys', 'unmapkeys'):
                commands.append(
                    'command! -bar %(pre)s%(cmd)s call s:%(cmd)s()'
                    % substitute)
                continue

            try:
                iter(completion)
            except TypeError:
                commands.append(FILECOMPLETION % substitute)
            else:
                if not completion:
                    commands.append(NOCOMPLETION % substitute)
                else:
                    commands.append(LISTCOMPLETION % substitute)
                    substitute['args'] = '\\n'.join(completion)
                    commands.append(ARGSLIST % substitute)

        # Create the vim script in a temporary file.
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

            substitute = {
                'pre': prefix,
                'window': options.window,
                'noname_fix': options.noname_fix,
                'getLength_fix': netbeans.Netbeans.getLength_fix,
                'console': netbeans.CONSOLE,
                'mapkeys': ', '.join('"<' + k + '>"' for k in self.mapkeys),
                'commands': '\n'.join(commands),
                'debugger': self.__class__.__name__.lower(),
                'debugger_specific': self.vim_script_custom(prefix),
                'version': __version__,
                'runtime_version': runtime_version.version,
                         }
            f.write(pkgutil.get_data(__name__, 'debugger.vim').decode()
                    % substitute)

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
        # Do key mapping substitution.
        mapping = self._keymaps(cmd, buf, lnum)
        if mapping:
            cmd, args = (lambda a, b='': (a, b))(*mapping.split(None, 1))

        if not self.started:
            self._start()

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

