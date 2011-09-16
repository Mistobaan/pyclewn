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

"""Supporting definitions for the pyclewn regression tests."""

import sys
import os
import string
import time
import traceback
from unittest import TestCase, TestResult

import clewn.vim as vim

if os.name == 'nt':
    SLEEP_TIME = '1400m'
elif 'CLEWN_PIPES' in os.environ:
    SLEEP_TIME = '600m'
else:
    SLEEP_TIME = '600m'
NETBEANS_PORT = 3219
LOGFILE = 'logfile'

# filenames used for testing
TESTFN = '@test'
TESTFN_FILE = TESTFN + '_file_'
TESTFN_OUT = TESTFN + '_out'

def get_description(test):
    """"Return a ClewnTestCase description."""
    return '<%s:%s> %s' % (test.__class__.__name__,
                            test.method, test.shortDescription())

class ClewnTestCase(TestCase):
    """Pyclewn test case abstract class.

    The netbeans port changes on each run, within the interval
    [NETBEANS_PORT, NETBEANS_PORT + 99].
    In verbose mode, pyclewn runs at 'nbdebug' log level and the log is
    written to LOGFILE.

    """
    _port = 0
    _verbose = False

    def __init__(self, method='runTest'):
        """Constructor."""
        TestCase.__init__(self, method)
        self.method = method
        self.debugged_script = None
        self.fnull = None

    def setUp(self):
        """Setup pyclewn arguments."""
        port = self._port + NETBEANS_PORT

        sys.argv = [
            '-c',                       # argv[0], a script
            '--netbeans=:%d' % port,    # netbeans port
            '--file=' + LOGFILE,
            '--cargs',                  # vim args
            '-nb:127.0.0.1:%d:changeme '
                '-u NORC '
                '-U NONE '
                '-s %s' % (port, TESTFN),
        ]
        if 'EDITOR' in os.environ:
            sys.argv.append('--editor=%s' % os.environ['EDITOR'])
        if self._verbose:
            sys.argv.append('--level=nbdebug')

    def setup_vim_arg(self, newarg):
        """Add a new Vim argument to the existing arguments."""
        unused = self
        argv = sys.argv
        i = argv.index('--cargs')
        argv.pop(i)
        assert len(argv) > i + 1
        args = argv.pop(i)
        args += " " + newarg
        argv.append('--cargs')
        argv.append(args)

    def tearDown(self):
        """Cleanup stuff after the test."""
        self.__class__._port = (self._port + 1) % 100
        for name in os.listdir(os.getcwd()):
            if name.startswith(TESTFN):
                try:
                    os.unlink(name)
                except OSError:
                    pass

    def clewn_test(self, cmd, expected, outfile, *test):
        """The test method.

        arguments:
            cmd: str
                the commands sourced by vim
            expected: str
                an expected string that must be found in outfile
            outfile: str
                the output file
            test: argument list
                the content of the test files that vim is loading

        The result check ignores changes in the amount of white space
        (including new lines).

        """
        cwd = os.getcwd() + os.sep
        cmd = ':sleep ${time}\n' + cmd

        # write the commands
        fp = open(TESTFN, 'w')
        fp.write(string.Template(cmd).substitute(time=SLEEP_TIME,
                                                    test_file=TESTFN_FILE,
                                                    test_out=TESTFN_OUT,
                                                    cwd=cwd))
        fp.close()

        # write the test files
        for i, t in enumerate(test):
            fp = open(TESTFN_FILE + str(i+1), 'w')
            fp.write(t)
            fp.close()

        # process the commands
        unused = vim.main(True)

        # wait for the python script being debugged to terminate
        if self.debugged_script:
            self.debugged_script.wait()
            self.debugged_script = None
            self.fnull.close()

        # check the result
        fp = open(outfile, 'r')
        output = fp.read()
        fp.close()

        if os.name == 'nt':
            expected = expected.replace('/', '\\')
        expected = string.Template(expected).substitute(
                                            cwd=cwd, test_file=TESTFN_FILE)

        checked = ' '.join(expected.split()) in ' '.join(output.split())
        # project files on Windows do have forward slashes, and gdb may output
        # a mix of backward and forward slashes: convert also output
        if os.name == 'nt' and not checked:
            output = output.replace('/', '\\')
            checked = ' '.join(expected.split()) in ' '.join(output.split())
        self.assertTrue(checked,
                "\n\n...Expected:\n%s \n\n...Got:\n%s" % (expected, output))

    def cltest_redir(self, cmd, expected, *test):
        """Test result redirected by vim to TESTFN_OUT."""
        self.clewn_test(cmd, expected, TESTFN_OUT, *test)

    def cltest_logfile(self, cmd, expected, level, *test):
        """Test result in the log file."""
        sys.argv.append('--level=%s' % level)
        self.clewn_test(cmd, expected, LOGFILE, *test)

