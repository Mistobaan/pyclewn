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
# $Id: test_support.py 193 2007-12-08 21:04:22Z xavier $

"""Supporting definitions for the pyclewn regression tests."""

import sys
import os
import string
import unittest
from test.test_support import TESTFN, verify, verbose

import clewn.dispatcher

SLEEP_TIME = '100m'
NETBEANS_PORT = 3219
LOGFILE = 'logfile'
TESTFN_FILE = TESTFN + '_file_'
TESTFN_OUT = TESTFN + '_out'

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
                '-s %s' % (port, TESTFN),
        ]
        if verbose:
            sys.argv.append('--level=nbdebug')

    def tearDown(self):
        self.__class__.__port = (self.__port + 1) % 100
        for name in os.listdir(os.getcwd()):
            if name.startswith(TESTFN):
                try:
                    os.unlink(name)
                except:
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

        # write the commands
        fp = open(TESTFN, 'w')
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
        clewn.dispatcher.main()

        # check the result
        fp = open(outfile, 'r')
        output = fp.read()
        fp.close()

        cwd = os.getcwd() + os.sep
        expected = string.Template(expected).substitute(
                                            cwd=cwd, test_file=TESTFN_FILE)

        verify(' '.join(expected.split()) in ' '.join(output.split()),
                "\n\n...Expected:\n%s \n\n...Got:\n%s" % (expected, output))

    def cltest_redir(self, cmd, expected, *test):
        """Test result redirected by vim to TESTFN_OUT."""
        self.clewn_test(cmd, expected, TESTFN_OUT, *test)

    def cltest_logfile(self, cmd, expected, level, *test):
        """Test result in the log file."""
        sys.argv.append('--level=%s' % level)
        self.clewn_test(cmd, expected, LOGFILE, *test)


