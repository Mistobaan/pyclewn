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
import time
import tempfile
import subprocess
import traceback
import optparse
import logging
import errno

from . import (__version__, ClewnError, misc, netbeans, evtloop, tty,
               simple, gdb, pdb,
               )
from .posix import daemonize, platform_data


WINDOW_LOCATION = ('top', 'bottom', 'left', 'right', 'none')
CONNECTION_DEFAULTs = '', 3219, 'changeme'
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

def exec_vimcmd(commands, pathname='', error_stream=None):
    """Run a list of Vim 'commands' and return the commands output."""
    try:
        perror = error_stream.write
    except AttributeError:
        perror = sys.stderr.write

    if not pathname:
        pathname = os.environ.get('EDITOR', 'gvim')

    args = [pathname, '-u', 'NONE', '-esX', '-c', 'set cpo&vim']
    fd, tmpname = tempfile.mkstemp(prefix='runvimcmd', suffix='.clewn')
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
        misc.unlink(tmpname)

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

def main(testrun=False):
    vim = Vim(testrun, sys.argv[1:])
    options = vim.options
    try:
        gdb_pty = None
        if not testrun:
            gdb_pty = tty.GdbInferiorPty(vim.stderr_hdlr, vim.socket_map)
        if (vim.clazz == gdb.Gdb
                    and gdb_pty
                    and not options.daemon
                    and os.isatty(sys.stdin.fileno())):
            # Use pyclewn pty as the debuggee standard input and output, but
            # not when vim is run as 'vim' or 'vi'.
            vim_pgm = os.path.basename(options.editor)
            if vim_pgm != 'vim' and vim_pgm != 'vi':
                gdb_pty.start()
                options.tty = gdb_pty.ptyname

        vim.setup(True)
        vim.loop()
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        except_str = 'Exception in pyclewn: "%s"\n' \
                     '%s\n'                         \
                     'pyclewn aborting...\n'        \
                            % (e, traceback.format_tb(sys.exc_info()[2])[-1])
        critical('\n' + except_str)
        if vim.nbserver.netbeans:
            vim.nbserver.netbeans.show_balloon(except_str)
    finally:
        if gdb_pty:
            gdb_pty.close()
        debug('Vim instance: ' + str(vim))
        vim.shutdown()

    return vim

