# vi:set ts=8 sts=4 sw=4 et tw=80:
"""
Test pyclewn.
"""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import sys
import os
from unittest import skipIf

from .test_support import ClewnTestCase

class Pyclewn(ClewnTestCase):
    """Test pyclewn."""

    def __init__(self, *args, **kwds):
        ClewnTestCase.__init__(self, *args, **kwds)
        self.debugger = 'simple'
        self.netbeans_port = 3221

    def setUp(self):
        ClewnTestCase.setUp(self)
        sys.argv.append('simple')

    @skipIf(True, 'test cancelled')
    def test_001(self):
        """The buffer is automatically loaded on a break command"""
        cmd = [
            'edit ${test_file}1',
            'Cbreak ${test_file}2:1',
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
            'Cbreak ${test_file}1:2',
            'edit ${test_file}2',
            'Cstep',
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
            'C           *          custom    call s:nbcommand("", <f-args>)',
            'Cballooneval *                   call s:nbcommand("ballooneval", <f-args>)',
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
            'redir! >> ${test_out}',
            'map <C-B> ',
            'map <C-K> ',
            'map <C-P>',
            'map <C-Z>',
            'qa!',
            ]
        expected = (
            'n  <C-B>         :nbkey C-B<CR>',
            'n  <C-K>         :nbkey C-K<CR>',
            'n  <C-P>         :nbkey C-P<CR>',
            'n  <C-Z>         :nbkey C-Z<CR>',
            )
        self.cltest_redir(cmd, expected, 'line 1\n')

    def test_007(self):
        """The bdelete Vim command on the clewn console"""
        cmd = [
            'edit ${test_file}1',
            'Cbreak ${test_file}1:1',
            'bdelete (clewn)_console',
            'Cquit',
            'Cbreak ${test_file}1:2',
            'edit (clewn)_console | $$-2,$$-1w! ${test_out}',
            'qa!',
            ]
        expected = (
            'break ${test_file}1:2',
            'Breakpoint 1 at file ${cwd}${test_file}1, line 2.',
            )
        self.cltest_redir(cmd, expected, 'line 1\nline 2\n')

