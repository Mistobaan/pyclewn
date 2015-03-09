# vi:set ts=8 sts=4 sw=4 et tw=80:
"""
A Vim instance instantiates a Debugger and controls the netbeans socket.
"""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import sys
import asyncio
import functools
import importlib
import subprocess
import traceback
import optparse
import logging
import errno
import threading
import atexit
import platform
import tempfile

from . import (__version__, ClewnError, misc, netbeans, tty,
               gdb, debugger)
from .process import daemonize

WINDOW_LOCATION = ('top', 'bottom', 'left', 'right', 'none')
CONNECTION_DEFAULTS =  {
        'gdb':      ('127.0.0.1', 3219, 'changeme'),
        'pdb':      ('127.0.0.1', 3220, 'changeme'),
        'simple':   ('127.0.0.1', 3221, 'changeme'),
    }
CONNECTION_TIMEOUT = 30
CONNECTION_ERROR = """Connection to Vim timed out after %s seconds.
Please check that the netbeans_intg feature is compiled
in your Vim version by running the Vim command ':version',
and checking that this command displays '+netbeans_intg'."""

BG_COLORS =( 'Black', 'DarkBlue', 'DarkGreen', 'DarkCyan', 'DarkRed',
             'DarkMagenta', 'Brown', 'DarkYellow', 'LightGray', 'LightGrey',
             'Gray', 'Grey', 'DarkGray', 'DarkGrey', 'Blue', 'LightBlue',
             'Green', 'LightGreen', 'Cyan', 'LightCyan', 'Red', 'LightRed',
             'Magenta', 'LightMagenta', 'Yellow', 'LightYellow', 'White',)

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('vim')

def connection_timeout():
    raise IOError(CONNECTION_ERROR % str(CONNECTION_TIMEOUT))

def exec_vimcmd(commands, editor='', error_stream=None):
    """Run a list of Vim 'commands' and return the commands output."""
    try:
        perror = error_stream.write
    except AttributeError:
        perror = sys.stderr.write

    if not editor:
        editor = os.environ.get('EDITOR', 'gvim')

    args = [editor, '-u', 'NONE', '-esX', '-c', 'set cpo&vim']
    fd, tmpname = tempfile.mkstemp(prefix='vimcmd', suffix='.clewn')
    commands.insert(0,  'redir! >%s' % tmpname)
    commands.append('quit')
    for cmd in commands:
        args.extend(['-c', cmd])

    output = f = None
    try:
        try:
            subprocess.Popen(args).wait()
            f = os.fdopen(fd)
            output = f.read()
        except (OSError, IOError) as err:
            if isinstance(err, OSError) and err.errno == errno.ENOENT:
                perror("Failed to run '%s' as Vim.\n" % args[0])
                perror("Please set the EDITOR environment variable or run "
                                "'pyclewn --editor=/path/to/(g)vim'.\n\n")
            else:
                perror("Failed to run Vim as:\n'%s'\n\n" % str(args))
                perror("Error; %s\n", err)
            raise
    finally:
        if f is not None:
            f.close()
        try:
            os.unlink(tmpname)
        except OSError:
            pass

    if not output:
        raise ClewnError(
            "Error trying to start Vim with the following command:\n'%s'\n"
            % ' '.join(args))

    return output

def pformat(name, obj):
    """Pretty format an object __dict__."""
    if obj:
        return '%s:\n%s\n' % (name, misc.pformat(obj.__dict__))
    else: return ''

def close_clewnthread(vim):
    """Terminate the clewn thread and stop the debugger."""
    try:
        info('enter close_clewnthread')
        sys.settrace(None)

        # Notify 'Clewn-thread' of pending termination.
        if not vim.closed:
            pdbinst = vim.debugger
            if threading.currentThread() != pdbinst.clewn_thread:
                pdbinst.exit()
                pdbinst.clewn_thread.join()
            debug('Vim instance: ' + str(vim))
            vim.shutdown()
    except KeyboardInterrupt:
        close_clewnthread(vim)

