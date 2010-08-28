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

"""
A Vim instance starts a Debugger instance and dispatches the netbeans messages
exchanged by vim and the debugger. A new Debugger instance is restarted whenever
the current one dies.

"""
import os
import sys
import time
import os.path
import tempfile
import subprocess
import asyncore
import inspect
import optparse
import logging
import errno

from clewn import *
import clewn.misc as misc
import clewn.gdb as gdb
import clewn.simple as simple
import clewn.netbeans as netbeans
import clewn.evtloop as evtloop
if os.name == 'nt':
    from clewn.nt import hide_console as daemonize
    from clewn.nt import platform_data
else:
    from clewn.posix import daemonize, platform_data


WINDOW_LOCATION = ('top', 'bottom', 'left', 'right')
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
Unused = error
Unused = warning

def exec_vimcmd(commands, pathname=''):
    """Run a list of Vim 'commands' and return the commands output."""
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
        except (OSError, IOError), err:
            if isinstance(err, OSError) and err.errno == errno.ENOENT:
                print >> sys.stderr, "Failed to run '%s' as Vim." % args[0]
                print >> sys.stderr, ("Please run 'pyclewn"
                                      " --editor=/path/to/(g)vim'.\n")
            else:
                print >> sys.stderr, ("Failed to run Vim as:\n'%s'\n" %
                                       str(args))
            raise
    finally:
        if f is not None:
            f.close()
        if tmpname and os.path.exists(tmpname):
            try:
                os.unlink(tmpname)
            except OSError:
                pass
    if output is None:
        raise ClewnError("error starting Vim with:\n'%s'" % ' '.join(args))
    return output

def pformat(name, obj):
    """Pretty format an object __dict__."""
    if obj:
        return '%s:\n%s\n' % (name, misc.pformat(obj.__dict__))
    else: return ''

def main(testrun=False):
    """Main."""
    vim = Vim(testrun)
    try:
        try:
            vim.setlogger()
            vim.start()
        except (KeyboardInterrupt, SystemExit):
            pass
        except:
            t, v, filename, lnum, last_tb = misc.last_traceback()

            # get the line where exception occured
            try:
                lines, top = inspect.getsourcelines(last_tb)
                location = 'source line: "%s"\nat %s:%d' \
                        % (lines[lnum - top].strip(), filename, lnum)
            except IOError:
                sys.exc_clear()
                location = ''

            except_str = '\nException in pyclewn:\n\n'  \
                            '%s\n"%s"\n%s\n\n'          \
                            'pyclewn aborting...\n'     \
                                    % (str(t), str(v), location)
            critical(except_str)
            vim.netbeans.show_balloon(except_str)
    finally:
        debug('Vim instance: ' + str(vim))
        vim.shutdown()