class TextTestResult(TestResult):
    """A test result class that prints formatted text results to a stream."""
    separator1 = '=' * 70
    separator2 = '-' * 70

    def __init__(self, stream, verbose, stop_on_error):
        """"Constructor."""
        TestResult.__init__(self)
        self.stream = stream
        self.verbose = verbose
        self.stop_on_error = stop_on_error

    def startTest(self, test):
        "Called when the given test is about to be run"
        TestResult.startTest(self, test)
        if self.verbose:
            self.stream.write(get_description(test))
            self.stream.write(' ... ')

    def addSuccess(self, test):
        "Called when a test has completed successfully"
        TestResult.addSuccess(self, test)
        if self.verbose:
            self.stream.write('ok\n')
        else:
            self.stream.write('.')

    def addError(self, test, err):
        """Called when an error has occurred."""
        TestResult.addError(self, test, err)
        if self.verbose:
            self.stream.write('ERROR\n')
        else:
            self.stream.write('E')
        if self.stop_on_error:
            self.stop()

    def addFailure(self, test, err):
        """Called when an error has occurred."""
        exctype, value, tb = err
        unused = tb
        # do not print the traceback on failure
        self.failures.append((test,
                ''.join(traceback.format_exception(exctype, value, None))))
        if self.verbose:
            self.stream.write('FAIL\n')
        else:
            self.stream.write('F')
        if self.stop_on_error:
            self.stop()

    def print_errors(self):
        """"Print the errors and failures."""
        self.stream.write('\n')
        self.print_error_list('ERROR', self.errors)
        self.print_error_list('FAIL', self.failures)

    def print_error_list(self, flavour, errors):
        """"Print the list of one flavour of errors."""
        for test, err in errors:
            self.stream.write(self.separator1)
            self.stream.write('\n%s: %s\n' % (flavour, get_description(test)))
            self.stream.write(self.separator2)
            self.stream.write('\n%s\n' % err)

class TextTestRunner(object):
    """A test runner class that prints results as they are run and a summary."""
    def __init__(self, verbose, stop_on_error, stream=sys.stderr):
        """"Constructor."""
        self.verbose = verbose
        self.stop_on_error = stop_on_error
        self.stream = stream

    def run(self, test):
        """Run the given test case or test suite."""
        result = TextTestResult(self.stream, self.verbose, self.stop_on_error)
        start = time.time()
        test(result)
        stop = time.time()
        elapsed = stop - start

        result.print_errors()

        # print the summary
        self.stream.write(result.separator2)
        run = result.testsRun
        self.stream.write('\nRan %d test%s in %.3fs\n\n' %
                            (run, run != 1 and 's' or '', elapsed))

        if not result.wasSuccessful():
            self.stream.write('FAILED (')
            failed, errored = map(len, (result.failures, result.errors))
            if failed:
                self.stream.write('failures=%d' % failed)
            if errored:
                if failed: self.stream.write(', ')
                self.stream.write('errors=%d' % errored)
            self.stream.write(')\n')
        else:
            self.stream.write('OK\n')
        return result

def run_suite(suite, verbose, stop_on_error):
    """Run the suite."""
    ClewnTestCase._verbose = verbose
    TextTestRunner(verbose, stop_on_error).run(suite)