def embed_pdb(vim, attach=False):
    """Start the python debugger thread."""
    # Use a daemon thread.
    class ClewnThread(threading.Thread):
        def __init__(self):
            threading.Thread.__init__(self, name='ClewnThread')
            self.setDaemon(True)
        def run(self):
            if vim.testrun:
                # Synchronisation with the test runner.
                print('Started.', file=sys.stderr)
                sys.stderr.flush()
            loop = vim.set_event_loop()
            loop.run_until_complete(vim.pdb_run(clewn_thread_ready))
            close_clewnthread(vim)

    clewn_thread = ClewnThread()
    module = vim.setup()
    pdbinst = vim.debugger
    pdbinst.target_thread = threading.currentThread()
    pdbinst.clewn_thread = clewn_thread

    clewn_thread_ready = threading.Event()
    clewn_thread.start()
    clewn_thread_ready.wait(1)
    if not clewn_thread_ready.isSet():
        print('Aborting, failed to start the clewn thread.', file=sys.stderr)
        sys.exit(1)

    Vim.pdb_running = True
    atexit.register(close_clewnthread, vim)

    if attach:
        if vim.options.run:
            pdbinst.let_target_run = True
        pdbinst.set_trace(sys._getframe(2))
    else:
        runscript = getattr(module, 'runscript')
        runscript(pdbinst, vim.options)

def pdb(run=False, **kwds):
    """Start pdb from within a python process.

    The 'kwds' keyword arguments may be any of the pyclewn options that set a
    value (no boolean option allowed).
    """
    if Vim.pdb_running:
        return

    argv = []
    if run:
        argv.append('--run')
    argv.extend(['--' + k + '=' + str(v)
                 for k, v in kwds.items()
                 if k != 'testrun'
                ])
    argv.append('pdb')
    testrun = 'testrun' in kwds
    embed_pdb(Vim(testrun, argv), attach=True)

def main(testrun=False):
    """Main.

    Return the vim instance to avoid its 'f_script' member to be garbage
    collected and the corresponding 'TmpFile' to be unlinked before Vim has a
    chance to start and source the file (only needed for the pdb test suite).

    """
    vim = Vim(testrun, sys.argv[1:])
    options = vim.options
    is_pdb = (vim.module == 'pdb')

    try:
        # Vim is running the command ':Pyclewn pdb script'.
        if is_pdb and not testrun and options.args:
            embed_pdb(vim)
            return vim

        vim.set_event_loop()
        vim.setup()

        # When is_pdb is True, this is either:
        #   * Vim is being spawned by the test suite.
        #   * or the user is running the Vim command ':Pyclewn pdb'
        if is_pdb:
            if not testrun and not options.cargs:
                critical('This command is meant to be run from Vim.')
            return

        vim_tasks = []
        # Use pyclewn terminal as the inferior standard input/output when vim is
        # run as 'gvim'.
        if (options.editor and vim.module == 'gdb' and not testrun and
                    os.isatty(sys.stdin.fileno()) and not options.daemon):
            out = exec_vimcmd(['echo has("gui_running")'],
                                 options.editor, vim.stderr_hdlr).strip()
            if out == '1':
                tasks, ptyname = tty.inferior_tty(vim.stderr_hdlr, vim.loop)
                options.tty = ptyname
                vim_tasks.extend(tasks)

        vim_tasks.append(asyncio.Task(vim.run(), loop=vim.loop))
        misc.cancel_after_first_completed(vim_tasks, lambda: vim.signal(None),
                                          loop=vim.loop)

    except Exception as e:
        except_str = 'Exception in pyclewn: "%s"\n' \
                     '%s\n'                         \
                     'pyclewn aborting...\n'        \
                            % (e, traceback.format_tb(sys.exc_info()[2])[-1])
        critical('\n' + except_str)
        if vim.netbeans:
            vim.netbeans.show_balloon(except_str)
        if not testrun:
            sys.exit(1)
    finally:
        debug('Vim instance: ' + str(vim))
        vim.shutdown()

    return vim

