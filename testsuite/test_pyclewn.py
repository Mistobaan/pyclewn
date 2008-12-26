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

"""Test pyclewn.

"""
import sys
import unittest
from test.test_support import run_unittest

import clewn.debugger.simple
from testsuite.test_support import ClewnTestCase

class PyclewnTestCase(ClewnTestCase):
    """Test pyclewn."""

    def setUp(self):
        """Test setup."""
        ClewnTestCase.setUp(self)
        sys.argv.append('--simple')

    def test_breakloadbuffer(self):
        """The buffer is automatically loaded on a break command"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cbreak ${test_file}2:1\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':echo bufname("%")\n'
            ':qa!\n',

            'line=1  id=1  name=1\n'
            '${cwd}${test_file}2',

            'line 1\n',

            'line 1\n'
            )

    def test_steploadbuffer(self):
        """The buffer is automatically loaded on a step command"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cbreak ${test_file}1:2\n'
            ':edit ${test_file}2\n'
            ':sleep ${time}\n'
            ':Cstep\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':echo bufname("%")\n'
            ':qa!\n',

            'line=1  id=2  name=3\n'
            'line=2  id=1  name=1\n'
            '${test_file}1',

            'line 1\n'
            'line 2\n',

            'line 1\n'
            )

    def test_wipeout(self):
        """The breakpoint and frame signs are restored after a wipeout"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cbreak ${test_file}1:2\n'
            ':sleep ${time}\n'
            ':edit ${test_file}2:1\n'
            ':sleep ${time}\n'
            ':1bwipeout\n'
            ':Cstep\n'
            ':sleep ${time}\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':echo bufname("%")\n'
            ':qa!\n',

            'line=1  id=2  name=3\n'
            'line=2  id=1  name=1\n'
            '${cwd}${test_file}1',

            'line 1\n'
            'line 2\n',

            'line 1\n'
            )

    def test_restart(self):
        """The simple application can be restarted"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cbreak ${test_file}1:1\n'
            ':Cquit\n'
            ':sleep ${time}\n'
            ':Cbreak ${test_file}1:2\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$-1w! ${test_out}\n'
            ':redir! >> ${test_out}\n'
            ':sign place\n'
            ':qa!\n',

            'Breakpoint 1 at file ${cwd}${test_file}1, line 2.\n'
            '--- Signs ---\n'
            'Signs for ${test_file}1:\n'
            '    line=2  id=2  name=1\n',

            'line 1\n'
            'line 2\n'
            )

    def test_cmdlist(self):
        """The list of commands is complete"""
        self.cltest_redir(
            ':redir! >> ${test_out}\n'
            ':command C\n'
            ':qa!\n',

            'Name        Args Range Complete  Definition\n'
            'C           *          custom    call s:nbcommand("", <f-args>)\n'
            'Cbreak      *          file      call s:nbcommand("break", <f-args>)\n'
            'Cclear      *          file      call s:nbcommand("clear", <f-args>)\n'
            'Ccontinue   *                    call s:nbcommand("continue", <f-args>)\n'
            'Cdbgvar     *                    call s:nbcommand("dbgvar", <f-args>)\n'
            'Cdelvar     *                    call s:nbcommand("delvar", <f-args>)\n'
            'Cdisable    *                    call s:nbcommand("disable", <f-args>)\n'
            'Cdumprepr   *                    call s:nbcommand("dumprepr", <f-args>)\n'
            'Cenable     *                    call s:nbcommand("enable", <f-args>)\n'
            'Chelp       *                    call s:nbcommand("help", <f-args>)\n',
            'Cinterrupt  *                    call s:nbcommand("interrupt", <f-args>)\n'
            'Cmapkeys    *                    call s:nbcommand("mapkeys", <f-args>)\n'
            'Cprint      *                    call s:nbcommand("print", <f-args>)\n'
            'Cquit       *                    call s:nbcommand("quit", <f-args>)\n'
            'Csigint     *                    call s:nbcommand("sigint", <f-args>)\n',
            'Cstep       *                    call s:nbcommand("step", <f-args>)\n'
            'Csymcompletion *                 call s:nbcommand("symcompletion", <f-args>)\n'
            'Cunmapkeys  0                    call s:unmapkeys()\n'
            )

    def test_mapkeys(self):
        """The simple keys are mapped"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cmapkeys\n'
            ':sleep ${time}\n'
            ':redir! >> ${test_out}\n'
            ':map <C-B> \n'
            ':map <C-E> \n'
            ':map <C-P>\n'
            ':map <C-Z>\n'
            ':map <S-C>\n'
            ':map <S-Q>\n'
            ':map <S-S>\n'
            ':qa!\n',

            'n  <C-B>         :nbkey C-B<CR>\n'
            'n  <C-E>         :nbkey C-E<CR>\n'
            'n  <C-P>         :nbkey C-P<CR>\n'
            'n  <C-Z>         :nbkey C-Z<CR>\n'
            'n  <S-C>         :nbkey S-C<CR>\n'
            'n  <S-Q>         :nbkey S-Q<CR>\n'
            'n  <S-S>         :nbkey S-S<CR>\n',

            'line 1\n'
            )

    def test_delconsole(self):
        """The bdelete Vim command on the clewn console"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cbreak ${test_file}1:1\n'
            ':sleep ${time}\n'
            ':bdelete (clewn)_console\n'
            ':Cquit\n'
            ':sleep ${time}\n'
            ':Cbreak ${test_file}1:2\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$-2,$$-1w! ${test_out}\n'
            ':qa!\n',

            '(simple) break ${test_file}1:2\n'
            'Breakpoint 1 at file ${cwd}${test_file}1, line 2.\n',

            'line 1\n'
            'line 2\n'
            )

def test_main():
    """Run all the tests."""
    suite = unittest.TestSuite()
    suite.addTest(PyclewnTestCase('test_breakloadbuffer'))
    suite.addTest(PyclewnTestCase('test_steploadbuffer'))
    suite.addTest(PyclewnTestCase('test_wipeout'))
    suite.addTest(PyclewnTestCase('test_restart'))
    suite.addTest(PyclewnTestCase('test_cmdlist'))
    suite.addTest(PyclewnTestCase('test_mapkeys'))
    suite.addTest(PyclewnTestCase('test_delconsole'))
    run_unittest(suite)

if __name__ == "__main__":
    test_main()

