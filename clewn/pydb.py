# vi:set ts=8 sts=4 sw=4 et tw=80:
#
# Copyright (C) 2010 Xavier de Gaye.
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

"""The Pdb debugger.
"""

import sys
import os
import bdb
import pdb
import threading
import time
import reprlib as _repr
import io

from . import (misc, debugger, asyncproc, evtloop)
try:
    from collections import OrderedDict
except ImportError:
    from .misc import OrderedDict

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('pdb')
Unused = warning

# list of pdb commands mapped to vim user commands C<command>
PDB_CMDS = {
    'help': (),
    'break': None,   # file name completion
    'tbreak': None,   # file name completion
    'enable': (),
    'disable': (),
    'condition': (),
    'ignore': (),
    'clear': None,   # file name completion
    'where': (),
    'bt': (),
    'up': (),
    'down': (),
    'step': (),
    'interrupt': (),
    'next': (),
    'return': (),
    'continue': (),
    'jump': (),
    'detach': (),
    'quit': (),
    'args': (),
    'p': (),
    'pp': (),
    'alias': (),
    'unalias': (),
    'threadstack': (),
}

# list of key mappings, used to build the .pyclewn_keys.gdb file
#     key : (mapping, comment)
MAPKEYS = {
    'S-B': ('break',),
    'S-A': ('args',),
    'S-S': ('step',),
    'C-Z': ('interrupt',),
    'C-N': ('next',),
    'S-R': ('return',),
    'S-C': ('continue',),
    'S-W': ('where',),
    'C-U': ('up',),
    'C-D': ('down',),
    'C-B': ('break "${fname}:${lnum}"',
                'set breakpoint at current line'),
    'C-E': ('clear "${fname}:${lnum}"',
                'clear breakpoint at current line'),
    'C-P': ('p ${text}',
                'print value of selection at mouse position'),
}

CLEWN_CMDS = ('interrupt', 'detach', 'threadstack')

def remove_quotes(args):
    """Remove quotes from a string."""
    matchobj = misc.re_quoted.match(args)
    if matchobj:
        args = matchobj.group(1)
    return args

def breakpoint_by_number(i):
    """Return a (breakpoint, error msg) by the breakpoint number."""
    try:
        i = int(i)
    except ValueError:
        err = 'Breakpoint index %r is not a number' % i
    else:
        try:
            bp = bdb.Breakpoint.bpbynumber[i]
        except IndexError:
            err = 'Breakpoint number (%d) out of range' % i
        else:
            if bp:
                return bp, ''
            err = 'Breakpoint (%d) already deleted' % i
    return None, err

def update_condition(arg):
    """Update the condition of a breakpoint."""
    # arg is breakpoint number and condition
    args = arg.split(' ', 1)
    bp, err = breakpoint_by_number(args[0])
    if bp:
        if len(args) == 1:
            cond = None
        else:
            cond = args[1].strip()
        bp.cond = cond
        if not cond:
            print('Breakpoint', bp.number, end=' ')
            print('is now unconditional.')
    else:
        print('***', err)

def update_ignore(arg):
    """Sets the ignore count for the given breakpoint number."""
    args = arg.split(' ', 1)
    bp, err = breakpoint_by_number(args[0])
    if bp:
        try:
            count = int(args[1].strip())
        except:
            err = 'Error, please enter: ignore <bpnumber> <count>'
        else:
            bp.ignore = count
            if count > 0:
                reply = 'Will ignore next '
                if count > 1:
                    reply = reply + '%d crossings' % count
                else:
                    reply = reply + '1 crossing'
                print(reply + ' of breakpoint %d.' % bp.number)
            else:
                print('Will stop next time breakpoint', end=' ')
                print(bp.number, 'is reached.')
            return
    print('***', err)

def tty_fobj(ttyname):
    """Return the tty file object."""
    tty = None
    if ttyname and ttyname != os.devnull:
        if not os.path.exists(ttyname):
            critical('"%s" does not exist', ttyname)
        else:
            try:
                tty = open(ttyname, 'r+')
            except IOError as err:
                critical(err)
            else:
                if os.name == 'posix' and not os.isatty(tty.fileno()):
                    tty = None
                    critical('"%s" is not a tty.', ttyname)
    # fall back to '/dev/null'
    if not tty:
        try:
            tty = open(os.devnull, 'r+')
        except IOError as err:
            critical(err)
    return tty