class Vim(object):
    """The Vim class."""

    pdb_running = False

    def __init__(self, testrun, argv):
        self.testrun = testrun
        self.file_hdlr = None
        self.stderr_hdlr = None
        self.clazz = None
        self.module = None
        self.f_script = None
        self.vim_process = None
        self.options = None
        self.closed = False
        self.parse_options(argv)

        self.debugger = None
        self.nbserver = None
        self.netbeans = None
        self.loglevel = None
        self.loop = None
        self.setlogger()
        self.events = None

    def set_event_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.events = asyncio.Queue(loop=self.loop)
        self.set_exception_handler()
        if self.loglevel is not None and self.loglevel <= logging.DEBUG:
            self.loop.set_debug(True)
        return self.loop

    def vim_version(self):
        """Check Vim version."""
        # test if Vim contains the netbeans 'remove' fix
        # test if Vim contains the netbeans 'getLength' fix
        # test if Vim contains the netbeans 'cmd on NoName buffer ignored' fix

        # pyclewn is started from within vim.
        # This is supported since vim73. When using 'pdb', pyclewn has no way
        # to know which vim it is connected to, unless using the netbeans
        # version, but this does not change consistently with vim netbeans
        # patches.
        if not self.options.editor:
            netbeans.Netbeans.remove_fix = '1'
            netbeans.Netbeans.getLength_fix = '1'
            self.options.noname_fix = '1'
            return

        cmds = ['echo v:version > 701 || v:version == 701 && has("patch207")',
                'echo v:version > 702 || v:version == 702 && has("patch253")',
                'echo v:version > 702 || v:version == 702 && has("patch334")',
                'echo v:version',
                ]
        output = exec_vimcmd(cmds, self.options.editor,
                                   self.stderr_hdlr).strip().split('\n')
        output = [x.strip('\r') for x in output]
        length = len(output)
        if length == 4:
            (netbeans.Netbeans.remove_fix,
             netbeans.Netbeans.getLength_fix,
             self.options.noname_fix,
             vimver) = output
        else:
            raise ClewnError('output of %s: %s' % (cmds, output))
        info('Vim version: %s', vimver)

    def spawn_vim(self):
        """Spawn vim."""
        args = self.options.cargs or []
        self.f_script = self.debugger.vim_script()
        info('sourcing the Vim script file: %s', self.f_script.name)
        args[:0] = [self.f_script.name]
        args[:0] = ['-S']
        args[:0] = ['-nb:%s' % ':'.join(self.connection)]
        args[:0] = [self.options.editor]

        # Uncomment next lines to run Valgrind on Vim.
        # args[:0] = ["--leak-check=yes"]
        # args[:0] = ["valgrind"]

        info('Vim argv list: %s', str(args))
        try:
            self.vim_process = subprocess.Popen(args, close_fds=True)
        except OSError:
            critical('cannot start Vim'); raise

    def setup(self):
        info('platform: %s', platform.platform())
        info('Python version: %s', ' '.join(sys.version.split('\n')))

        # Get the connection parameters.
        connection_defaults = CONNECTION_DEFAULTS[self.module]
        conn = list(connection_defaults)
        if self.options.netbeans:
            conn = self.options.netbeans.split(':')
            conn[1:] = conn[1:] or [connection_defaults[1]]
            conn[2:] = conn[2:] or [connection_defaults[2]]
        conn[1] = conn[1] or connection_defaults[1]
        # getaddrinfo() rejects a unicode port number on python 2.7.
        conn[1] = str(conn[1])
        self.connection = conn

        module = importlib.import_module('clewn.%s' % self.module)
        class_name = self.module[0].upper() + self.module[1:]
        self.clazz = getattr(module, class_name)
        self.debugger = self.clazz(self)

        self.vim_version()
        if self.options.editor:
            self.spawn_vim()
        else:
            script = self.debugger.vim_script()
            info('building the Vim script file: %s', script)

        return module

    def shutdown(self):
        if self.closed:
            return
        self.closed = True

        while self.events and not self.events.empty():
            event = self.events. get_nowait()
            warning('pending event at shutdown: ', event)

        # Remove the Vim script file in case the script failed to remove itself.
        if (self.f_script and not (self.module == 'pdb' and self.testrun)):
            del self.f_script

        if self.debugger:
            self.debugger.close()
        if self.nbserver:
            self.nbserver.close()
        if self.netbeans:
            self.netbeans.close()
        info('pyclewn exiting')

        if self.testrun:
            # wait for Vim to terminate
            if self.vim_process is not None:
                while True:
                    try:
                        self.vim_process.wait()
                    except OSError as err:
                        errcode = err.errno
                        if errcode == errno.EINTR:
                            continue
                        elif errcode == errno.ECHILD:
                            break
                        raise
                    else:
                        break
            if self.file_hdlr is not None:
                logging.getLogger().removeHandler(self.file_hdlr)
                self.file_hdlr.close()

        if self.loop:
            self.loop.close()

    def parse_options(self, argv):
        """Parse the command line options."""
        def args_callback(option, opt_str, value, parser):
            try:
                args = misc.dequote(value)
            except ClewnError as e:
                raise optparse.OptionValueError(e)
            if option._short_opts[0] == '-c':
                parser.values.cargs = args
            else:
                parser.values.args = args

        def bpcolor_callback(option, opt_str, value, parser):
            colors = value.split(',')
            if len(colors) != 3:
                raise optparse.OptionValueError('Three colors are required for'
                ' the \'--background\' option.')
            if not set(colors).issubset(BG_COLORS):
                raise optparse.OptionValueError('These colors are invalid: %s.'
                    % str(tuple(set(colors).difference(BG_COLORS))))
            parser.values.bg_colors = colors

        formatter = optparse.IndentedHelpFormatter(max_help_position=30)
        parser = optparse.OptionParser(
                        version='%prog ' + __version__,
                        usage='%prog [options] [debugger]',
                        formatter=formatter)

        parser.add_option('-g', '--gdb',
                type='string', metavar='PARAM_LIST', default='',
                help='set gdb PARAM_LIST')
        parser.add_option('-d', '--daemon',
                action="store_true", default=False,
                help='run as a daemon (default \'%default\')')
        parser.add_option('--run',
                action="store_true", default=False,
                help=('allow the debuggee to run after the pdb() call'
                ' (default \'%default\')'))
        parser.add_option('-e', '--editor', default=None,
                help='set Vim program to EDITOR')
        parser.add_option('-c', '--cargs', metavar='ARGS',
                type='string', action='callback', callback=args_callback,
                help='set Vim arguments to ARGS')
        parser.add_option('-p', '--pgm',
                help='set the debugger pathname to PGM')
        parser.add_option('-a', '--args',
                type='string', action='callback', callback=args_callback,
                help='set the debugger arguments to ARGS')
        parser.add_option('--terminal',
                type='string', default='xterm,-e',
                help=('set the terminal to use with the inferiortty'
                ' command (default \'%default\')'))
        parser.add_option('--tty',
                type='string', metavar='TTY', default=os.devnull,
                help=('use TTY for input/output by the python script being'
                ' debugged (default \'%default\')'))
        parser.add_option('-w', '--window', default='top',
                type='string', metavar='LOCATION',
                help="%s%s%s" % ("open the debugger console window at LOCATION "
                "which may be one of ", WINDOW_LOCATION,
                ", the default is '%default'"))
        parser.add_option('-m', '--maxlines',
                metavar='LNUM', default=netbeans.CONSOLE_MAXLINES, type='int',
                help='set the maximum number of lines of the debugger console'
                ' window to LNUM (default %default lines)')
        parser.add_option('-x', '--prefix', default='C',
                help='set the commands prefix to PREFIX (default \'%default\')')
        parser.add_option('-b', '--background',
                type='string', action='callback', callback=bpcolor_callback,
                metavar='COLORS',
                help='COLORS is a comma separated list of the three colors of'
                ' the breakpoint enabled, breakpoint disabled and frame sign'
                ' background colors, in this order'
                ' (default \'Cyan,Green,Magenta\')')
        parser.add_option('-n', '--netbeans', metavar='CONN',
                help='set netBeans connection parameters to CONN with CONN as'
                ' \'host[:port[:passwd]]\'')
        parser.add_option('-l', '--level', metavar='LEVEL',
                type='string', default='',
                help='set the log level to LEVEL: %s (default \'error\')'
                % ', '.join(misc.LOG_LEVELS))
        parser.add_option('-f', '--file', metavar='FILE',
                help='set the log file name to FILE')
        (options, args) = parser.parse_args(args=argv)

        # The debugger module name.
        self.module = 'gdb'
        if args:
            if len(args) != 1:
                parser.error('only one argument is allowed: "%s"' %args)
            self.module = args[0]
        if self.module == 'pdb':
            # Only the testsuite may spawn the editor.
            if not self.testrun:
                if options.editor not in (None, ''):
                    parser.error('Invalid option "--editor" in this context.')
                options.editor = ''
        elif options.editor is None:
            options.editor = os.environ.get('EDITOR', 'gvim')

        location = options.window.lower()
        if location in WINDOW_LOCATION:
            options.window = location
        else:
            parser.error(
                    '"%s" is an invalid window LOCATION, must be one of %s'
                    % (options.window, WINDOW_LOCATION))

        if options.netbeans and len(options.netbeans.split(':')) > 3:
            parser.error('too many netbeans connection parameters')

        # Set Netbeans class members.
        if location == 'none':
            netbeans.Netbeans.enable_setdot = False

        if options.maxlines <= 0:
            parser.error('invalid number for maxlines option')
        netbeans.Netbeans.max_lines = options.maxlines

        if options.background:
            netbeans.Netbeans.bg_colors = options.background

        level = options.level.upper()
        if level:
            if hasattr(logging, level):
                 options.level = getattr(logging, level)
            elif level == misc.NBDEBUG_LEVEL_NAME.upper():
                options.level = misc.NBDEBUG
            else:
                parser.error(
                    '"%s" is an invalid log LEVEL, must be one of: %s'
                    % (options.level, ', '.join(misc.LOG_LEVELS)))

        self.options = options

    def setlogger(self):
        """Setup the root logger with handlers: stderr and optionnaly a file."""
        class Formatter(logging.Formatter):
            def format(self, record):
                if record.name == 'asyncio':
                    record.name = 'aio'
                elif record.name == 'trollius':
                    record.name = 'trol'
                record.created %= 100
                return logging.Formatter.format(self, record)

        # do not handle exceptions while emit(ing) a logging record
        logging.raiseExceptions = False
        # add nbdebug log level
        logging.addLevelName(misc.NBDEBUG, misc.NBDEBUG_LEVEL_NAME.upper())
        # can't use basicConfig with kwargs, only supported with 2.4
        root = logging.getLogger()

        # Don't print on stderr after logging module teardown.
        # 'lastResort' has been introduced with Python 3.2.
        # Issue 12637 in Python 3.2: 'lastResort' prints all messages, even
        # those with level < WARNING.
        # See also issue 9501 in Python 3.3.0.
        if (sys.version_info[:2] == (3, 2) and hasattr(logging, 'lastResort')):
            logging.lastResort = None

        if not root.handlers:
            root.manager.emittedNoHandlerWarning = True
            if self.options.level == misc.NBDEBUG:
                fmt = Formatter(
                        '%(created).3f %(name)-4s %(levelname)-7s %(message)s')
            else:
                fmt = Formatter(
                        '%(name)-4s %(levelname)-7s %(message)s')
            if self.options.file:
                try:
                    file_hdlr = logging.FileHandler(self.options.file, 'w')
                except IOError:
                    logging.exception('cannot setup the log file')
                else:
                    file_hdlr.setFormatter(fmt)
                    root.addHandler(file_hdlr)
                    self.file_hdlr = file_hdlr

            # default level: CRITICAL
            self.loglevel = logging.CRITICAL
            if self.options.level:
                self.loglevel = self.options.level

            # add an handler to stderr, except when running the testsuite
            # or a log file is used with a level not set to critical
            if (not self.testrun and
                        not (self.options.file and
                            self.loglevel != logging.CRITICAL)):
                self.stderr_hdlr = misc.StderrHandler()
                self.stderr_hdlr.setFormatter(fmt)
                root.addHandler(self.stderr_hdlr)

            root.setLevel(self.loglevel)

    def set_exception_handler(self):
        def exception_handler(loop, context):
            # A read() syscall returns -1 when the slave side of the pty is
            # closed. Ignore the exception.
            exc = context.get('exception')
            if (isinstance(context.get('protocol'), gdb.Gdb) and
                    isinstance(exc, OSError) and exc.errno == errno.EIO):
                return

            loop.default_exception_handler(context)
            # Terminate the vim.run() loop.
            self.signal(None)

        self.loop.set_exception_handler(exception_handler)

    def signal(self, event):
        self.events.put_nowait(event)

    @asyncio.coroutine
    def run(self):
        protocol_factory = functools.partial(netbeans.Netbeans,
                                             self.signal, self.connection[2])
        self.nbserver = yield from(self.loop.create_server(protocol_factory,
                                                           self.connection[0],
                                                           self.connection[1]))
        timeout = self.loop.call_later(CONNECTION_TIMEOUT, connection_timeout)

        while True:
            event = yield from(self.events.get())
            if timeout:
                timeout.cancel()
                timeout = None

            if isinstance(event, netbeans.Netbeans):
                if event is self.netbeans:
                    if not self.netbeans.connected:
                        if self.netbeans.debugger is not None:
                            # Wait until the debugger has signaled it is closed.
                            continue
                        else:
                            info('signaled netbeans is disconnected')
                            break
                    # Netbeans signaling it is ready.
                    info(self.netbeans)
                    self.netbeans.set_debugger(self.debugger)
                    # Daemonize now, no more critical startup errors to print on
                    # the console.
                    if self.options.daemon:
                        daemonize()
                    info('pyclewn version %s and the %s debugger', __version__,
                         self.module)
                elif self.netbeans:
                    nb = event
                    if nb.connected:
                        info('rejecting connection from %s:'
                             ' netbeans already connected', nb.addr)
                        nb.close()
                else:
                    # Netbeans connection accepted.
                    self.netbeans = event
                    self.nbserver.close()
                    self.nbserver = None

            elif self.netbeans and isinstance(event, debugger.Debugger):
                if self.netbeans.connected:
                    # The debugger has been closed, instantiate a new one.
                    self.debugger = self.clazz(self)
                    self.netbeans.set_debugger(self.debugger)
                    info('new "%s" instance', self.module)
                else:
                    info('signaled debugger closed and netbeans disconnected')
                    break

            else:
                info('got signal %s', event)
                break

    @asyncio.coroutine
    def pdb_run(self, clewn_thread_ready):
        """Run the pdb clewn thread."""
        protocol_factory = functools.partial(netbeans.Netbeans,
                                             self.signal, self.connection[2])
        self.nbserver = yield from(self.loop.create_server(protocol_factory,
                                                           self.connection[0],
                                                           self.connection[1]))
        clewn_thread_ready.set()

        while True:
            event = yield from(self.events.get())
            if isinstance(event, netbeans.Netbeans):
                if event is self.netbeans:
                    if not self.netbeans.connected:
                        if self.netbeans.debugger is not None:
                            self.netbeans.close()
                            self.netbeans = None
                            info('the current netbeans session is closed')
                            continue
                        else:
                            info('signaled netbeans is disconnected')
                            break
                    # Netbeans signaling it is ready.
                    info(self.netbeans)
                    self.netbeans.set_debugger(self.debugger)
                    info('pyclewn version %s and the %s debugger', __version__,
                         self.module)
                elif self.netbeans:
                    nb = event
                    if nb.connected:
                        info('rejecting connection from %s:'
                             ' netbeans already connected', nb.addr)
                        nb.close()
                else:
                    info('netbeans connection accepted')
                    self.netbeans = event

            elif isinstance(event, debugger.Debugger):
                # Ignore debugger close events since this only indicates here
                # that the netbeans socket is closed. The target thread is
                # responsible for terminating the clewn thread by calling
                # pdb.exit().
                info('ignoring a debugger close event')

            else:
                info('got signal %s', event)
                if self.netbeans:
                    self.netbeans.close()
                break

    def __str__(self):
        """Return a representation of the whole stuff."""
        self_str = ''
        if self.netbeans is not None:
            self_str = '\n%s%s' % (pformat('options', self.options),
                            pformat('netbeans', self.netbeans))
        if self.debugger is not None:
            self_str += ('debugger %s:\n%s\n'
                                % (self.module, self.debugger))
        return self_str