class Vim(object):
    """The Vim class.

    Instance attributes:
        testrun: boolean
            True when run from a test suite
        argv: list
            pyclewn options as a list
        file_hdlr: logger.FileHandler
            log file
        stderr_hdlr: misc.StderrHandler
            sdterr stream handler
        socket_map: asyncore socket dictionary
            socket and socket-like objects listening on the select
            event loop
        debugger: debugger.Debugger
            the debugger instance run by Vim
        clazz: class
            the selected Debugger subclass
        f_script: file
            the Vim script file object
        nbserver: netbeans.Server
            the netbeans listening server instance
        vim: subprocess.Popen
            the vim Popen instance
        options: optparse.Values
            the command line options
        closed: boolean
            True when shutdown has been run
        poll: evtloop.Poll
            manage the select thread

    """

    def __init__(self, testrun, argv):
        self.testrun = testrun
        self.file_hdlr = None
        self.stderr_hdlr = None
        self.socket_map = {}
        self.debugger = None
        self.clazz = None
        self.f_script = None
        self.vim = None
        self.options = None
        self.closed = False
        self.parse_options(argv)
        self.setlogger()

    def vim_version(self):
        """Check Vim version."""
        # test if Vim contains the netbeans 'remove' fix
        # test if Vim contains the netbeans 'getLength' fix
        # test if Vim contains the netbeans 'cmd on NoName buffer ignored' fix

        # pyclewn is started from within vim
        # This is supported since vim73.
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
        if not self.options.cargs \
                or not                  \
                [a for a in self.options.cargs if a.startswith('-nb')]:
            args[:0] = ['-nb']
        args[:0] = [self.options.editor]

        # uncomment next lines to run Valgrind on Vim
        # args[:0] = ["--leak-check=yes"]
        # args[:0] = ["valgrind"]

        info('Vim argv list: %s', str(args))
        try:
            self.vim = subprocess.Popen(args, close_fds=True)
        except OSError:
            critical('cannot start Vim'); raise

    def setup(self, oneshot):
        """Listen to netbeans and start vim.

        Method parameters:
            oneshot: boolean
                when True, 'nbserver' accepts only a single connection
        """
        self.nbserver = netbeans.Server(self.socket_map)
        # instantiate 'poll' after addition of 'nbserver' to the asyncore
        # 'socket_map'
        self.poll = evtloop.Poll(self.socket_map)

        # log platform information for debugging
        info(platform_data())

        # listen on netbeans port
        conn = list(CONNECTION_DEFAULTs)
        if self.options.netbeans:
            conn = self.options.netbeans.split(':')
            conn[1:] = conn[1:] or [CONNECTION_DEFAULTs[1]]
            conn[2:] = conn[2:] or [CONNECTION_DEFAULTs[2]]
        assert len(conn) == 3, 'too many netbeans connection parameters'
        conn[1] = conn[1] or CONNECTION_DEFAULTs[1]
        self.nbserver.bind_listen(oneshot, *conn)

        self.vim_version()
        self.debugger = self.clazz(self.options, self.socket_map, self.testrun)
        if self.options.editor:
            self.spawn_vim()
        else:
            # pyclewn is started from within vim.
            script = self.debugger.vim_script()
            info('building the Vim script file: %s', script)

    def shutdown(self, logging_shutdown=True):
        if self.closed:
            return
        self.closed = True

        # Remove the Vim script file in case the script failed to remove itself.
        if hasattr(self, 'f_script') and self.f_script:
            del self.f_script

        if self.nbserver.netbeans:
            self.nbserver.netbeans.close()
        self.nbserver.close()
        info('pyclewn exiting')

        if self.testrun:
            # wait for Vim to terminate
            if self.vim is not None:
                while True:
                    try:
                        self.vim.wait()
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

        # do not shutdown logging with gdb as the SIGCHLD handler may overwrite
        # all the traces after the shutdown
        elif self.clazz != gdb.Gdb and logging_shutdown:
            logging.shutdown()

        for asyncobj in list(self.socket_map.values()):
            asyncobj.close()
        self.poll.close()

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

        editor = os.environ.get('EDITOR', 'gvim')
        formatter = optparse.IndentedHelpFormatter(max_help_position=30)
        parser = optparse.OptionParser(
                        version='%prog ' + __version__,
                        usage='usage: python %prog [options]',
                        formatter=formatter)

        parser.add_option('-s', '--simple',
                action="store_true", default=False,
                help='select the simple debugger')
        parser.add_option('--pdb',
                action="store_true", default=False,
                help='select \'pdb\', the python debugger')
        parser.add_option('-g', '--gdb',
                type='string', metavar='PARAM_LIST', default='',
                help='select the gdb debugger (the default)'
                     ', with a mandatory, possibly empty, PARAM_LIST')
        parser.add_option('-d', '--daemon',
                action="store_true", default=False,
                help='run as a daemon (default \'%default\')')
        parser.add_option('--run',
                action="store_true", default=False,
                help=('allow the debuggee to run after the pdb() call'
                ' (default \'%default\')'))
        parser.add_option('-e', '--editor', default=editor,
                help='set Vim pathname to VIM (default \'%default\');'
                + ' Vim is not spawned by pyclewn when this parameter is'
                + ' set to an empty string')
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
                ' command for running gdb or pdb inferior'
                ' (default \'%default\')'))
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
                ' \'host[:port[:passwd]]\', (the default is \'%s\''
                ' where the empty host represents INADDR_ANY)' %
                ':'.join([str(x) for x in CONNECTION_DEFAULTs]))
        parser.add_option('-l', '--level', metavar='LEVEL',
                type='string', default='',
                help='set the log level to LEVEL: %s (default \'error\')'
                % ', '.join(misc.LOG_LEVELS))
        parser.add_option('-f', '--file', metavar='FILE',
                help='set the log file name to FILE')
        (self.options, args) = parser.parse_args(args=argv)

        if self.options.simple:
            self.clazz = simple.Simple
        elif self.options.pdb:
            self.clazz = pdb.Pdb
        else:
            self.clazz = gdb.Gdb

        location = self.options.window.lower()
        if location in WINDOW_LOCATION:
            self.options.window = location
        else:
            parser.error(
                    '"%s" is an invalid window LOCATION, must be one of %s'
                    % (self.options.window, WINDOW_LOCATION))

        # set Netbeans class members
        if location == 'none':
            netbeans.Netbeans.enable_setdot = False

        if self.options.maxlines <= 0:
            parser.error('invalid number for maxlines option')
        netbeans.Netbeans.max_lines = self.options.maxlines

        if self.options.background:
            netbeans.Netbeans.bg_colors = self.options.background

        level = self.options.level.upper()
        if level:
            if hasattr(logging, level):
                 self.options.level = getattr(logging, level)
            elif level == misc.NBDEBUG_LEVEL_NAME.upper():
                self.options.level = misc.NBDEBUG
            else:
                parser.error(
                    '"%s" is an invalid log LEVEL, must be one of: %s'
                    % (self.options.level, ', '.join(misc.LOG_LEVELS)))

    def setlogger(self):
        """Setup the root logger with handlers: stderr and optionnaly a file."""
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
            fmt = logging.Formatter('%(name)-4s %(levelname)-7s %(message)s')

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
            level = logging.CRITICAL
            if self.options.level:
                level = self.options.level

            # add an handler to stderr, except when running the testsuite
            # or a log file is used with a level not set to critical
            if (not self.testrun and
                        not (self.options.file and level != logging.CRITICAL)):
                self.stderr_hdlr = misc.StderrHandler()
                self.stderr_hdlr.setFormatter(fmt)
                root.addHandler(self.stderr_hdlr)

            root.setLevel(level)

    def loop(self):
        """The event loop."""

        start = time.time()
        while True:
            # Accept the netbeans connection.
            if start is not False:
                if time.time() - start > CONNECTION_TIMEOUT:
                    raise IOError(CONNECTION_ERROR % str(CONNECTION_TIMEOUT))
                nbsock = self.nbserver.netbeans
                if nbsock and nbsock.ready:
                    start = False
                    info(nbsock)
                    nbsock.set_debugger(self.debugger)

                    # Daemonize now, no more critical startup errors to
                    # print on the console.
                    if self.options.daemon:
                        daemonize()
                    info('pyclewn version %s and the %s debugger',
                                        __version__, self.clazz.__name__)
            elif nbsock.connected:
                # Instantiate a new debugger.
                if self.debugger.closed:
                    self.debugger = self.clazz(self.options, self.socket_map,
                                               self.testrun)
                    nbsock.set_debugger(self.debugger)
                    info('new "%s" instance', self.clazz.__name__.lower())
            else:
                if not self.debugger.started or self.debugger.closed:
                    break

            timeout = self.debugger._call_jobs()
            self.poll.run(timeout=timeout)

        self.debugger.close()

    def __str__(self):
        """Return a representation of the whole stuff."""
        self_str = ''
        if self.nbserver.netbeans is not None:
            self_str = '\n%s%s' % (pformat('options', self.options),
                            pformat('netbeans', self.nbserver.netbeans))
        if self.debugger is not None:
            self_str += ('debugger %s:\n%s\n'
                                % (self.clazz.__name__, self.debugger))
        return self_str

