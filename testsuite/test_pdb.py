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

"""Test pdb.

"""
import sys
import os
import subprocess
from unittest2 import skipIf

from test_support import ClewnTestCase

use_select_emulation = ('CLEWN_PIPES' in os.environ or os.name == 'nt')

class Pdb(ClewnTestCase):
    """Test pyclewn."""

    def setUp(self):
        """Test setup."""
        ClewnTestCase.setUp(self)
        sys.argv.append('--pdb')

        # start the python script being debugged
        self.fnull = open(os.devnull, 'w')
        self.pdb_script = subprocess.Popen(
                                    ['python', './foobar.py'],
                                     stdout=self.fnull)

    def tearDown(self):
        """Cleanup stuff after the test."""
        ClewnTestCase.tearDown(self)

        # wait for the python script being debugged to terminate
        if self.pdb_script:
            self.pdb_script.wait()

    def test_001(self):
        """The buffer is automatically loaded on the interrupt command"""
        cmd = [
            'Cinterrupt',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'echo bufname("%")',
            'redir! > ${test_file}1',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'line=15  id=1  name=1',
            '${cwd}foobar.py',
            )
        self.cltest_redir(cmd, expected)

    def test_002(self):
        """The break command"""
        cmd = [
            'Cinterrupt',
            'Cbreak main',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'Cclear 1',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'line=5  id=2  name=2',
            'line=15  id=1  name=1',
            )
        self.cltest_redir(cmd, expected)

    def test_003(self):
        """The disable command"""
        cmd = [
            'Cinterrupt',
            'Cbreak ${cwd}foobar.py:5',
            'Cdisable 1',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'Cclear 1',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'line=5  id=3  name=3',
            'line=15  id=1  name=1',
            )
        self.cltest_redir(cmd, expected)

    def test_004(self):
        """The enable command"""
        cmd = [
            'Cinterrupt',
            'Cbreak ${cwd}foobar.py:5',
            'Cbreak ${cwd}foobar.py:7',
            'Cdisable 1 2',
            'Cenable 2',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'Cclear 1 2',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'line=5  id=3  name=3',
            'line=7  id=4  name=4',
            'line=15  id=1  name=1',
            )
        self.cltest_redir(cmd, expected)

    def test_005(self):
        """The clear command"""
        cmd = [
            'Cinterrupt',
            'Cbreak ${cwd}foobar.py:5',
            'Cbreak ${cwd}foobar.py:7',
            'Cbreak ${cwd}foobar.py:7',
            'Cclear ${cwd}foobar.py:5',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'Cclear 2 3',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'line=7  id=6  name=6',
            'line=7  id=4  name=4',
            'line=15  id=1  name=1',
            )
        self.cltest_redir(cmd, expected)

    def test_006(self):
        """The p command"""
        cmd = [
            'Cinterrupt',
            'Cbreak foo.foo',
            'Ccontinue',
            'Cnext',
            'Cp c.value',
            'call Wait_eop()',
            'edit (clewn)_console | $$-4,$$w! ${test_out}',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            '(Pdb) p c.value',
            '1',
            '(Pdb)',
            )
        self.cltest_redir(cmd, expected)

    def test_007(self):
        """The temporary breakpoint command"""
        cmd = [
            'Cinterrupt',
            'Ctbreak main',
            'Ccontinue',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            "line=7  id=1  name=1",
            )
        self.cltest_redir(cmd, expected)

    def test_008(self):
        """Delete a breakpoint"""
        cmd = [
            'Cinterrupt',
            'Cbreak main',
            'Cbreak main',
            'Cclear 2',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'Cclear 1',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'line=5  id=2  name=2',
            'line=15  id=1  name=1',
            )
        self.cltest_redir(cmd, expected)

    def test_009(self):
        """Setting a breakpoint opens the source file"""
        cmd = [
            'Cinterrupt',
            'Cbreak main',
            'Ccontinue',
            'Cbreak foo.foo',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'Cclear 2',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'Signs for ${cwd}foobar.py:',
            'line=5  id=2  name=2',
            'line=7  id=1  name=1',
            'Signs for ${cwd}testsuite/foo.py:',
            'line=32  id=4  name=4',
            )
        self.cltest_redir(cmd, expected)

    def test_010(self):
        """Stepping opens the source file"""
        cmd = [
            'Cinterrupt',
            'Cbreak main',
            'Ccontinue',
            'Cstep',
            'Cstep',
            'Cstep',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'Signs for ${cwd}foobar.py:',
            'line=5  id=2  name=2',
            'Signs for ${cwd}testsuite/foo.py:',
            'line=32  id=1  name=1',
            )
        self.cltest_redir(cmd, expected)

    def test_011(self):
        """Change a variable in the locals dictionary"""
        cmd = [
            'Cinterrupt',
            'Cbreak foo.foo',
            'Ccontinue',
            'C run = 123',
            'Cp run',
            'call Wait_eop()',
            'edit (clewn)_console | $$-3,$$w! ${test_out}',
            'C run = False',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            '(Pdb) p run',
            '123',
            '(Pdb)',
            )
        self.cltest_redir(cmd, expected)

    @skipIf(use_select_emulation, 'when using select emulation')
    def test_012(self):
        """Interrupting an infinite loop"""
        cmd = [
            'Cinterrupt',
            'Cbreak testsuite/foo.py:35',
            'Ccontinue',
            'C run = True',
            'C c.value = -1',
            'Ccontinue',
            'Cinterrupt',
            'Cjump 19',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'Signs for ${cwd}testsuite/foo.py:',
            'line=19  id=1  name=1',
            'line=35  id=2  name=2',
            )
        self.cltest_redir(cmd, expected)

    @skipIf(True, 'debuggee is attached')
    def test_013(self):
        """A ZeroDivisionError exception"""
        cmd = [
            'Cinterrupt',
            'Cbreak testsuite/foo.py:35',
            'Ccontinue',
            'C run = True',
            'C c.value = 0',
            'Ccontinue',
            'call Wait_eop()',
            'edit (clewn)_console | $$-7,$$w! ${test_out}',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            "ZeroDivisionError: division by zero",
            '> ?() at ${cwd}foobar.py:15',
            '  main() at ${cwd}foobar.py:9',
            "  foo(run=True, do_sleep=[], args=('unused',)) at ${cwd}testsuite/foo.py:39",
            "  bar(prefix='value', i=0) at ${cwd}testsuite/foo.py:25",
            )
        self.cltest_redir(cmd, expected)

    @skipIf(use_select_emulation, 'when using select emulation')
    def test_014(self):
        """Breakpoints are restored after detach"""
        cmd = [
            'Cinterrupt',
            'Cbreak foo.foo',
            'Ccontinue',
            'C run = True',
            'Cbreak testsuite/foo.py:39',
            'Cclear 1',
            'Cdetach',
            'Pyclewn pdb',
            'Cinterrupt',
            'Ccontinue',
            'call Wait_eop()',
            'Ccontinue',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'C run = False',
            'Ccontinue',
            'qa',
            ]
        expected = (
            'Signs for ${cwd}testsuite/foo.py:',
            'line=39  id=1  name=1',
            'line=39  id=2  name=4',
            )
        self.cltest_redir(cmd, expected)
        os.environ['PATH'] = '.:' + os.environ['PATH']

    def test_015(self):
        """The next command in the main module frame"""
        cmd = [
            'Cinterrupt',
            'Cnext',
            'Cwhere',
            'call Wait_eop()',
            'edit (clewn)_console | $$-1w! ${test_out}',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            '> ?() at ${cwd}foobar.py:16',
            )
        self.cltest_redir(cmd, expected)

    @skipIf(use_select_emulation, 'when using select emulation')
    def test_016(self):
        """Stop at breakpoint set in caller after interrupt"""
        cmd = [
            'Cinterrupt',
            'Cbreak testsuite/foo.py:35',
            'Ccontinue',
            'C run = True',
            'C c.value = -1',
            'Ccontinue',
            'Cinterrupt',
            'Cjump 19',
            'Cbreak testsuite/foo.py:40',
            'Ccontinue',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'redir! > ${test_file}1',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'Signs for ${cwd}testsuite/foo.py:',
            'line=35  id=2  name=2',
            'line=40  id=1  name=1',
            'line=40  id=4  name=4',
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
            'call Wait_eop()',
            'C run = True',
            'Ccontinue',
            'call Wait_eop()',
            'edit (clewn)_console | $$-1,$$w! ${test_out}',
            'Creturn',
            'Cnext',
            'C run = False',
            'Ccontinue',
            'qa!',
            ]
        expected = (
            'value',
            )
        self.cltest_redir(cmd, expected)

