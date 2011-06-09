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
import unittest
import testsuite.test_support as test_support

from .test_support import ClewnTestCase

class PdbTestCase(ClewnTestCase):
    """Test pyclewn."""

    def setUp(self):
        """Test setup."""
        # use always the same netbeans port
        self._port = 0
        ClewnTestCase.setUp(self)
        sys.argv.append('--pdb')

        # start the python script being debugged
        self.fnull = open(os.devnull, 'w')
        self.debugged_script = subprocess.Popen(
                                    ['python3', './foobar.py'],
                                     stdout=self.fnull)

    def test_intr_load_buffer(self):
        """The buffer is automatically loaded on the interrupt command"""
        self.cltest_redir(
            ':Cinterrupt\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':echo bufname("%")\n'
            ':redir! > ${test_file}1\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':qa!\n',

            'line=13  id=1  name=1\n'
            '${cwd}foobar.py',
            )

    def test_break(self):
        """The break command"""
        self.cltest_redir(
            ':Cinterrupt\n'
            ':sleep ${time}\n'
            ':Cbreak main\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':redir! > ${test_file}1\n'
            ':Cclear 1\n'
            ':sleep ${time}\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':qa!\n',

            'line=5  id=2  name=2\n'
            'line=13  id=1  name=1\n',
            )

    def test_disable(self):
        """The disable command"""
        self.cltest_redir(
            ':Cinterrupt\n'
            ':sleep ${time}\n'
            ':Cbreak ${cwd}foobar.py:5\n'
            ':Cdisable 1\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':redir! > ${test_file}1\n'
            ':Cclear 1\n'
            ':sleep ${time}\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':qa!\n',

            'line=5  id=3  name=3\n'
            'line=13  id=1  name=1\n',
            )

    def test_enable(self):
        """The enable command"""
        self.cltest_redir(
            ':Cinterrupt\n'
            ':sleep ${time}\n'
            ':Cbreak ${cwd}foobar.py:5\n'
            ':Cbreak ${cwd}foobar.py:7\n'
            ':Cdisable 1 2\n'
            ':Cenable 2\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':redir! > ${test_file}1\n'
            ':Cclear 1 2\n'
            ':sleep ${time}\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':qa!\n',

            'line=5  id=3  name=3\n'
            'line=7  id=4  name=4\n'
            'line=13  id=1  name=1\n',
            )

    def test_clear(self):
        """The clear command"""
        self.cltest_redir(
            ':Cinterrupt\n'
            ':sleep ${time}\n'
            ':Cbreak ${cwd}foobar.py:5\n'
            ':Cbreak ${cwd}foobar.py:7\n'
            ':Cbreak ${cwd}foobar.py:7\n'
            ':Cclear ${cwd}foobar.py:5\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':redir! > ${test_file}1\n'
            ':Cclear 2 3\n'
            ':sleep ${time}\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':qa!\n',

            'line=7  id=6  name=6\n'
            'line=7  id=4  name=4\n'
            'line=13  id=1  name=1\n',
            )

    def test_p_command(self):
        """The p command"""
        self.cltest_redir(
            ':Cinterrupt\n'
            ':sleep ${time}\n'
            ':Cbreak foo.foo\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':Cnext\n'
            ':sleep ${time}\n'
            ':Cp c.value\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$-3,$$w! ${test_out}\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':qa!\n',

            '(pdb) p c.value\n'
            '1\n'
            '(pdb)\n',
            )

    def test_temporary_breakpoint(self):
        """The temporary breakpoint command"""
        self.cltest_redir(
            ':Cinterrupt\n'
            ':sleep ${time}\n'
            ':Ctbreak main\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':redir! > ${test_file}1\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':qa!\n',

            "line=7  id=1  name=1\n"
            )

    def test_delete_bp(self):
        """Delete a breakpoint"""
        self.cltest_redir(
            ':Cinterrupt\n'
            ':sleep ${time}\n'
            ':Cbreak main\n'
            ':Cbreak main\n'
            ':Cclear 2\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':redir! > ${test_file}1\n'
            ':Cclear 1\n'
            ':sleep ${time}\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':qa!\n',

            'line=5  id=2  name=2\n'
            'line=13  id=1  name=1\n',
            )

    def test_bp_open_file(self):
        """Setting a breakpoint opens the source file"""
        self.cltest_redir(
            ':Cinterrupt\n'
            ':sleep ${time}\n'
            ':Cbreak main\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':Cbreak foo.foo\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':redir! > ${test_file}1\n'
            ':Cclear 2\n'
            ':sleep ${time}\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':qa!\n',

            'Signs for ${cwd}foobar.py:\n'
            'line=5  id=2  name=2\n'
            'line=7  id=1  name=1\n'
            'Signs for ${cwd}testsuite/foo.py:\n'
            'line=32  id=4  name=4\n',
            )

    def test_frame_open_file(self):
        """Stepping opens the source file"""
        self.cltest_redir(
            ':Cinterrupt\n'
            ':sleep ${time}\n'
            ':Cbreak main\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':Cstep\n'
            ':sleep ${time}\n'
            ':Cstep\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':redir! > ${test_file}1\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':qa!\n',

            'Signs for ${cwd}foobar.py:\n'
            'line=5  id=2  name=2\n'
            'Signs for ${cwd}testsuite/foo.py:\n'
            'line=32  id=1  name=1\n',
            )

    def test_locals_change(self):
        """Change a variable in the locals dictionary"""
        self.cltest_redir(
            ':Cinterrupt\n'
            ':sleep ${time}\n'
            ':Cbreak foo.foo\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':C run = 123\n'
            ':sleep ${time}\n'
            ':Cp run\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$-3,$$w! ${test_out}\n'
            ':C run = False\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':qa!\n',

            '(pdb) p run\n'
            '123\n'
            '(pdb)\n',
            )

    def test_infinite_loop(self):
        """Interrupting an infinite loop"""
        self.cltest_redir(
            ':sleep ${time}\n'
            ':Cinterrupt\n'
            ':sleep ${time}\n'
            ':Cbreak ${cwd}testsuite/foo.py:35\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':C run = True\n'
            ':C c.value = -1\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':Cinterrupt\n'
            ':sleep ${time}\n'
            ':Cjump 19\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':redir! > ${test_file}1\n'
            ':Cbreak ${cwd}testsuite/foo.py:39\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':C run = False\n'
            ':sleep ${time}\n'
            ':Ccontinue\n'
            ':qa!\n',

            'Signs for ${cwd}testsuite/foo.py:\n'
            'line=19  id=1  name=1\n'
            'line=35  id=2  name=2\n',
            )

    def test_zero_division(self):
        """A ZeroDivisionError exception"""
        self.cltest_redir(
            ':Cinterrupt\n'
            ':sleep ${time}\n'
            ':Cbreak ${cwd}testsuite/foo.py:35\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':C run = True\n'
            ':C c.value = 0\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$-6,$$w! ${test_out}\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':qa!\n',

            '(pdb) continue\n'
            "An exception occured: ('ZeroDivisionError:', \"'int division or modulo by zero'\")\n"
            '> <module>() at ${cwd}foobar.py:13\n'
            '  main() at ${cwd}foobar.py:8\n'
            "  foo(run=True, args=('unused',)) at ${cwd}testsuite/foo.py:38\n"
            "  bar(prefix='value', i=0) at ${cwd}testsuite/foo.py:25\n"
            '(pdb)\n',
            )

    def test_bp_restored_after_detach(self):
        """Breakpoints are restored after detach"""
        self.cltest_redir(
            ':Cinterrupt\n'
            ':sleep ${time}\n'
            ':Cbreak foo.foo\n'
            ':sleep ${time}\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':C run = True\n'
            ':sleep ${time}\n'
            ':Cbreak ${cwd}testsuite/foo.py:38\n'
            ':sleep ${time}\n'
            ':Cclear 1\n'
            ':sleep ${time}\n'
            ':Cdetach\n'
            ':sleep ${time}\n'
            ':Pyclewn pdb\n'
            ':sleep ${time}\n'
            ':Cinterrupt\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':redir! > ${test_file}1\n'
            ':C run = False\n'
            ':sleep ${time}\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':qa\n',

            'Signs for ${cwd}testsuite/foo.py:\n'
            'line=38  id=8  name=1\n'
            'line=38  id=6  name=4\n',
            )

def test_main():
    """Run all the tests."""
    suite = unittest.TestSuite()
    suite.addTest(PdbTestCase('test_intr_load_buffer'))
    suite.addTest(PdbTestCase('test_break'))
    suite.addTest(PdbTestCase('test_disable'))
    suite.addTest(PdbTestCase('test_enable'))
    suite.addTest(PdbTestCase('test_clear'))
    suite.addTest(PdbTestCase('test_p_command'))
    suite.addTest(PdbTestCase('test_temporary_breakpoint'))
    suite.addTest(PdbTestCase('test_delete_bp'))
    suite.addTest(PdbTestCase('test_bp_open_file'))
    suite.addTest(PdbTestCase('test_frame_open_file'))
    suite.addTest(PdbTestCase('test_locals_change'))
    suite.addTest(PdbTestCase('test_infinite_loop'))
    suite.addTest(PdbTestCase('test_zero_division'))
    suite.addTest(PdbTestCase('test_bp_restored_after_detach'))
    test_support.run_suite(suite)

if __name__ == "__main__":
    test_main()

