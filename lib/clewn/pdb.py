# vi:set ts=8 sts=4 sw=4 et tw=80:
"""
The Pdb debugger.
"""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
try:
    import reprlib   # Python 3
except ImportError:
    import repr as reprlib   # Python 2
try:
    import queue  # Python 3
except ImportError:
    import Queue as queue   # Python 2
try:
    import StringIO
except ImportError:
    pass

import sys
import os
import threading
import time
import io
import signal
from collections import OrderedDict

from . import PY3, text_type, misc, debugger
from pdb_clone import __version__, pdb, bdb

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('pdb')

TIMEOUT = .100

HELP_EMPTY_CMD = (
"""The empty command executes the (one-line) statement in the context of the
current stack frame after alias expansion. The first word of the statement
must not be a debugger command and may be an alias. Prefer using single quotes
to double quotes as the later must be backslash escaped in Vim command line.
To assign to a global variable you must always prefix the command with a
'global' command, e.g.:

    C global list_options; list_options = ['-l']
""")

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
    'commands': (),
    'threadstack': (),
}

# list of key mappings, used to build the .pyclewn_keys.pdb file
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
    'C-K': ('clear "${fname}:${lnum}"',
                'clear breakpoint at current line'),
    'C-P': ('p ${text}',
                'print value of selection at mouse position'),
}

CLEWN_CMDS = ('interrupt', 'detach', 'threadstack', 'dumprepr')
STATE_INIT, STATE_RUN, STATE_DETACH, STATE_EXIT = range(4)

def remove_quotes(args):
    """Remove quotes from a string."""
    matchobj = misc.re_quoted.match(args)
    if matchobj:
        args = matchobj.group(1)
    return args

def tty_fobj(ttyname):
    """Return the tty stream object."""
    if not os.path.exists(ttyname):
        critical('terminal "%s" does not exist', ttyname)
        return

    fileio = io.FileIO(ttyname, 'w+')
    try:
        if PY3:
            tty = io.TextIOWrapper(fileio, line_buffering=True)
        else:
            tty = io.BufferedWriter(fileio, buffer_size=1)
    except IOError as err:
        critical('%s: %s', ttyname, err)
        raise
    else:
        if not os.isatty(fileio.fileno()):
            info('"%s" is not a tty.', fileio.name)
        return tty

def user_method_redirect(f):
    """user_method_redirect decorator."""
    def newf(self, *args, **kwds):
        """Decorated function."""
        self.message = self.set_trace_type
        f(self, *args, **kwds)
    return newf

class ShortRepr(reprlib.Repr):
    """Minimum length object representation."""

    def __init__(self):
        reprlib.Repr.__init__(self)
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

class BalloonRepr(reprlib.Repr):
    """Balloon object representation."""

    def __init__(self):
        reprlib.Repr.__init__(self)
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