class Vim(object):
    """The Vim instance dispatches netbeans messages.

    Instance attributes:
        testrun: boolean
            True when run from a test suite
        file_hdlr: logger.FileHandler
            log file
        socket_map: asyncore socket dictionary
            socket and socket-like objects listening on the select
            event loop
        debugger: debugger.Debugger
            the debugger instance run by Vim
        clazz: class
            the selected Debugger subclass
        f_script: file
            the Vim script file object
        netbeans: netbeans.Netbeans
            the netbeans async_chat instance
        vim: subprocess.Popen
            the vim Popen instance
        options: optparse.Values
            the command line options

    """

    def __init__(self, testrun):
        """Constructor"""
        self.testrun = testrun
        self.file_hdlr = None
        self.socket_map = asyncore.socket_map
        self.debugger = None
        self.clazz = None
        self.f_script = None
        self.netbeans = netbeans.Netbeans()
        self.vim = None
        self.options = None
        self.parse_options()

    def vim_version(self):
        """Check Vim version."""
        # test if Vim contains the netbeans 'remove' fix
        # test if Vim contains the netbeans 'getLength' fix
        # test if Vim contains the netbeans 'cmd on NoName buffer ignored' fix

        # pyclewn is started from within vim
        if not self.options.vim:
            self.netbeans.remove_fix = '1'
            self.netbeans.getLength_fix = '1'
            self.options.noname_fix = '1'
            return

        cmds = ['echo v:version > 701 || v:version == 701 && has("patch207")',
                'echo v:version > 702 || v:version == 702 && has("patch253")',
                'echo v:version > 702 || v:version == 702 && has("patch334")',
                'echo v:version',
                'runtime plugin/pyclewn.vim',
                'if exists("g:pyclewn_version")'
                    ' | echo g:pyclewn_version'
                    ' | endif',
                ]
        output = exec_vimcmd(cmds, self.options.vim).strip().split('\n')
        output = [x.strip('\r') for x in output]
        length = len(output)
        version = ''
        if length == 5:
            (self.netbeans.remove_fix,
             self.netbeans.getLength_fix,
             self.options.noname_fix,
             vimver, version) = output
        elif length == 4:
            (self.netbeans.remove_fix,
             self.netbeans.getLength_fix,
             self.options.noname_fix,
             vimver) = output
        else:
            critical('output of %s: %s', cmds, output)
            sys.exit(1)
        info('Vim version: %s', vimver)

        # check pyclewn version
        pyclewn_version = 'pyclewn-' + __tag__
        if version != pyclewn_version:
            critical('pyclewn.vim version does not match pyclewn\'s:\n'\
                        '\t\tpyclewn version: "%s"\n'\
                        '\t\tpyclewn.vim version: "%s"',
                        pyclewn_version, version)
            sys.exit(1)
        info('pyclewn.vim version: %s', version)

    def spawn_vim(self):
        """Spawn vim."""
        self.vim_version()
        args = self.options.vim_args or []
        self.f_script = self.debugger._vim_script(self.options)
        info('sourcing the Vim script file: %s', self.f_script.name)
        args[:0] = [self.f_script.name]
        args[:0] = ['-S']
        if not self.options.vim_args \
                or not                  \
                [a for a in self.options.vim_args if a.startswith('-nb')]:
            args[:0] = ['-nb']
        args[:0] = [self.options.vim]

        # uncomment next lines to run Valgrind on Vim
        # args[:0] = ["--leak-check=yes"]
        # args[:0] = ["valgrind"]

        info('Vim argv list: %s', str(args))
        try:
            self.vim = subprocess.Popen(args,
                                close_fds=(os.name != 'nt'))
        except OSError:
            critical('cannot start Vim'); raise

    def start(self):
        """Start Vim, connect to it, and start the debugger."""
        # log platform information for debugging
        info(platform_data())

        # instantiate the debugger
        self.debugger = self.clazz(self.netbeans, self.options)

        # read keys mappings
        self.debugger._read_keysfile()

        # listen on netbeans port
        conn = list(CONNECTION_DEFAULTs)
        if self.options.netbeans:
            conn = self.options.netbeans.split(':')
            conn[1:] = conn[1:] or [CONNECTION_DEFAULTs[1]]
            conn[2:] = conn[2:] or [CONNECTION_DEFAULTs[2]]
        assert len(conn) == 3, 'too many netbeans connection parameters'
        conn[1] = conn[1] or CONNECTION_DEFAULTs[1]
        self.netbeans.nb_listen(*conn)
        info(self.netbeans)

        if self.options.vim:
            self.spawn_vim()
        # pyclewn is started from within vim
        else:
            self.vim_version()
            script = self.debugger._vim_script(self.options)
            info('building the Vim script file: %s', script)

        # run the dispatch loop
        self.loop()
        self.debugger.close()

    def shutdown(self):
        """Shutdown the asyncore dispatcher."""
        # remove the Vim script file in case the script failed to remove it
        if self.f_script:
            del self.f_script

        self.netbeans.close()
        info('pyclewn exiting')

        if self.testrun:
            # wait for Vim to close all files
            if self.vim is not None:
                try:
                    self.vim.wait()
                except OSError:
                    # ignore: [Errno 4] Interrupted system call
                    pass
            if self.file_hdlr is not None:
                logging.getLogger().removeHandler(self.file_hdlr)
                self.file_hdlr.close()
            # get: IOError: [Errno 2] No such file or directory: '@test_out'
            # sleep does help avoiding this error
            time.sleep(0.100)

        else:
            logging.shutdown()

        for asyncobj in self.socket_map.values():
            asyncobj.close()

    def parse_options(self):
        """Parse the command line options."""
        def args_callback(option, opt_str, value, parser):
            unused = opt_str
            try:
                args = misc.dequote(value)
            except ClewnError, e:
                raise optparse.OptionValueError(e)
            if option._short_opts[0] == '-c':
                parser.values.vim_args = args
            else:
                parser.values.args = args

        def bpcolor_callback(option, opt_str, value, parser):
            unused = option
            unused = opt_str
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
                        version='%prog ' + __tag__,
                        usage='usage: python %prog [options]',
                        formatter=formatter)

        parser.add_option('-s', '--simple',
                action="store_true", dest='simple_debugger', default=False,
                help='select the simple debugger')
        parser.add_option('-g', '--gdb', dest='gdb_parameters',
                type='string', metavar='PARAM_LIST', default='',
                help='select the gdb debugger (the default)'
                     ', with a mandatory, possibly empty, PARAM_LIST')
        parser.add_option('-d', '--daemon',
                action="store_true", dest='daemon', default=False,
                help='run as a daemon (default \'%default\')')
        parser.add_option('-e', '--editor', dest='vim', default=editor,
                help='set Vim pathname to VIM (default \'%default\');'
                + ' Vim is not spawned by pyclewn when this parameter is'
                + ' set to an empty string')
        parser.add_option('-c', '--cargs', dest='vim_args', metavar='ARGS',
                type='string', action='callback', callback=args_callback,
                help='set Vim arguments to ARGS')
        parser.add_option('-p', '--pgm', dest='pgm',
                help='set the debugger pathname to PGM')
        parser.add_option('-a', '--args', dest='args',
                type='string', action='callback', callback=args_callback,
                help='set the debugger arguments to ARGS')
        parser.add_option('-w', '--window', dest='location', default='top',
                type='string',
                help="%s%s%s" % ("open the debugger console window at LOCATION "
                "which may be one of ", WINDOW_LOCATION,
                ", the default is '%default'"))
        parser.add_option('-m', '--maxlines', dest='max_lines',
                metavar='LNUM', default=netbeans.CONSOLE_MAXLINES, type='int',
                help='set the maximum number of lines of the debugger console'
                ' window to LNUM (default %default lines)')
        parser.add_option('-x', '--prefix', dest='prefix', default='C',
                help='set the commands prefix to PREFIX (default \'%default\')')
        parser.add_option('-b', '--background', dest='bg_colors',
                type='string', action='callback', callback=bpcolor_callback,
                metavar='COLORS',
                help='COLORS is a comma separated list of the three colors of'
                ' the breakpoint enabled, breakpoint disabled and frame sign'
                ' background colors, in this order'
                ' (default \'Cyan,Green,Magenta\')')
        parser.add_option('-n', '--netbeans',
                metavar='CONN',
                help='set netBeans connection parameters to CONN with CONN as'
                ' \'host[:port[:passwd]]\', (the default is \'%s\''
                ' where the empty host represents INADDR_ANY)' %
                ':'.join([str(x) for x in CONNECTION_DEFAULTs]))
        parser.add_option('-l', '--level', dest='logLevel', metavar='LEVEL',
                type='string', default='',
                help='set the log level to LEVEL: %s (default error)'
                % misc.LOG_LEVELS)
        parser.add_option('-f', '--file', dest='logFile', metavar='FILE',
                help='set the log file name to FILE')
        (self.options, args) = parser.parse_args()

        if self.options.simple_debugger:
            self.clazz = simple.Simple
        if self.options.gdb_parameters or self.clazz is None:
            self.clazz = gdb.Gdb

        location = self.options.location.lower()
        if location in WINDOW_LOCATION:
            self.options.location = location
        else:
            parser.error(
                    '"%s" is an invalid window LOCATION, must be one of %s'
                    % (self.options.location, WINDOW_LOCATION))

        if self.options.max_lines <= 0:
            parser.error('invalid number for maxlines option')
        self.netbeans.max_lines = self.options.max_lines

        if self.options.bg_colors:
            self.netbeans.bg_colors = self.options.bg_colors

        level = self.options.logLevel.upper()
        if level:
            if hasattr(logging, level):
                 self.options.logLevel = getattr(logging, level)
            elif level == misc.NBDEBUG_LEVEL_NAME.upper():
                self.options.logLevel = misc.NBDEBUG
            else:
                parser.error(
                    '"%s" is an invalid log LEVEL, must be one of: %s'
                    % (self.options.logLevel, misc.LOG_LEVELS))

    def setlogger(self):
        """Setup the root logger with handlers: stderr and optionnaly a file."""
        # do not handle exceptions while emit(ing) a logging record
        logging.raiseExceptions = False
        # add nbdebug log level
        logging.addLevelName(misc.NBDEBUG, misc.NBDEBUG_LEVEL_NAME.upper())

        # can't use basicConfig with kwargs, only supported with 2.4
        root = logging.getLogger()
        if not root.handlers:
            root.manager.emittedNoHandlerWarning = True
            fmt = logging.Formatter('%(name)-4s %(levelname)-7s %(message)s')

            if self.options.logFile:
                try:
                    hdlr_file = logging.FileHandler(self.options.logFile, 'w')
                except IOError:
                    logging.exception('cannot setup the log file')
                else:
                    hdlr_file.setFormatter(fmt)
                    root.addHandler(hdlr_file)
                    self.file_hdlr = hdlr_file

            # default level: ERROR
            level = logging.ERROR
            if self.options.logLevel:
                level = self.options.logLevel

                # add an handler to stderr, except when running the testsuite
                if not self.testrun:
                    hdlr_stream = logging.StreamHandler(sys.stderr)
                    hdlr_stream.setFormatter(fmt)
                    root.addHandler(hdlr_stream)

            root.setLevel(level)

    def loop(self):
        """The dispatch loop."""

        start = time.time()
        while self.socket_map:
            # start the debugger
            if start is not False:
                if time.time() - start > CONNECTION_TIMEOUT:
                    raise IOError(CONNECTION_ERROR % str(CONNECTION_TIMEOUT))
                if self.netbeans.ready:
                    start = False
                    info(self.netbeans)
                    self.netbeans.set_debugger(self.debugger)

                    # can daemonize now, no more critical startup errors to
                    # print on the console
                    if self.options.daemon:
                        daemonize()
                    version = __tag__
                    if __changeset__:
                        version += '.' + __changeset__
                    info('pyclewn version %s and the %s debugger',
                                        version, self.clazz.__name__)

            # instantiate a new debugger
            elif self.debugger.closed and self.netbeans.connected:
                self.debugger = self.clazz(self.netbeans, self.options)
                self.netbeans.set_debugger(self.debugger)
                info('new "%s" instance', self.clazz.__name__.lower())

            timeout = self.debugger._call_jobs()
            evtloop.poll(self.socket_map, timeout=timeout)

    def __str__(self):
        """Return a representation of the whole stuff."""
        self_str = '\n%s%s' % (pformat('options', self.options),
                            pformat('netbeans', self.netbeans))
        if self.debugger is not None:
            self_str += ('debugger %s:\n%s\n'
                                % (self.clazz.__name__, self.debugger))
        return self_str

