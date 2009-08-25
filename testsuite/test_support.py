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
import unittest
import test.test_support as test_support

import clewn.vim as vim

if os.name == 'nt':
    SLEEP_TIME = '1400m'
elif os.environ.has_key('CLEWN_PIPES'):
    SLEEP_TIME = '600m'
else:
    SLEEP_TIME = '400m'
NETBEANS_PORT = 3219
LOGFILE = 'logfile'
TESTFN_FILE = test_support.TESTFN + '_file_'
TESTFN_OUT = test_support.TESTFN + '_out'

class ClewnTestCase(unittest.TestCase):
    """Pyclewn test case abstract class.

    The netbeans port changes on each run, within the interval
    [NETBEANS_PORT, NETBEANS_PORT + 99].
    In 'verbose' mode, pyclewn runs at 'nbdebug' log level and the log is
    written to LOGFILE.

    """
    __port = 0

    def setUp(self):
        """Setup pyclewn arguments."""
        port = self.__port + NETBEANS_PORT

        sys.argv = [
            '-c',                       # argv[0], a script
            '--netbeans=:%d' % port,    # netbeans port
            '--file=' + LOGFILE,
            '--cargs',                  # gvim args
            '-nb:127.0.0.1:%d:changeme '
                '-u NONE '
                '-U NONE '
                '--noplugin '
                '-s %s' % (port, test_support.TESTFN),
        ]
        if test_support.verbose:
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
        self.__class__.__port = (self.__port + 1) % 100
        for name in os.listdir(os.getcwd()):
            if name.startswith(test_support.TESTFN):
                try:
                    os.unlink(name)
                except OSError:
                    pass

    def clewn_test(self, cmd, expected, outfile, *test):
        """The test method.

        arguments:
            cmd: str
                the commands sourced by gvim
            expected: str
                an expected string that must be found in outfile
            outfile: str
                the output file
            test: argument list
                the content of the test files that gvim is loading

        The result check ignores changes in the amount of white space
        (including new lines).

        """
        unused = self
        if os.name == 'nt' or os.environ.has_key('CLEWN_PIPES'):
            # some Windows tests fail sometimes without this sleeping
            cmd = ':sleep ${time}\n' + cmd

        # write the commands
        fp = open(test_support.TESTFN, 'w')
        fp.write(string.Template(cmd).substitute(time=SLEEP_TIME,
                                                    test_file=TESTFN_FILE,
                                                    test_out=TESTFN_OUT))
        fp.close()

        # write the test files
        for i, t in enumerate(test):
            fp = open(TESTFN_FILE + str(i+1), 'w')
            fp.write(t)
            fp.close()

        # process the commands
        vim.main(True)

        # check the result
        fp = open(outfile, 'r')
        output = fp.read()
        fp.close()

        if os.name == 'nt':
            expected = expected.replace('/', '\\')
        cwd = os.getcwd() + os.sep
        expected = string.Template(expected).substitute(
                                            cwd=cwd, test_file=TESTFN_FILE)

        checked = ' '.join(expected.split()) in ' '.join(output.split())
        # project files on Windows do have forward slashes, so try with
        # forward slashes if the normal verification failed
        if os.name == 'nt' and not checked:
            expected = expected.replace('\\', '/')
            checked = ' '.join(expected.split()) in ' '.join(output.split())
        test_support.verify(checked,
                "\n\n...Expected:\n%s \n\n...Got:\n%s" % (expected, output))

    def cltest_redir(self, cmd, expected, *test):
        """Test result redirected by vim to TESTFN_OUT."""
        self.clewn_test(cmd, expected, TESTFN_OUT, *test)

    def cltest_logfile(self, cmd, expected, level, *test):
        """Test result in the log file."""
        sys.argv.append('--level=%s' % level)
        self.clewn_test(cmd, expected, LOGFILE, *test)


