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

"""
The Dispatcher instance runs an Application instance (debugger) and
dispatches messages to gvim and the debugger.

A new Application instance is restarted whenever the current one dies.
The debugger to run is chosen from the command line arguments, amongst the
registered debuggers.

"""
import sys
import os
import string
import time
import subprocess
import asyncore
import inspect
import optparse
import logging
import pprint
import platform

import clewn
import misc
import clewn.application as application
import clewn.gdb as gdb
import clewn.netbeans as netbeans

CONNECTION_DEFAULTs = '', 3219, 'changeme'
CONNECTION_TIMEOUT = 30

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('disp')

def last_traceback():
    t, v, tb = sys.exc_info()
    assert tb
    while tb:
        filename = tb.tb_frame.f_code.co_filename
        lnum = tb.tb_lineno
        last_tb = tb
        tb = tb.tb_next
    del tb

    return t, v, filename, lnum, last_tb

def main():
    # build the list of Application subclasses,
    # candidates for selection by the commad line arguments
    classes = clewn.class_list()

    testrun = reduce(lambda x, y: x or (y == 'unittest'),
                                        [False] + sys.modules.keys())
    proc = Dispatcher(classes, testrun)
    proc.parse_options()
    try:
        try:
            proc.setlogger()
            proc.start()
        except (KeyboardInterrupt, SystemExit):
            pass
        except:
            t, v, filename, lnum, last_tb = last_traceback()

            # get the line where exception occured
            try:
                lines, top = inspect.getsourcelines(last_tb)
                info = 'source line: "%s"\nat %s:%d' \
                        % (lines[lnum - top].strip(), filename, lnum)
            except IOError:
                sys.exc_clear()
                info = ''

            except_str = '\nException in pyclewn:\n\n'  \
                            '%s\n"%s"\n%s\n\n'          \
                            'pyclewn aborting...\n'     \
                                    % (str(t), str(v), info)
            critical(except_str)
            proc.nbsock.show_balloon(except_str)
    finally:
        debug('Dispatcher instance: ' + str(proc))
        proc.shutdown()