class ShortRepr(_repr.Repr):
    """Minimum length object representation."""

    def __init__(self):
        """Constructor."""
        _repr.Repr.__init__(self)
        self.maxlevel = 2
        self.maxtuple = 2
        self.maxlist = 2
        self.maxarray = 2
        self.maxdict = 1
        self.maxset = 2
        self.maxfrozenset = 2
        self.maxdeque = 2
        self.maxstring = 20
        self.maxlong = 20
        self.maxother = 20

_saferepr = ShortRepr().repr

class BalloonRepr(_repr.Repr):
    """Balloon object representation."""

    def __init__(self):
        """Constructor."""
        _repr.Repr.__init__(self)
        self.maxlevel = 4
        self.maxtuple = 4
        self.maxlist = 4
        self.maxarray = 2
        self.maxdict = 2
        self.maxset = 4
        self.maxfrozenset = 4
        self.maxdeque = 4
        self.maxstring = 40
        self.maxlong = 40
        self.maxother = 40

_balloonrepr = BalloonRepr().repr

class Ping(asyncproc.FileAsynchat):
    """Terminate the select call in the asyncore loop."""
    def __init__(self, f, reader, map=None):
        """Constructor."""
        asyncproc.FileAsynchat.__init__(self, f, None, reader, map)

    def writable(self):
        """Do not monitor 'writable' select events."""
        return False

    def found_terminator(self):
        """Ignore received data."""
        self.ibuff = []

