# vi:set ts=8 sts=4 sw=4 et tw=80:
"""
Test pdb.
"""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from io import open

import sys
import os
import subprocess
import time
from unittest import skipIf

from clewn import PY33
from .test_support import TESTRUN_SLEEP_TIME, ClewnTestCase

class Pdb(ClewnTestCase):
    """Test pyclewn."""

    def __init__(self, *args, **kwds):
        ClewnTestCase.__init__(self, *args, **kwds)
        self.debugger = 'pdb'
        self.netbeans_port = 3220

    def setUp(self):
        ClewnTestCase.setUp(self)
        sys.argv.append('pdb')

        # start the python script being debugged
        self.fnull = open(os.devnull, 'w')
        self.pdb_script = subprocess.Popen([sys.executable, './foobar.py'],
                                           stdout=self.fnull,
                                           stderr=subprocess.PIPE,
                                           universal_newlines=True)
        # Wait for the clewn thread to be started.
        started = self.pdb_script.stderr.readline()
        time.sleep(TESTRUN_SLEEP_TIME / 1000)

    def tearDown(self):
        """Cleanup stuff after the test."""
        ClewnTestCase.tearDown(self)

        # Wait for the python script being debugged to terminate.
        if self.pdb_script:
            if PY33:
                try:
                    self.pdb_script.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    self.pdb_script.kill()
            else:
                self.pdb_script.kill()
            self.pdb_script.stderr.close()
            self.fnull.close()

    def test_001(self):
        """The buffer is automatically loaded on the interrupt command"""
        cmd = [
            'Cinterrupt',
            'sleep ${sleep_time}',
            'redir! > ${test_out}',
            'sign place',
            'echo bufname("%")',
            'redir! > ${test_file}1',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'line=21  id=1  name=1',
            '${cwd}foobar.py',
            )
        self.cltest_redir(cmd, expected)

    def test_002(self):
        """The break command"""
        cmd = [
            'Cinterrupt',
            'Cbreak main',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'Cclear 1',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'line=12  id=2  name=2',
            'line=21  id=1  name=1',
            )
        self.cltest_redir(cmd, expected)

    def test_003(self):
        """The disable command"""
        cmd = [
            'Cinterrupt',
            'Cbreak ${cwd}foobar.py:13',
            'Cdisable 1',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'Cclear 1',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'line=13  id=3  name=3',
            'line=21  id=1  name=1',
            )
        self.cltest_redir(cmd, expected)

    def test_004(self):
        """The enable command"""
        cmd = [
            'Cinterrupt',
            'Cbreak ${cwd}foobar.py:13',
            'Cbreak ${cwd}foobar.py:14',
            'Cdisable 1 2',
            'Cenable 2',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'Cclear 1 2',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'line=13  id=3  name=3',
            'line=14  id=4  name=4',
            'line=21  id=1  name=1',
            )
        self.cltest_redir(cmd, expected)

    def test_005(self):
        """The clear command"""
        cmd = [
            'Cinterrupt',
            'Cbreak ${cwd}foobar.py:13',
            'Cbreak ${cwd}foobar.py:14',
            'Cbreak ${cwd}foobar.py:14',
            'Cclear ${cwd}foobar.py:13',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'Cclear 2 3',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'line=14  id=6  name=6',
            'line=14  id=4  name=4',
            'line=21  id=1  name=1',
            )
        self.cltest_redir(cmd, expected)

    def test_006(self):
        """The p command"""
        cmd = [
            'Cinterrupt',
            'Cbreak foo.foo',
            'Ccontinue',
            'Cnext',
            'sleep ${sleep_time}',
            'Cp c.value + 1000',
            'edit (clewn)_console | $$-4,$$w! ${test_out}',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            '1001',
            )
        self.cltest_redir(cmd, expected)

    def test_007(self):
        """The temporary breakpoint command"""
        cmd = [
            'Cinterrupt',
            'Ctbreak main',
            'Ccontinue',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            "line=13  id=1  name=1",
            )
        self.cltest_redir(cmd, expected)

    def test_008(self):
        """Delete a breakpoint"""
        cmd = [
            'Cinterrupt',
            'Cbreak main',
            'Cbreak main',
            'Cclear 2',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'Cclear 1',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'line=12  id=2  name=2',
            'line=21  id=1  name=1',
            )
        self.cltest_redir(cmd, expected)

    def test_009(self):
        """Setting a breakpoint opens the source file"""
        cmd = [
            'Cinterrupt',
            'Cbreak main',
            'Ccontinue',
            'Cbreak foo.foo',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'Cclear 2',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'Signs for ${cwd}foobar.py:',
            'line=12  id=2  name=2',
            'line=13  id=1  name=1',
            'Signs for ${cwd}testsuite/foo.py:',
            'line=41  id=4  name=4',
            )
        self.cltest_redir(cmd, expected)

    def test_010(self):
        """Stepping opens the source file"""
        cmd = [
            'Cinterrupt',
            'Cstep',
            'sleep ${sleep_time}',
            'Cstep',
            'sleep ${sleep_time}',
            'Cstep',
            'sleep ${sleep_time}',
            'Cstep',
            'sleep ${sleep_time}',
            'Cstep',
            'sleep ${sleep_time}',
            'Cstep',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'Signs for ${cwd}testsuite/foo.py:',
            'line=43  id=1  name=1',
            )
        self.cltest_redir(cmd, expected)

    def test_011(self):
        """Change a variable in the locals dictionary"""
        cmd = [
            'Cinterrupt',
            'Cbreak foo.foo',
            'Ccontinue',
            'C run = 123',
            'Cp run + 1000',
            'edit (clewn)_console | $$-3,$$w! ${test_out}',
            'C run = False',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            '1123',
            )
        self.cltest_redir(cmd, expected)

    def test_012(self):
        """Interrupting an infinite loop"""
        cmd = [
            'Cinterrupt',
            'Cbreak testsuite/foo.py:44',
            'Ccontinue',
            'C run = True',
            'C c.value = -1',
            'Ccontinue',
            'Cinterrupt',
            'call Wait_eop()',
            'C i = 0',
            'Ctbreak 28',
            'Ccontinue',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'Signs for ${cwd}testsuite/foo.py:',
            'line=28  id=1  name=1',
            'line=44  id=2  name=2',
            )
        self.cltest_redir(cmd, expected)

    @skipIf(True, 'debuggee is attached')
    def test_013(self):
        """A ZeroDivisionError exception"""
        cmd = [
            'Cinterrupt',
            'Cbreak testsuite/foo.py:44',
            'Ccontinue',
            'C run = True',
            'C c.value = 0',
            'Ccontinue',
            'edit (clewn)_console | $$-7,$$w! ${test_out}',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            "ZeroDivisionError: division by zero",
            '> <module>() at ${cwd}foobar.py:15',
            '  main() at ${cwd}foobar.py:9',
            "  foo(run=True, do_sleep=[], args=('unused',)) at ${cwd}testsuite/foo.py:39",
            "  bar(prefix='value', i=0) at ${cwd}testsuite/foo.py:25",
            )
        self.cltest_redir(cmd, expected)

    def test_014(self):
        """Breakpoints are restored after detach"""
        cmd = [
            'Cinterrupt',
            'Cbreak foo.foo',
            'Ccontinue',
            'C run = True',
            'Cbreak testsuite/foo.py:48',
            'Cclear 1',
            'Cdetach',
            'let pyclewn_python = "%s"' % sys.executable,
            'Pyclewn pdb',
            'Cinterrupt',
            'Cinterrupt',
            'Ccontinue',
            'sleep ${sleep_time}',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'C run = False',
            'Ccontinue',
            'qa',
            ]
        expected = (
            'Signs for ${cwd}testsuite/foo.py:',
            'line=48  id=1  name=1',
            'line=48  id=2  name=4',
            )
        self.cltest_redir(cmd, expected)
        os.environ['PATH'] = '.:' + os.environ['PATH']

    def test_015(self):
        """The next command in the main module frame"""
        cmd = [
            'Cinterrupt',
            'Cnext',
            'sleep ${sleep_time}',
            'Cwhere',
            'edit (clewn)_console | $$-1w! ${test_out}',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            '> <module>() at ${cwd}foobar.py:22',
            )
        self.cltest_redir(cmd, expected)

    def test_016(self):
        """Stop at breakpoint set in caller after interrupt"""
        cmd = [
            'Cinterrupt',
            'Cbreak testsuite/foo.py:44',
            'Ccontinue',
            'C run = True',
            'C c.value = -1',
            'Ccontinue',
            'Cinterrupt',
            'call Wait_eop()',
            'C i = 0',
            'Cbreak testsuite/foo.py:49',
            'Ccontinue',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'Signs for ${cwd}testsuite/foo.py:',
            'line=44  id=2  name=2',
            'line=49  id=1  name=1',
            'line=49  id=4  name=4',
            )
        self.cltest_redir(cmd, expected)

    def test_017(self):
        """The commands command"""
        cmd = [
            'Cinterrupt',
            'Cbreak foo.foo',
            'Ccontinue',
            'Cbreak bar',
            'Ccommands 2',
            'C silent',
            'C print(prefix)',
            'C end',
            'C run = True',
            'Ccontinue',
            'edit (clewn)_console | $$-2,$$w! ${test_out}',
            'Creturn',
            'Cnext',
            'sleep ${sleep_time}',
            'C run = False',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'value',
            )
        self.cltest_redir(cmd, expected)

