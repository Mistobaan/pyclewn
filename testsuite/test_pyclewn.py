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

"""Test pyclewn.

"""
import sys
import os
from unittest2 import skipIf

from test_support import ClewnTestCase

class Pyclewn(ClewnTestCase):
    """Test pyclewn."""

    def setUp(self):
        """Test setup."""
        ClewnTestCase.setUp(self)
        sys.argv.append('--simple')

    @skipIf(True, 'test cancelled')
    def test_001(self):
        """The buffer is automatically loaded on a break command"""
        cmd = [
            'edit ${test_file}1',
            'Cbreak ${test_file}2:1',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'echo bufname("%")',
            'qa!',
            ]
        expected = (
            'line=1  id=1  name=1',
            '${cwd}${test_file}2',
            )
        self.cltest_redir(cmd, expected, 'line 1\n', 'line 1\n')

    def test_002(self):
        """The buffer is automatically loaded on a step command"""
        cmd = [
            'edit ${test_file}1',
            'Cbreak ${test_file}1:2',
            'edit ${test_file}2',
            'Cstep',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            'line=1  id=1  name=3',
            'line=2  id=2  name=1',
            )
        self.cltest_redir(cmd, expected, 'line 1\nline 2\n', 'line 1\n')

    def test_003(self):
        """The breakpoint and frame signs are restored after a wipeout"""
        cmd = [
            'edit ${test_file}1',
            'Cbreak ${test_file}1:2',
            'edit ${test_file}2',
            '1bwipeout',
            'Cstep',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'echo bufname("%")',
            'qa!',
            ]
        expected = (
            'line=1  id=1  name=3',
            'line=2  id=2  name=1',
            '${cwd}${test_file}1',
            )
        self.cltest_redir(cmd, expected, 'line 1\nline 2\n', 'line 1\n')

    def test_004(self):
        """The simple debugger can be restarted"""
        cmd = [
            'edit ${test_file}1',
            'Cbreak ${test_file}1:1',
            'Cquit',
            'Cbreak ${test_file}1:2',
            'call Wait_eop()',
            'edit (clewn)_console | $$-1w! ${test_out}',
            'redir! >> ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            'Breakpoint 1 at file ${cwd}${test_file}1, line 2.',
            '--- Signs ---',
            'Signs for ${test_file}1:',
            '    line=2  id=2  name=1',
            )
        self.cltest_redir(cmd, expected, 'line 1\nline 2\n')

    def test_005(self):
        """The list of commands is complete"""
        cmd = [
            'redir! >> ${test_out}',
            'command C',
            'qa!',
            ]
        expected = (
            'Name        Args Range Complete  Definition',
            'C           *          custom    call s:nbcommand("", <f-args>)',
            'Cbreak      *          file      call s:nbcommand("break", <f-args>)',
            'Ccontinue   *                    call s:nbcommand("continue", <f-args>)',
            'Cdbgvar     *                    call s:nbcommand("dbgvar", <f-args>)',
            'Cdelvar     *                    call s:nbcommand("delvar", <f-args>)',
            'Cdisable    *                    call s:nbcommand("disable", <f-args>)',
            'Cdumprepr   *                    call s:nbcommand("dumprepr", <f-args>)',
            'Cenable     *                    call s:nbcommand("enable", <f-args>)',
            'Chelp       *                    call s:nbcommand("help", <f-args>)',
            'Cinterrupt  *                    call s:nbcommand("interrupt", <f-args>)',
            'Cloglevel   *          custom    call s:nbcommand("loglevel", <f-args>)',
            'Cmapkeys  0                      call s:mapkeys()',
            'Cprint      *                    call s:nbcommand("print", <f-args>)',
            'Cquit       *                    call s:nbcommand("quit", <f-args>)',
            'Csigint     *                    call s:nbcommand("sigint", <f-args>)',
            'Cstep       *                    call s:nbcommand("step", <f-args>)',
            'Csymcompletion *                 call s:nbcommand("symcompletion", <f-args>)',
            'Cunmapkeys  0                    call s:unmapkeys()',
            )
        self.cltest_redir(cmd, expected)

    def test_006(self):
        """The simple keys are mapped"""
        cmd = [
            'edit ${test_file}1',
            'Cmapkeys',
            'call Wait_eop()',
            'redir! >> ${test_out}',
            'map <C-B> ',
            'map <C-E> ',
            'map <C-P>',
            'map <C-Z>',
            'map <S-C>',
            'map <S-Q>',
            'map <S-S>',
            'qa!',
            ]
        expected = (
            'n  <C-B>         :nbkey C-B<CR>',
            'n  <C-E>         :nbkey C-E<CR>',
            'n  <C-P>         :nbkey C-P<CR>',
            'n  <C-Z>         :nbkey C-Z<CR>',
            'n  <S-C>         :nbkey S-C<CR>',
            'n  <S-Q>         :nbkey S-Q<CR>',
            'n  <S-S>         :nbkey S-S<CR>',
            )
        self.cltest_redir(cmd, expected, 'line 1\n')

    @skipIf(True, 'test cancelled')
    def test_007(self):
        """The bdelete Vim command on the clewn console"""
        cmd = [
            'edit ${test_file}1',
            'Cbreak ${test_file}1:1',
            'bdelete (clewn)_console',
            'Cquit',
            'Cbreak ${test_file}1:2',
            'call Wait_eop()',
            'edit (clewn)_console | $$-2,$$-1w! ${test_out}',
            'qa!',
            ]
        expected = (
            'break ${test_file}1:2',
            'Breakpoint 1 at file ${cwd}${test_file}1, line 2.',
            )
        self.cltest_redir(cmd, expected, 'line 1\nline 2\n')

    def test_008(self):
        """There is only one console after a chdir"""
        cmd = [
            'edit ${test_file}1',
            'Cbreak ${test_file}1:1',
            'call Wait_eop()',
            'wincmd k',
            'quit',
            'cd testsuite',
            'Cstep',
            'cd ..',
            'call Wait_eop()',
            'edit ${test_file}2',
            'redir! > ${test_out}',
            'ls',
            'qa!',
            ]
        expected = (
            '1 #    "${test_file}1"                 line 1',
            '2  a=  "(clewn)_console"               line 1',
            '3 %a   "${test_file}2"                 line 1',

            )
        self.cltest_redir(cmd, expected, 'line 1\nline 2\n')