class Pdb(debugger.Debugger, pdb.Pdb):
    """The Pdb debugger.

    Instance attributes:
        frame_returning: frame
            set to the current frame when entering interaction on 'return'
        curframe_locals: dict
            cache the current frame locals
        thread: threading.Thread
            the clewn thread
        socket_map: dict
            map used in interaction
        stdout: StringIO instance
            stdout redirection
        ping_r, ping_w: file descriptors
            ping file descriptors
        stop_loop: boolean
            when True, stop the asyncore loop
        let_target_run: boolean
            when True, the target does not hang waiting for an established
            netbeans session
        trace_type: str
            trace type
        doprint_trace: boolean
            when True, print the stack entry
        clewn_thread_ident, target_thread_ident: int
            thread identifiers
        synchronisation_evt: Event
            used to synchronise both threads
        closing: boolean
            when True, terminate the clewn thread asyncore loop
        do_exit: boolean
            when True, run exit()
        poll: evtloop.Poll
            manage the select thread

    """

    def __init__(self, *args):
        """Constructor."""
        debugger.Debugger.__init__(self, *args)
        pdb.Pdb.__init__(self)

        # avoid pychecker warnings (not initialized in base class)
        self.curindex = 0
        self.lineno = None
        self.curframe = None
        self.stack = []
        self.frame_returning = None

        self.curframe_locals = None
        self.thread = None
        self.socket_map = {}
        self.stdout = io.StringIO()
        self.stop_loop = False
        self.let_target_run = False
        self.trace_type = ''
        self.doprint_trace = False
        self.clewn_thread_ident = 0
        self.target_thread_ident = 0
        self.synchronisation_evt = threading.Event()
        self.closing = False
        self.do_exit = False

        # the ping pipe is used to ping the clewn thread asyncore loop to enable
        # switching nbsock to the loop running in the main thread, in the
        # 'interaction' method
        ping_r, self.ping_w = os.pipe()
        Ping(ping_r, True)
        # a dummy Ping instance to avoid having 'self.socket_map' empty, when
        # outside the 'interaction' method (when using select emulation on
        # Windows)
        Ping(self.ping_w, False, map=self.socket_map)
        # instantiating 'poll' after addition of Ping to the 'socket_map'
        self.poll = evtloop.Poll(self.socket_map)

        self.cmds.update(PDB_CMDS)
        self.cmds['help'] = list(self.cmds.keys())
        self.mapkeys.update(MAPKEYS)

    def set_nbsock(self, nbsock):
        """Set the netbeans socket."""
        nbsock.lock = threading.Lock()
        debugger.Debugger.set_nbsock(self, nbsock)

    def _start(self):
        """Start the debugger."""
        info('starting a new netbeans session')
        debugger.Debugger._start(self)

        # restore the breakpoint signs
        for bp in bdb.Breakpoint.bpbynumber:
            if bp:
                self.add_bp(bp.number, bp.file, bp.line)
                if not bp.enabled:
                    self.update_bp(bp.number, True)

        self.do_prompt()

    def close(self):
        """Close the netbeans session."""
        # we do not really close the thread here, just netbeans
        debug('enter close')
        debugger.Debugger.close(self)
        self.let_target_run = True

    def do_prompt(self, timed=False):
        """Print the prompt in the Vim debugger console."""
        if self.stop_loop:
            self._prompt_str = '[running...] '
            if timed:
                self.get_console().timeout_append(self._prompt_str)
                return
        else:
            self._prompt_str = '(pdb) '
        self.print_prompt()

    def hilite_frame(self):
        """Highlite the frame sign."""
        frame, lineno = self.stack[self.curindex]
        filename = self.canonic(frame.f_code.co_filename)
        if filename == "<" + filename[1:-1] + ">":
            filename = None
        self.show_frame(filename, lineno)

    def frame_args(self, frame):
        """Return the frame arguments as a dictionary."""
        if frame is self.curframe:
            locals_ = self.curframe_locals
        else:
            locals_ = frame.f_locals
        args = OrderedDict()

        # see python source: Python/ceval.c
        co = frame.f_code
        n = co.co_argcount
        if co.co_flags & 4:
            n = n + 1
        if co.co_flags & 8:
            n = n + 1

        for i in range(n):
            name = co.co_varnames[i]
            if name in locals_:
                args[name] = locals_[name]
            else:
                args[name] = "*** undefined ***"
        return args

    def ping(self):
        """Ping the clewn thread asyncore loop."""
        self.synchronisation_evt.clear()
        try:
            os.write(self.ping_w, b'ping\n')
        except OSError as err:
            error('Cannot ping the clewn thread: %s.', err)
        else:
            self.synchronisation_evt.wait(1)
            if not self.synchronisation_evt.isSet():
                error('Cannot ping the clewn thread:'
                                ' \'synchronisation_evt\' not set.')

    def exit(self):
        """Terminate the clewn thread."""
        # clear the 'socket_map' to terminate the 'select_thread'
        self.socket_map.clear()
        self.poll.close()
        self.closing = True

    #-----------------------------------------------------------------------
    #   Bdb methods
    #-----------------------------------------------------------------------

    def trace_dispatch(self, frame, event, arg):
        """Hide the clewn part of the backtrace after a KeyboardInterrupt."""
        try:
            return pdb.Pdb.trace_dispatch(self, frame, event, arg)
        except KeyboardInterrupt:
            # hide bdb traceback to the user: prevent exception chaining
            raise KeyboardInterrupt() from KeyboardInterrupt()

    def dispatch_line(self, frame):
        """Override dispatch_line to set 'doprint_trace' when breaking."""
        dobreak_here = self.break_here(frame)
        if dobreak_here:
            self.doprint_trace = True
        if self.stop_here(frame) or dobreak_here:
            self.user_line(frame)
            if self.quitting: raise bdb.BdbQuit
        return self.trace_dispatch

    def dispatch_return(self, frame, arg):
        """Override 'dispatch_return' to fix issue 13183."""
        try:
            self.frame_returning = frame
            return pdb.Pdb.dispatch_return(self, frame, arg)
        finally:
            self.frame_returning = None

    def dispatch_exception(self, frame, arg):
        """Override to handle the exception before termination."""
        if self.stop_here(frame) or frame is self.botframe:
            self.user_exception(frame, arg)
            if self.quitting: raise bdb.BdbQuit
        return self.trace_dispatch

    def format_stack_entry(self, frame_lineno, lprefix=': '):
        """Override format_stack_entry: no line, add args, gdb format."""
        unused = lprefix
        frame, lineno = frame_lineno
        if frame.f_code.co_name:
            s = frame.f_code.co_name
        else:
            s = "<lambda>"

        args = self.frame_args(frame)
        s = s + '(' + ', '.join([a + '=' + _saferepr(v)
                            for a, v in args.items()]) + ')'

        if frame is self.curframe:
            locals_ = self.curframe_locals
        else:
            locals_ = frame.f_locals
        if '__return__' in locals_:
            rv = locals_['__return__']
            s = s + '->'
            s = s + _saferepr(rv)

        filename = self.canonic(frame.f_code.co_filename)
        s = s + ' at %s:%r' % (filename, lineno)
        return s

    def set_continue(self):
        """Override set_continue: the trace function is not removed."""
        self.stopframe = self.botframe
        self.stoplineno = -1
        self.returnframe = None
        self.quitting = 0

    def set_step(self):
        """Stop after one line of code."""
        # Issue #13183: pdb skips frames after hitting a breakpoint and running
        # step commands.
        # Restore the trace function in the caller (that may not have been set
        # for performance reasons) when returning from the current frame.
        if self.frame_returning:
            caller_frame = self.frame_returning.f_back
            if caller_frame and not caller_frame.f_trace:
                caller_frame.f_trace = self.trace_dispatch
        pdb.Pdb.set_step(self)

    def set_break(self, filename, lineno, temporary=0, cond=None,
                  funcname=None):
        """Override set_break to install a netbeans hook."""
        result = pdb.Pdb.set_break(self, filename, lineno, temporary, cond,
                                   funcname)
        if result is None:
            bp = self.get_breaks(filename, lineno)[-1]
            self.add_bp(bp.number, bp.file, bp.line)
        return result

    def clear_break(self, filename, lineno):
        """Override clear_break to install a netbeans hook."""
        bplist = []
        if (filename, lineno) in bdb.Breakpoint.bplist:
            bplist = [bp.number for bp in bdb.Breakpoint.bplist[filename, lineno]]

        result = pdb.Pdb.clear_break(self, filename, lineno)
        if result is None:
            for bpno in bplist:
                self.delete_bp(bpno)
            print('Deleted breakpoint(s): %r' % bplist)
        return result

    def clear_bpbynumber(self, arg):
        """Fix bug in standard library: clear _one_ breakpoint."""
        bp, err = breakpoint_by_number(arg)
        if bp:
            self.delete_bp(bp.number)
            bp.deleteMe()
            if (bp.file, bp.line) not in bdb.Breakpoint.bplist:
                self.breaks[bp.file].remove(bp.line)
            if not self.breaks[bp.file]:
                del self.breaks[bp.file]
        else:
            return err

    #-----------------------------------------------------------------------
    #   Pdb and Cmd methods
    #-----------------------------------------------------------------------

    def user_call(self, frame, argument_list):
        """This method is called when there is the remote possibility
        that we ever need to stop in this function."""
        unused = argument_list
        if self._wait_for_mainpyfile:
            return
        if self.stop_here(frame):
            self.trace_type = '--Call--'
            self.interaction(frame, None)

    def user_line(self, frame):
        """This function is called when we stop or break at this line."""
        if self._wait_for_mainpyfile:
            if (self.mainpyfile != self.canonic(frame.f_code.co_filename)
                or frame.f_lineno<= 0):
                return
            self._wait_for_mainpyfile = 0
            # hide the frames above mainpyfile
            self.botframe = frame
        # the 'bp_commands' method was introduced after python 2.4
        interact = True
        if hasattr(self, 'bp_commands'):
            interact = self.bp_commands(frame)
        if interact:
            self.interaction(frame, None)

    def user_return(self, frame, return_value):
        """This function is called when a return trap is set here."""
        frame.f_locals['__return__'] = return_value
        self.trace_type = '--Return--'
        self.interaction(frame, None)

    def user_exception(self, frame, exc_info):
        """This function is called if an exception occurs,
        but only if we are to stop at or just below this level."""
        (exc_type, exc_value, exc_traceback) = exc_info
        frame.f_locals['__exception__'] = exc_type, exc_value
        if isinstance(exc_type, type('')):
            exc_type_name = exc_type
        else: exc_type_name = exc_type.__name__
        self.trace_type = ('An exception occured: %s'
                        % repr((exc_type_name + ':', repr(exc_value))))
        self.interaction(frame, exc_traceback)

    def default(self, line):
        """Override 'default' to allow ':C import sys; sys.exit(0)'."""
        locals_ = self.curframe_locals
        globals_ = self.curframe.f_globals
        try:
            code = compile(line + '\n', '<stdin>', 'single')
            exec(code, globals_, locals_)
        except SystemExit:
            raise
        except:
            t, v = sys.exc_info()[:2]
            if isinstance(t, type('')):
                exc_type_name = t
            else: exc_type_name = t.__name__
            print('***', exc_type_name + ':', v)

    def print_stack_entry(self, frame_lineno, prompt_prefix=pdb.line_prefix):
        """Override print_stack_entry."""
        frame, unused = frame_lineno
        if frame is self.curframe:
            prefix = '> '
        else:
            prefix = '  '
        self.console_print('%s%s\n', prefix,
                    self.format_stack_entry(frame_lineno, prompt_prefix))

    def interaction(self, frame, traceback):
        """Handle user interaction in the asyncore loop."""
        # wait for the netbeans session to be established
        while not self.started or not self.stop_loop:
            if self.let_target_run:
                return
            time.sleep(debugger.LOOP_TIMEOUT)

        fd = self.set_nbsock_owner(self.target_thread_ident, self.socket_map)
        self.ping()
        # nbsock may have been closed by vim and the clewn thread
        # during the ping
        if fd is None or self.closed:
            del self.socket_map[fd]
            return

        self.setup(frame, traceback)
        if self.trace_type or self.doprint_trace:
            if self.get_console().timed_out:
                self.console_print('\n')
            if self.trace_type:
                self.console_print(self.trace_type + '\n')
            if traceback:
                self.print_stack_trace()
            else:
                self.print_stack_entry(self.stack[self.curindex])
        self.trace_type = ''
        self.doprint_trace = False

        self.hilite_frame()
        self.stop_loop = False
        self.do_prompt()

        try:
            while not self.stop_loop and self.started:
                try:
                    if self.cmdqueue:
                        self.do_line_cmd(self.cmdqueue.pop(0))
                    else:
                        self.poll.run(debugger.LOOP_TIMEOUT)
                except KeyboardInterrupt:
                    # ignore a KeyboardInterrupt to avoid breaking
                    # the debugging session
                    self.console_print('\nIgnoring a KeyboardInterrupt.\n')
                    self.do_prompt()
            self.show_frame()
            self.forget()
        finally:
            self.set_nbsock_owner(0)
            del self.socket_map[fd]
            self.ping()
            if self.do_exit:
                self.exit()

    #-----------------------------------------------------------------------
    #   commands
    #-----------------------------------------------------------------------

    def do_line_cmd(self, line):
        """Process a line as a command."""
        if line:
            cmd, args = (lambda a, b='': (a, b))(*line.split(None, 1))
            try:
                method = getattr(self, 'cmd_%s' % cmd)
            except AttributeError:
                method = self.default_cmd_processing
            self._do_cmd(method, cmd, args)

    def _do_cmd(self, method, cmd, args):
        """Process a command received from netbeans."""
        unused = method
        if args:
            cmd = '%s %s' % (cmd, args)
        debug(cmd)
        if not cmd:
            error('_do_cmd: processing an empty line')
            return

        # alias substitution
        line = self.precmd(cmd)
        self.console_print('%s\n', line)

        cmd, args = (lambda a, b='': (a, b))(*line.split(None, 1))
        if threading.currentThread() == self.thread:
            # restricted set of commands allowed in clewn thread
            if cmd not in CLEWN_CMDS:
                self.console_print('Target running, allowed commands'
                                        ' are: %s\n', str(CLEWN_CMDS))
            else:
                self.onecmd(line)
        else:
            if cmd == 'interrupt':
                self.console_print('The target is already interrupted.\n')
            else:
                self.onecmd(line)

        if cmd not in ('mapkeys', 'dumprepr', 'loglevel'):
            self.do_prompt(True)

    def onecmd(self, line):
        """Execute a command.

        Note that not all commands are valid at instantiation time, when reading
        '.pdbrc'.

        """
        if not line:
            return
        cmd, args = (lambda a, b='': (a, b))(*line.split(None, 1))
        try:
            method = getattr(self, 'cmd_%s' % cmd)
        except AttributeError:
            method = self.default_cmd_processing

        _stdout = sys.stdout
        sys.stdout = self.stdout
        try:
            method(cmd, args.strip())
        finally:
            sys.stdout = _stdout

        r = self.stdout.getvalue()
        if r:
            self.console_print(r)
            self.stdout = io.StringIO()

    def default_cmd_processing(self, cmd, args):
        """Process any command whose cmd_xxx method does not exist."""
        if args:
            cmd = '%s %s' % (cmd, args)
        # exec python statements
        self.default(cmd)

    def cmd_help(self, *args):
        """Print help on the pdb commands."""
        unused, cmd = args
        cmd = cmd.strip()
        allowed = list(PDB_CMDS.keys()) + ['mapkeys', 'unmapkeys', 'dumprepr',
                                                                    'loglevel']
        if not cmd:
            print("\nAvailable commands:")
            count = 0
            for item in sorted(allowed):
                count += 1
                if count % 7 == 0:
                    print(item)
                else:
                    print(item.ljust(11), end=' ')
            print('\n')
            print ("The empty command executes the (one-line) statement in the\n"
            "context of the current stack frame after alias expansion.\n"
            "The first word of the statement must not be a debugger\n"
            "command and may be an alias.\n"
            "Prefer using single quotes to double quotes as the later must\n"
            "be backslash escaped in Vim command line.\n"
            "To assign to a global variable you must always prefix the\n"
            "command with a 'global' command, e.g.:\n\n"
            ":C global list_options; list_options = ['-l']\n")
        elif cmd not in allowed:
            print('*** No help on', cmd)
        elif cmd == 'help':
            print ("h(elp)\n"
            "Without argument, print the list of available commands.\n"
            "With a command name as argument, print help about that command.")
        elif cmd in ('interrupt', 'detach', 'quit',
                     'mapkeys', 'unmapkeys', 'dumprepr',
                     'loglevel', 'threadstack',):
            method = getattr(self, 'cmd_%s' % cmd, None)
            if method is not None and method.__doc__ is not None:
                print(method.__doc__.split('\n')[0])
        else:
            self.do_help(cmd)
            if cmd == 'clear':
                print ('\nPyclewn does not support clearing all the'
                ' breakpoints when\nthe command is invoked without argument.')
            if cmd == 'alias':
                print ("When setting an alias from Vim command line, prefer\n"
                "using single quotes to double quotes as the later must be\n"
                "backslash escaped in Vim command line.\n"
                "For example, the previous example could be entered on Vim\n"
                "command line:\n\n"
                ":Calias pi for k in %1.__dict__.keys():"
                " print '%1.%s = %r' % (k, %1.__dict__[k])\n\n"
                "And the alias run with:\n\n"
                ":C pi some_instance\n")

    def cmd_break(self, cmd, args):
        """Set a breakpoint."""
        unused = cmd
        self.do_break(remove_quotes(args))

    def cmd_tbreak(self, cmd, args):
        """Set a temporary breakpoint."""
        unused = cmd
        self.do_break(remove_quotes(args), True)

    def cmd_enable(self, cmd, arg):
        """Enable breakpoints."""
        unused = cmd
        args = arg.split()
        for i in args:
            bp, err = breakpoint_by_number(i)
            if bp:
                bp.enable()
                self.update_bp(bp.number, False)
            else:
                print('***', err)

    def cmd_disable(self, cmd, arg):
        """Disable breakpoints."""
        unused = cmd
        args = arg.split()
        for i in args:
            bp, err = breakpoint_by_number(i)
            if bp:
                bp.disable()
                self.update_bp(bp.number, True)
            else:
                print('***', err)

    def cmd_condition(self, cmd, args):
        """Update the condition of a breakpoint."""
        unused = self
        unused = cmd
        update_condition(args)

    def cmd_ignore(self, cmd, args):
        """Sets the ignore count for the given breakpoint number."""
        unused = self
        unused = cmd
        update_ignore(args)

    def cmd_clear(self, cmd, args):
        """Clear breakpoints."""
        unused = cmd
        if not args:
            self.console_print(
                'An argument is required:\n'
                '   clear file:lineno -> clear all breaks at file:lineno\n'
                '   clear bpno bpno ... -> clear breakpoints by number\n')
            return
        self.do_clear(remove_quotes(args))

    def cmd_where(self, cmd, args):
        """Print a stack trace, with the most recent frame at the bottom."""
        unused = cmd
        self.do_where(args)

    cmd_bt = cmd_where

    def cmd_up(self, cmd, args):
        """Move the current frame one level up in the stack trace."""
        unused = cmd
        self.do_up(args)
        self.hilite_frame()

    def cmd_down(self, cmd, args):
        """Move the current frame one level down in the stack trace."""
        unused = cmd
        self.do_down(args)
        self.hilite_frame()

    def cmd_step(self, cmd, args):
        """Execute the current line, stop at the first possible occasion."""
        unused = cmd
        self.do_step(args)
        self.stop_loop = True

    def cmd_interrupt(self, cmd, args):
        """Interrupt the debuggee."""
        self.doprint_trace = True
        self.cmd_step(cmd, args)

    def cmd_next(self, cmd, args):
        """Continue execution until the next line in the current function."""
        unused = cmd
        self.do_next(args)
        self.stop_loop = True

    def cmd_return(self, cmd, args):
        """Continue execution until the current function returns."""
        unused = cmd
        self.do_return(args)
        self.stop_loop = True

    def cmd_continue(self, *args):
        """Continue execution."""
        unused = args
        self.set_continue()
        self.stop_loop = True

    def cmd_quit(self, *args):
        """Remove the python trace function and close the netbeans session."""
        unused = args
        self.clear_all_breaks()
        pdb.Pdb.set_continue(self)
        self.console_print('Python trace function removed.\n')

        # terminate the clewn thread in the run_pdb() loop
        self.console_print('Clewn thread terminated.\n')
        self.console_print('---\n\n')
        self.console_flush()
        self.netbeans_detach()
        self.do_exit = True
        self.stop_loop = True

    def cmd_jump(self, cmd, args):
        """Set the next line that will be executed."""
        unused = cmd
        self.do_jump(args)
        self.hilite_frame()

    def cmd_detach(self, *args):
        """Close the netbeans session."""
        unused = args
        self.console_print('Netbeans connection closed.\n')
        self.console_print('---\n\n')
        self.console_flush()
        self.netbeans_detach()
        self.stop_loop = True

    def cmd_args(self, *args):
        """Print the argument list of the current function."""
        fargs = self.frame_args(self.curframe)
        args = '\n'.join(name + ' = ' + repr(fargs[name]) for name in fargs)
        self.console_print(args + '\n')

    def cmd_p(self, cmd, args):
        """Evaluate the expression and print its value."""
        unused = cmd
        self.do_p(args)

    def cmd_pp(self, cmd, args):
        """Evaluate the expression and pretty print its value."""
        unused = cmd
        self.do_pp(args)

    def cmd_alias(self, cmd, args):
        """Create an alias called name that executes command."""
        unused = cmd
        self.do_alias(args)

    def cmd_unalias(self, cmd, args):
        """Deletes the specified alias."""
        unused = cmd
        self.do_unalias(args)

    def cmd_threadstack(self, *args):
        """Print a stack of the frames of all the threads."""
        unused = args
        if not hasattr(sys, '_current_frames'):
            self.console_print('Command not supported,'
                               ' upgrade to Python 2.5 at least.\n')
            return
        for thread_id, frame in sys._current_frames().items():
            try:
                if thread_id == self.clewn_thread_ident:
                    thread = 'Clewn-thread'
                elif thread_id == self.target_thread_ident:
                    thread = 'Debugged-thread'
                else:
                    thread = thread_id
                self.console_print('Thread: %s\n', thread)
                stack, unused = self.get_stack(frame, None)
                for frame_lineno in stack:
                    self.print_stack_entry(frame_lineno)
            except KeyboardInterrupt:
                pass

    #-----------------------------------------------------------------------
    #   netbeans events
    #-----------------------------------------------------------------------

    def balloon_text(self, arg):
        """Process a netbeans balloonText event."""
        debugger.Debugger.balloon_text(self, arg)
        if threading.currentThread() == self.thread:
            return

        try:
            value = eval(arg, self.curframe.f_globals, self.curframe_locals)
        except:
            t, v = sys.exc_info()[:2]
            if isinstance(t, str):
                exc_name = t
            else:
                exc_name = t.__name__
            self.show_balloon('*** (%s) %s: %s' % (arg, exc_name, repr(v)))
            return

        try:
            code = value.__code__
            self.show_balloon('(%s) Function: %s' % (arg, code.co_name))
            return
        except:
            pass

        try:
            code = value.__func__.__code__
            self.show_balloon('(%s) Method: %s' % (arg, code.co_name))
            return
        except:
            pass

        self.show_balloon('%s = %s' % (arg, _balloonrepr(value)))

def main(pdb, options):
    """Invoke the debuggee as a script."""
    argv = options.args
    if not argv:
        critical('usage: Pyclewn pdb scriptfile [arg] ...')
        sys.exit(1)

    sys.stdin = sys.stdout = sys.stderr = tty_fobj(options.tty)
    mainpyfile = argv[0]
    sys.path[0] = os.path.dirname(mainpyfile)
    sys.argv = argv
    try:
        pdb._runscript(mainpyfile)
    finally:
        pdb.console_print('Script "%s" terminated.\n\n' % mainpyfile)
        pdb.console_flush()