class Pdb(debugger.Debugger, pdb.Pdb):
    """The Pdb debugger.

    Instance attributes:
        target_thread: threading.Thread
            the thread being debugged
        clewn_thread: threading.Thread
            the clewn thread
        target_queue: Queue
            queue of commands to be processed by the target thread
        in_interaction: bool
            True when the target thread is stopped in interaction()
        mouse_text: str
            the text that is being hovered to by the mouse
        stdout: StringIO instance
            stdout redirection
        stop_interaction: bool
            when True, stop the interaction loop
        let_target_run: bool
            when True, the target does not hang waiting for an established
            netbeans session
        trace_type: str
            trace type
        doprint_trace: bool
            when True, print the stack entry
        state: int
            pdb state
        interrupted: bool
            the interrupt command has been issued
        start_interrupted: bool
            the start interrupt has been issued
        attached: bool
            pdb is attached to a running process

    """

    def __init__(self, *args):
        debugger.Debugger.__init__(self, *args)
        pdb.Pdb.__init__(self, nosigint=False)

        # Avoid pychecker warnings (not initialized in base class).
        self.curindex = 0
        self.lineno = None
        self.curframe = None
        self.stack = []
        self.start_interrupted = False
        self.interrupted = False
        self.attached = True
        self.tty = None

        self.target_thread = None
        self.clewn_thread = None
        self.target_queue = queue.Queue()
        self.in_interaction = False
        self.mouse_text = ''
        self.stdout = io.StringIO() if PY3 else StringIO.StringIO()
        self.stop_interaction = False
        self.let_target_run = False
        self.trace_type = ''
        self.doprint_trace = False
        self._previous_sigint_handler = None
        self.state = STATE_INIT

        self.cmds.update(PDB_CMDS)
        self.pyclewn_cmds['inferiortty'] = ()
        self.cmds['help'] = list(self.cmds.keys())
        self.mapkeys.update(MAPKEYS)

    def set_nbsock(self, nbsock):
        """Set the netbeans socket."""
        nbsock.lock = threading.Lock()
        debugger.Debugger.set_nbsock(self, nbsock)

    def start(self):
        """Start the debugger."""
        info('starting a new netbeans session')
        mode = 'with' if bdb._bdb else 'without'
        self.console_print('pdb-clone {} ({} the _bdb extension module).\n\n'
                                                .format(__version__, mode))
        # restore the breakpoint signs
        for bp in bdb.Breakpoint.bpbynumber:
            if bp:
                self.add_bp(bp.number, bp.file, bp.line)
                if not bp.enabled:
                    self.update_bp(bp.number, True)

        self.print_prompt()

    def close(self):
        """Close the netbeans session."""
        # We do not really close the thread here, just netbeans.
        info('enter Pdb.close')
        debugger.Debugger.close(self)
        self.let_target_run = True
        self.set_continue()

    def print_prompt(self, timed=False):
        """Print the prompt in the Vim debugger console."""
        if self.stop_interaction:
            self.prompt = '[running...] '
        else:
            self.prompt = '(Pdb) '
            # Do not flush on timeout when running the test suite.
            if self.vim.testrun:
                debugger.Debugger.print_prompt(self)
                return
        if timed:
            self.get_console().timeout_append(self.prompt)
        else:
            debugger.Debugger.print_prompt(self)

    def hilite_frame(self):
        """Highlite the frame sign."""
        frame, lineno = self.stack[self.curindex]
        filename = self.canonic(frame.f_code.co_filename)
        if not PY3:
            filename = unicode(filename)
        if filename == "<" + filename[1:-1] + ">":
            filename = None
        self.show_frame(filename, lineno)

    def frame_args(self, frame):
        """Return the frame arguments as a dictionary."""
        locals_ = self.get_locals(frame)
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

    def detach(self):
        """Detach the netbeans connection."""
        self.console_print('Netbeans connection closed.\n')
        self.console_print('---\n\n')
        self.console_flush()
        self.netbeans_detach()

    def exit(self):
        """Terminate the clewn thread."""
        info('terminating the clewn thread')
        if self._previous_sigint_handler:
            signal.signal(signal.SIGINT, self._previous_sigint_handler)
            self._previous_sigint_handler = None

        if self.tty:
            self.tty.close()

        self.vim.loop.call_soon_threadsafe(self.vim.signal, None)

    #-----------------------------------------------------------------------
    #   Bdb methods
    #-----------------------------------------------------------------------

    def format_stack_entry(self, frame_lineno, lprefix=': '):
        """Override format_stack_entry: no line, add args, gdb format."""
        frame, lineno = frame_lineno
        if frame.f_code.co_name:
            s = frame.f_code.co_name
        else:
            s = "<lambda>"

        args = self.frame_args(frame)
        s = s + '(' + ', '.join([a + '=' + _saferepr(v)
                            for a, v in args.items()]) + ')'

        locals_ = self.get_locals(frame)
        if '__return__' in locals_:
            rv = locals_['__return__']
            s = s + '->'
            s = s + _saferepr(rv)

        filename = self.canonic(frame.f_code.co_filename)
        s = s + ' at %s:%r' % (filename, lineno)
        return s

    def set_break(self, filename, lineno, temporary=False, cond=None,
                  funcname=None):
        """Override set_break to install a netbeans hook."""
        bp = pdb.Pdb.set_break(self, filename, lineno, temporary, cond,
                                                               funcname)
        if bp:
            filename = bp.file if PY3 else unicode(bp.file)
            self.add_bp(bp.number, filename, bp.line)
            return bp

    #-----------------------------------------------------------------------
    #   Pdb and Cmd methods
    #-----------------------------------------------------------------------

    def message(self, *args, **kwds):
        """Allow 'end' keyword in message method."""
        args = tuple(str(x) for x in args)
        print(*args, file=self.stdout, **kwds)

    def error(self, msg):
        print(str('***'), str(msg), file=self.stdout)

    # Use 'console_print' for all messages printed outside the 'onecmd' method,
    # (onecmd executes pdb commands, as opposed to pyclewn commands).  Otherwise
    # use 'message'.
    onecmd_message = message

    def set_trace_type(self, msg):
        """trace_type setter."""
        self.trace_type = msg

    @user_method_redirect
    def user_call(self, frame, argument_list):
        """This method is called when there is the remote possibility
        that we ever need to stop in this function."""
        pdb.Pdb.user_call(self, frame, argument_list)

    @user_method_redirect
    def user_line(self, frame, breakpoint_hits=None):
        """Override user_line to set 'doprint_trace' when breaking."""
        if breakpoint_hits:
            self.doprint_trace = True
            commands_result = self.bp_commands(frame, breakpoint_hits)
            if commands_result:
                self.stop_interaction = False
                self.doprint_trace = False
                doprompt, silent = commands_result
                if not silent:
                    self.print_stack_entry(self.stack[self.curindex])
                self.forget()
                if not doprompt:
                    return
        self.interaction(frame, None)

    @user_method_redirect
    def user_return(self, frame, return_value):
        """This function is called when a return trap is set here."""
        pdb.Pdb.user_return(self, frame, return_value)

    @user_method_redirect
    def user_exception(self, frame, exc_info):
        """This function is called if an exception occurs."""
        pdb.Pdb.user_exception(self, frame, exc_info)

    def cmdloop(self):
        """Command loop used in pyclewn, only to define breakpoint commands."""
        while not self.stop_interaction and self.started:
            # Commands queued after the ';;' separator.
            if self.cmdqueue:
                self.onecmd(self.cmdqueue.pop(0))
            else:
                try:
                    line = self.target_queue.get(block=True, timeout=TIMEOUT)
                except queue.Empty:
                    pass
                else:
                    self.onecmd(line)
        self.stop_interaction = False

    def print_stack_entry(self, frame_lineno, prompt_prefix=pdb.line_prefix):
        """Override print_stack_entry."""
        frame, _ = frame_lineno
        if frame is self.curframe:
            prefix = '> '
        else:
            prefix = '  '
        self.console_print('%s%s\n', prefix,
                    self.format_stack_entry(frame_lineno, prompt_prefix))

    def sigint_handler(self, signum, frame):
        """Override sigint_handler."""
        if self.allow_kbdint:
            raise KeyboardInterrupt
        self.console_print("Program interrupted. (Use 'cont' to resume).\n")
        self.doprint_trace = True
        self.set_trace(frame)

    def interaction(self, frame, traceback, post_mortem=False):
        """Handle user interaction in the target thread."""
        # Sleep a while to prevent both threads sending netbeans commands
        # simultaneously which would swap around the Vim windows in an
        # inconsistent way.
        if self.interrupted:
            self.interrupted = False
            time.sleep(1)

        # Wait for the netbeans session to be established.
        while not self.started or self.state == STATE_INIT:
            if self.let_target_run:
                # After having been detached, the first <Ctl-C> restores the
                # initial (default) signal handler and sets the trace function.
                # So, the debuggee can be killed with the next <Ctl-C>, while
                # still being allowed to be interrupted from the clewn thread at
                # a call debug event since the trace function is set.
                if self._previous_sigint_handler:
                    signal.signal(signal.SIGINT, self._previous_sigint_handler)
                    self._previous_sigint_handler = None
                return
            time.sleep(TIMEOUT)

        if self.start_interrupted:
            self.start_interrupted = False
            # Do not set the trace function in post mortem debugging, as
            # interaction() is not called from the trace function
            # trace_dispatch() then.
            if not post_mortem:
                self.set_trace(frame)

        if not self.nosigint and not self._previous_sigint_handler:
            self._previous_sigint_handler = signal.signal(signal.SIGINT,
                                                    self.sigint_handler)

        if self.setup(frame, traceback):
            # No interaction desired at this time (happens if .pdbrc contains a
            # command like "continue").
            self.stop_interaction = False
            self.forget()
            return

        if self.trace_type or self.doprint_trace:
            if self.get_console().timed_out:
                self.console_print('\n')
            if self.trace_type:
                self.console_print(self.trace_type + '\n')
            if self.doprint_trace or traceback:
                self.print_stack_entry(self.stack[self.curindex])
        self.trace_type = ''
        self.doprint_trace = False

        self.hilite_frame()
        self.print_prompt()
        assert not self.stop_interaction
        try:
            self.in_interaction = True
            self.mouse_text = ''
            while not self.stop_interaction and self.started:
                if self.state == STATE_DETACH:
                    self.set_continue()
                    break

                try:
                    self.allow_kbdint = True
                    # Commands queued after the ';;' separator.
                    if self.cmdqueue:
                        self.onecmd(self.cmdqueue.pop(0))
                    elif self.mouse_text:
                        self.balloon_text(self.mouse_text)
                        self.mouse_text = ''
                    else:
                        try:
                            line = self.target_queue.get(block=True,
                                                         timeout=TIMEOUT)
                        except queue.Empty:
                            pass
                        else:
                            self.onecmd(line)
                except KeyboardInterrupt:
                    self.console_print('--KeyboardInterrupt--\n')
                    self.print_prompt()
                finally:
                    self.allow_kbdint = False
            self.stop_interaction = False
            self.show_frame()
            self.forget()
        finally:
            self.in_interaction = False

        if not self.attached and not self.started:
            info('terminate the debuggee started from Vim')
            raise bdb.BdbQuit

        if self.state != STATE_RUN:
            self.detach()
            if self.state == STATE_EXIT:
                self.exit()
            self.state = STATE_INIT

    #-----------------------------------------------------------------------
    #   commands
    #-----------------------------------------------------------------------

    def onecmd(self, line):
        """Process a line as a command.

        The clewn thread queues the command when it must be run by the target
        thread. The target thread executes the command. This method may also be
        called from the target thread when parsing .pdbrc or executing
        breakpoint commands.
        """
        debug('onecmd [%s]: %s', threading.currentThread().name, line)
        if not line:
            return False

        # Alias substitution.
        if threading.currentThread() != self.clewn_thread:
            line = self.precmd(line)

        cmd, args = (lambda a, b='': (a, b))(*line.split(None, 1))
        try:
            method = getattr(self, 'cmd_%s' % cmd)
        except AttributeError:
            method = self.default_cmd_processing

        if threading.currentThread() == self.clewn_thread:
            # The debugger.inferiortty() method must be invoked from the clewn
            # thread.
            if self.in_interaction and method != self.cmd_inferiortty:
                self.target_queue.put(line)
                return
        elif self.commands_defining:
            if line == 'interrupt':
                raise KeyboardInterrupt
            if self.handle_command_def(line):
                self.stop_interaction = True
            else:
                debugger.Debugger.print_prompt(self)
            return self.stop_interaction

        # restricted set of commands allowed in clewn thread
        if (threading.currentThread() == self.clewn_thread and
                not (cmd in CLEWN_CMDS or
                    (self.in_interaction and method == self.cmd_inferiortty))):
            self.console_print('Target running, allowed commands'
                           ' are: %s\n', tuple(str(cmd) for cmd in CLEWN_CMDS))
        else:
            self.message = self.onecmd_message
            method(cmd, args.strip())
            r = self.stdout.getvalue()
            if r:
                if not PY3:
                    r = unicode(r)
                self.console_print(r)
                self.stdout = io.StringIO() if PY3 else StringIO.StringIO()

        if cmd not in ('mapkeys', 'dumprepr', 'loglevel'):
            # A timed printout, printed  by the background task when it flushes
            # the console 500 msecs msecs after the print_prompt call, unless a
            # new console_print call wipes out the prompt mean time, see
            # netbeans.Console.
            self.print_prompt(True)

        return self.stop_interaction

    def _do_cmd(self, method, cmd, args):
        """Override to handle alias substitution."""
        if args:
            cmd = '%s %s' % (cmd, args)
        self.console_print('%s\n', cmd)
        self.onecmd(cmd)

    def default_cmd_processing(self, cmd, args):
        """Process any command whose cmd_xxx method does not exist."""
        if args:
            cmd = '%s %s' % (cmd, args)
        # exec python statements
        self.default(cmd)

    def cmd_inferiortty(self, cmd, args):
        """Spawn pdb inferior terminal and setup pdb with this terminal."""
        def set_inferior_tty_cb(line, ttyname=None):
            if not ttyname:
                if not line.startswith('set inferior-tty'):
                    return
                ttyname = line.split()[2]
            if self.tty:
                self.tty.close()
                self.tty = None
            self.tty = tty_fobj(ttyname)
            if self.tty:
                sys.stdin = sys.stdout = sys.stderr = self.tty
                info('set inferior tty to %s', ttyname)
                self.console_print('inferiortty %s\n' % ttyname)

        if not args:
            self.inferiortty(set_inferior_tty_cb)
        else:
            set_inferior_tty_cb('', ttyname=args)

    for n in ('enable', 'disable', 'condition', 'ignore', 'where',
                                'bt', 'p', 'pp', 'alias', 'unalias'):
        exec('def cmd_%s(self, cmd, args): return self.do_%s(args)' % (n, n))

    def cmd_help(self, *args):
        """Print help on the pdb commands."""
        _, cmd = args
        cmd = cmd.strip()
        allowed = list(PDB_CMDS.keys()) + ['mapkeys', 'unmapkeys', 'dumprepr',
                                           'loglevel', 'exitclewn']
        if not cmd:
            self.message("Available commands (typing in Vim ':C<CTRL-D>'"
                         " prints this same list):")
            count = 0
            for item in sorted(allowed):
                count += 1
                if count % 7 == 0:
                    self.message(item)
                else:
                    self.message(item.ljust(11), end=' ')
            self.message('\n')
            self.message(HELP_EMPTY_CMD)
        elif cmd not in allowed:
            self.message('*** No help on', cmd)
        elif cmd == 'help':
            self.message("h(elp)\n"
            "Without argument, print the list of available commands.\n"
            "With a command name as argument, print help about that command.")
        elif cmd in ('interrupt', 'detach', 'quit',
                     'mapkeys', 'unmapkeys', 'dumprepr',
                     'loglevel', 'exitclewn', 'threadstack',):
            method = getattr(self, 'cmd_%s' % cmd, None)
            if method is not None and method.__doc__ is not None:
                self.message(method.__doc__.split('\n')[0])
        else:
            self.do_help(cmd)
            if cmd == 'clear':
                self.message('\nPyclewn does not support clearing all the'
                ' breakpoints when\nthe command is invoked without argument.')
            if cmd == 'alias':
                self.message(
                "\nWhen setting an alias from Vim command line, prefer\n"
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
        self.do_break(remove_quotes(args))

    def cmd_tbreak(self, cmd, args):
        """Set a temporary breakpoint."""
        self.do_break(remove_quotes(args), True)

    def done_breakpoint_state(self, bp, state):
        """Override done_breakpoint_state to update breakpoint sign."""
        pdb.Pdb.done_breakpoint_state(self, bp, state)
        self.update_bp(bp.number, not state)

    def done_delete_breakpoint(self, bp):
        """Override done_delete_breakpoint to clear the breakpoint sign."""
        pdb.Pdb.done_delete_breakpoint(self, bp)
        self.delete_bp(bp.number)

    def cmd_clear(self, cmd, args):
        """Clear breakpoints."""
        if not args:
            self.message(
                'An argument is required:\n'
                '   clear file:lineno -> clear all breaks at file:lineno\n'
                '   clear bpno bpno ... -> clear breakpoints by number')
            return
        self.do_clear(remove_quotes(args))

    def cmd_up(self, cmd, args):
        """Move the current frame one level up in the stack trace."""
        self.do_up(args)
        self.hilite_frame()

    def cmd_down(self, cmd, args):
        """Move the current frame one level down in the stack trace."""
        self.do_down(args)
        self.hilite_frame()

    def cmd_step(self, cmd, args):
        """Execute the current line, stop at the first possible occasion."""
        self.do_step(args)
        self.stop_interaction = True

    def cmd_interrupt(self, cmd, args):
        """Interrupt the debuggee."""
        if self.state == STATE_INIT:
            self.state = STATE_RUN

        # A debugging session always start with an interrupt (sent from Vim
        # pyclewn.vim startup script) and the interrupt of the first debugging
        # session is a soft interrupt (does not use SIGINT), the signal handler
        # being only set in the ensuing interaction.
        if self._previous_sigint_handler:
            os.kill(os.getpid(), signal.SIGINT)
            self.interrupted = True
        else:
            # This supposes that the trace function has not been removed so that
            # we can enter interaction on a call debug event (because of the
            # call to set_step).
            self.start_interrupted = True
            self.doprint_trace = True
            self.set_step()

    def cmd_next(self, cmd, args):
        """Continue execution until the next line in the current function."""
        self.do_next(args)
        self.stop_interaction = True

    def cmd_return(self, cmd, args):
        """Continue execution until the current function returns."""
        self.do_return(args)
        self.stop_interaction = True

    def cmd_continue(self, *args):
        """Continue execution."""
        self.set_continue()
        self.stop_interaction = True

    def cmd_quit(self, *args):
        """Remove the python trace function and close the netbeans session."""
        self.console_print('Python trace function removed.\n')
        if self.attached:
            self.clear_all_breaks()
            self.set_continue()
        else:
            self.console_print('Script "%s" terminated.\n' % self.mainpyfile)
            # This will raise BdbQuit and termine the script.
            self.set_quit()

        # Terminate the clewn thread in the run_pdb() loop.
        self.console_print('Clewn thread terminated.\n')
        self.state = STATE_EXIT
        self.stop_interaction = True

    def cmd_jump(self, cmd, args):
        """Set the next line that will be executed."""
        self.do_jump(args)
        self.hilite_frame()

    def cmd_detach(self, *args):
        """Close the netbeans session."""
        if not self.attached:
            self.console_print('Cannot detach, the debuggee is not attached.\n')
            return
        self.state = STATE_DETACH
        if threading.currentThread() == self.clewn_thread:
            self.cmd_interrupt(*args)

    def cmd_args(self, *args):
        """Print the argument list of the current function."""
        fargs = self.frame_args(self.curframe)
        args = '\n'.join(name + ' = ' + repr(fargs[name]) for name in fargs)
        self.message(args)

    def cmd_threadstack(self, *args):
        """Print a stack of the frames of all the threads."""
        if not hasattr(sys, '_current_frames'):
            self.console_print('Command not supported,'
                               ' upgrade to Python 2.5 at least.\n')
            return
        for thread_id, frame in sys._current_frames().items():
            try:
                if thread_id == self.clewn_thread.ident:
                    thread = 'Clewn-thread'
                elif thread_id == self.target_thread.ident:
                    thread = 'Debugged-thread'
                else:
                    thread = thread_id
                self.console_print('Thread: %s\n', thread)
                stack, _ = self.get_stack(frame, None)
                for frame_lineno in stack:
                    self.print_stack_entry(frame_lineno)
            except KeyboardInterrupt:
                pass

    def cmd_commands(self, cmd, args):
        """Enter breakpoint commands."""
        self.console_print(
            'Type the commands to be executed when this breakpoint is hit:\n'
            'In Vim command line, type the "C" prefix, followed by a space'
            ' and the command.\n'
            'End with a line saying just "C end".\n'
            )
        self.prompt = '(com) '
        debugger.Debugger.print_prompt(self)
        return self.do_commands(args)

    #-----------------------------------------------------------------------
    #   netbeans events
    #-----------------------------------------------------------------------

    def balloon_text(self, arg):
        """Process a netbeans balloonText event."""
        if threading.currentThread() == self.clewn_thread:
            debugger.Debugger.balloon_text(self, arg)
            if self.in_interaction:
                self.mouse_text = arg
            return

        try:
            value = eval(arg, self.curframe.f_globals,
                            self.get_locals(self.curframe))
        except Exception:
            t, v = sys.exc_info()[:2]
            if isinstance(t, text_type):
                exc_name = t
            else:
                exc_name = t.__name__
            self.show_balloon('*** (%s) %s: %s' % (arg, exc_name, repr(v)))
            return

        try:
            code = value.__code__
            self.show_balloon('(%s) Function: %s' % (arg, code.co_name))
            return
        except Exception:
            pass

        try:
            code = value.__func__.__code__
            self.show_balloon('(%s) Method: %s' % (arg, code.co_name))
            return
        except Exception:
            pass

        self.show_balloon('%s = %s' % (arg, _balloonrepr(value)))

def runscript(pdbinst, options):
    """Invoke the debuggee as a script."""
    argv = options.args
    if not argv:
        critical('usage: Pyclewn pdb scriptfile [arg] ...')
        sys.exit(1)

    mainpyfile = argv[0]
    if not os.path.exists(mainpyfile):
        critical('file "%s" does not exist', mainpyfile)
        sys.exit(1)

    tty = tty_fobj(options.tty)
    if tty:
        info('set inferior tty to %s', tty.name)
        sys.stdin = sys.stdout = sys.stderr = tty
    sys.path[0] = os.path.dirname(mainpyfile)
    sys.argv = argv
    try:
        pdbinst.attached = False
        pdbinst._runscript(mainpyfile)
    except Exception as e:
        trace_type = 'Uncaught exception:\n    %r\n' %e
        trace_type += 'Entering post mortem debugging.'
        pdbinst.trace_type = trace_type
        t = sys.exc_info()[2]
        pdbinst.interaction(None, t, True)
    finally:
        if tty:
            tty.close()
        pdbinst.console_print('Script "%s" terminated.\n' % mainpyfile)
        pdbinst.console_print('---\n\n')
        pdbinst.console_flush()