class Dispatcher(object):
    """The Dispatcher dispatches messages to gvim and the debugger.

    Instance attributes:
        testrun: boolean
            True when run from a test suite
        file_hdlr: logger.FileHandler
            log file
        app: application.Application
            the application instance run by Dispatcher
        clss: class
            the selected Application class
        f_script: file
            the vim script file object
        nbsock: netbeans.Netbeans
            the netbeans socket
        gvim: subprocess.Popen
            the gvim Popen instance
        class_list: list or tuple
            the list of registered Application classes
        options: optparse.Values
            the command line options
        parser: optparse.OptionParser
            the command line parser used to add options for processing

    """

    def __init__(self, class_list, testrun):
        """Constructor

        Parameter:
            class_list: list or tuple
                the list of registered Application classes

        """
        self.testrun = testrun
        self.file_hdlr = None
        self.app = None
        self.clss = None
        self.f_script = None
        self.nbsock = netbeans.Netbeans()
        self.gvim = None
        self.options = None
        formatter = optparse.IndentedHelpFormatter(max_help_position=30)
        usage = "usage: python %prog [options]"
        self.parser = optparse.OptionParser(
                        version='%prog ' + clewn.__version__ + clewn.__svn__,
                        usage=usage,
                        formatter=formatter)
        self.class_list = class_list
        for clss in class_list:
            self.register(clss)

    def start(self):
        """Start the editor, connect to it, and start the application."""
        # log platform information for debugging
        info('platform: [%s]', ', '.join(platform.uname()))

        # set Gdb as the default Application
        if not self.clss:
            self.clss = gdb.Gdb

        if self.clss.param:
            self.clss.param = self.parser.values.param or self.clss.param

        # instantiate the application
        self.app = self.clss(self.nbsock,
                                self.options.daemon,
                                self.parser.values.pgm,
                                self.parser.values.args)

        # read keys mappings
        self.app.read_keysfile()

        # listen on netbeans port
        conn = list(CONNECTION_DEFAULTs)
        if self.parser.values.netbeans:
            conn = self.parser.values.netbeans.split(':')
            conn[1:] = conn[1:] or [CONNECTION_DEFAULTs[1]]
            conn[2:] = conn[2:] or [CONNECTION_DEFAULTs[2]]
        assert len(conn) == 3, 'too many netbeans connection parameters'
        conn[1] = conn[1] or CONNECTION_DEFAULTs[1]
        self.nbsock.listen(*conn)
        info(self.nbsock)

        # check pyclewn version
        version = clewn.run_vim_cmd(['runtime pyclewn.vim',
                                   'if exists("g:pyclewn_version")'
                                       '| echo g:pyclewn_version'
                                       '| endif']).strip()
        pyclewn_version = 'pyclewn-' + clewn.__version__
        if version != pyclewn_version:
            critical('pyclewn.vim version does not match pyclewn\'s:\n'\
                        '\t\tpyclewn version: "%s"\n'\
                        '\t\tpyclewn.vim version: "%s"',
                        pyclewn_version, version)
            sys.exit()
        info('pyclewn.vim version: %s', version)
        info('vim version: %s', clewn.run_vim_cmd(['echo v:version']).strip())

        # start the editor
        args = self.options.editor_args or []
        self.f_script = self.app.vim_script(self.options.prefix)
        info('sourcing the vim script file: %s', self.f_script.name)
        args[:0] = [self.f_script.name]
        args[:0] = ['-S']
        args[:0] = ['runtime pyclewn.vim']
        args[:0] = ['-c']
        if not self.options.editor_args \
                or not                  \
                [a for a in self.options.editor_args if a.startswith('-nb')]:
            args[:0] = ['-nb']
        args[:0] = ['-g']       # it is safe to have multiple options '-g'
        args[:0] = [self.options.editor]
        info('editor argv list: %s', str(args))
        try:
            self.gvim = subprocess.Popen(args)
        except OSError:
            critical('cannot start the editor'); raise

        # run the dispatch loop
        self.loop()
        self.app.close()

    def shutdown(self):
        """Shutdown the dispatcher."""
        # remove the vim script file in case the script failed to remove itself
        if self.f_script:
            del self.f_script

        self.nbsock.close()
        info('pyclewn exiting')

        if self.testrun:
            # required by testsuite with multiple dispatcher instances
            # _bset being a Singleton
            if self.app is not None:
                self.app._bset.clear()
            # wait for gvim to close all files
            if self.gvim is not None:
                try:
                    self.gvim.wait()
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

        assert not asyncore.socket_map

    def parse_options(self):
        """Parse the command line options."""
        def loglvl_callback(option, opt_str, value, parser):
            level = value.upper()
            if hasattr(logging, level):
                parser.values.logLevel = getattr(logging, level)
            elif level == misc.NBDEBUG_LEVEL_NAME.upper():
                parser.values.logLevel = misc.NBDEBUG
            else:
                raise optparse.OptionValueError(
                        '"%s" is an invalid log LEVEL, must be one of: %s'
                        % (str(value), misc.LOG_LEVELS))
        def args_callback(option, opt_str, value, parser):
            try:
                args = misc.unquote(value)
            except misc.Error, e:
                raise optparse.OptionValueError(e)
            if option._short_opts[0] == '-c':
                parser.values.editor_args = args
            else:
                parser.values.args = args

        self.parser.add_option('-d', '--daemon',
                action="store_true", dest='daemon', default=False,
                help='run as a daemon (default \'%default\')')
        self.parser.add_option('-p', '--pgm', dest='pgm',
                help='set the application program to PGM')
        self.parser.add_option('-a', '--args', dest='args',
                type='string', action='callback', callback=args_callback,
                help='set the application program arguments to ARGS')
        self.parser.add_option('-e', '--editor', dest='editor', default='gvim',
                help='set the editor program to EDITOR (default \'%default\')')
        self.parser.add_option('-c', '--cargs', dest='editor_args', metavar='ARGS',
                type='string', action='callback', callback=args_callback,
                help='set the editor program arguments to ARGS')
        self.parser.add_option('-x', '--prefix', dest='prefix', default='C',
                help='set the commands prefix to PREFIX (default \'%default\')')
        self.parser.add_option('-n', '--netbeans',
                metavar='CONN',
                help='set netBeans connection parameters to CONN with CONN as'
                ' \'host[:port[:passwd]]\', (the default is \'%s\''
                ' where the empty host represents INADDR_ANY)' %
                ':'.join([str(x) for x in CONNECTION_DEFAULTs]))
        self.parser.add_option('-l', '--level', dest='logLevel', metavar='LEVEL',
                type='string', action='callback', callback=loglvl_callback,
                help='set the log level to LEVEL: %s (default error)'
                % misc.LOG_LEVELS)
        self.parser.add_option('-f', '--file', dest='logFile', metavar='FILE',
                help='set the log file name to FILE')
        (self.options, args) = self.parser.parse_args()

    def setlogger(self):
        """Setup the root logger with handlers: stderr and optionnaly a file."""
        # add nbdebug log level
        logging.addLevelName(misc.NBDEBUG, misc.NBDEBUG_LEVEL_NAME.upper())

        # can't use basicConfig with kwargs, only supported with 2.4
        root = logging.getLogger()
        if not root.handlers:
            root.manager.emittedNoHandlerWarning = True
            fmt = logging.Formatter('%(name)-4s %(levelname)-7s %(message)s')

            # add an handler to stderr, except when running the testsuite
            if not self.testrun:
                hdlr = logging.StreamHandler(sys.stderr)
                hdlr.setFormatter(fmt)
                root.addHandler(hdlr)

            if self.options.logFile:
                try:
                    hdlr = logging.FileHandler(self.options.logFile, 'w')
                except IOError:
                    logging.exception('cannot setup the log file')
                else:
                    hdlr.setFormatter(fmt)
                    root.addHandler(hdlr)
                    self.file_hdlr = hdlr

            # default level: ERROR
            level = logging.ERROR
            if self.options.logLevel:
                level = self.options.logLevel
            root.setLevel(level)

    def loop(self):
        """The dispatch loop."""
        map = asyncore.socket_map

        start = time.time()
        while map:
            # start the application
            if start is not False:
                if time.time() - start > CONNECTION_TIMEOUT:
                    raise IOError(
                        'connection to the editor timed out after %s seconds'
                        % str(CONNECTION_TIMEOUT))
                if self.nbsock.ready:
                    start = False
                    info(self.nbsock)
                    self.nbsock.set_application(self.app)

                    # can daemonize now, no more critical startup errors to
                    # print on the console
                    if self.options.daemon:
                        self.daemonize()
                    info('pyclewn version %s and the %s application',
                        clewn.__version__ + clewn.__svn__, self.clss.__name__)

            # instantiate a new application
            elif self.app.closed and self.nbsock.connected:
                self.app = self.clss(self.nbsock,
                                        self.options.daemon,
                                        self.parser.values.pgm,
                                        self.parser.values.args)
                self.nbsock.set_application(self.app)
                info('new "%s" instance', self.clss.__name__.lower())

            asyncore.poll(timeout=.100, map=map)

    def register(self, clss):
        """Register an application."""
        def set_applicationCallback(option, opt_str, value, parser):
            if self.clss:
                raise optparse.OptionValueError(
                            'selecting two applications is not allowed')
            opt = (option._short_opts or option._long_opts)[0]
            for clss in self.class_list:
                if opt == clss.opt or opt == clss.long_opt:
                    self.clss = clss
                    break
            else:
                assert False, 'programming error'

        assert clss is not application.Application
        assert issubclass(clss, application.Application)
        assert clss.opt or clss.long_opt
        metavar = clss.metavar or clss.__name__
        args = dict(metavar=metavar, help=clss.help,
                action='callback', callback=set_applicationCallback)
        # Application option takes one parameter
        if clss.param:
            args['type'] = 'string'
        self.parser.add_option(clss.opt, clss.long_opt, **args)

    def daemonize(self):
        """Run Dispatcher as a daemon."""
        CHILD = 0
        if os.name == 'posix':
            # setup a pipe between the child and the parent,
            # so that the parent knows when the child has done
            # the setsid() call and is allowed to exit
            pipe_r, pipe_w = os.pipe()

            pid = os.fork()
            if pid != CHILD:
		# the read returns when the child closes the pipe
		os.close(pipe_w)
		os.read(pipe_r, 1)
		os.close(pipe_r)
                os._exit(os.EX_OK)

            # close stdin, stdout and stderr
            try:
                devnull = os.devnull
            except AttributeError:
                devnull = '/dev/null'
            fd = os.open(devnull, os.O_RDWR)
            os.close(0)
            os.close(1)
            os.close(2)
            os.dup(fd)      # replace stdin  (file descriptor 0)
            os.dup(fd)      # replace stdout (file descriptor 1)
            os.dup(fd)      # replace stderr (file descriptor 2)
            os.close(fd)    # don't need this now that we've duplicated it

            # change our process group in the child
            try:
                os.setsid()
            except OSError:
                critical('cannot run as a daemon'); raise
            os.close(pipe_r)
            os.close(pipe_w)

    def pprint(self, name, obj):
        if obj:
            return '%s:\n%s\n' % (name, pprint.pformat(obj.__dict__))
        else: return ''

    def __str__(self):
        return '\n'                                                     \
            + self.pprint('options', self.options)                      \
            + self.pprint('netbeans', self.nbsock)                      \
            + self.pprint('application %s' % self.clss.__name__, self.app)


if __name__ == "__main__":
    main()

