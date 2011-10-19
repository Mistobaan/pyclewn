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

"""Test the simple debugger.

"""
import os
import sys
import os.path
from unittest2 import skipIf

from test_support import ClewnTestCase

use_select_emulation = ('CLEWN_PIPES' in os.environ or os.name == 'nt')

class Simple(ClewnTestCase):
    """Test the Simple commands."""

    def setUp(self):
        """Test setup."""
        ClewnTestCase.setUp(self)
        sys.argv.append('--simple')


    def test_001(self):
        """The break command"""
        cmd = [
            'edit ${test_file}1',
            'Cbreak ${test_file}1:1',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            'line=1  id=2  name=1',
            )
        self.cltest_redir(cmd, expected, 'line 1\n')

    def test_002(self):
        """The continue command"""
        cmd = [
            'edit ${test_file}1',
            'Cbreak ${test_file}1:1',
            'Ccontinue',
            'Cdumprepr',
            'call Wait_eop()',
            'edit (clewn)_console | $$ | ?\'inferior\': Target:?w! ${test_out}',
            'qa!',
            ]
        expected = (
            "'inferior': Target: {'running': True, 'closed': False}",
            )
        self.cltest_redir(cmd, expected, 'line 1\n')

    def test_003(self):
        """The dbgvar command"""
        cmd = [
            'edit ${test_file}1',
            'Cbreak ${test_file}1:1',
            'Cdbgvar testvar value',
            'Cdbgvar second value',
            'Cdbgvar last value',
            'Cstep',
            'Cstep',
            'Cstep',
            'Cstep',
            'Cstep',
            'call Wait_eop()',
            'edit (clewn)_dbgvar | w! ${test_out}',
            'qa!',
            ]
        expected = (
            '     testvar ={=} 3',
            '      second ={*} 3',
            '        last ={=} 2',
            )
        self.cltest_redir(cmd, expected, 'line 1\n')

    def test_004(self):
        """The delvar command"""
        cmd = [
            'edit ${test_file}1',
            'Cdbgvar testvar value',
            'Cdelvar',
            'Cdelvar unknown',
            'Cdelvar testvar',
            'call Wait_eop()',
            'edit (clewn)_console | $$-7,$$-1w! ${test_out}',
            'edit (clewn)_dbgvar',
            'redir! >> ${test_out}',
            'file',
            'qa!',
            ]
        expected = (
            '(simple) delvar',
            'Invalid arguments.',
            '(simple) delvar unknown',
            '"unknown" not found.',
            '(simple) delvar testvar',
            '"(clewn)_dbgvar" [readonly] --No lines in buffer--',
            )
        self.cltest_redir(cmd, expected, 'line 1\n')

    def test_005(self):
        """The disable command"""
        cmd = [
            'edit ${test_file}1',
            'Cbreak ${test_file}1:1',
            'Cdisable 1',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            'line=1  id=3  name=2',
            )
        self.cltest_redir(cmd, expected, 'line 1\n')

    def test_006(self):
        """The dumprepr command"""
        cmd = [
            'edit ${test_file}1',
            'Cdumprepr',
            'call Wait_eop()',
            'edit (clewn)_console | $$ | ?\'_bset\'?,?\'lnum\'?w!  ${test_out}',
            'qa!',
            ]
        expected = (
            " 'bp_id': 0,",
            " 'closed': False,",
            " 'inferior': Target: {'running': False, 'closed': False},",
            " 'lnum': 0,",
            )
        self.cltest_redir(cmd, expected, 'line 1\n')

    def test_007(self):
        """The enable command"""
        cmd = [
            'edit ${test_file}1',
            'Cbreak ${test_file}1:1',
            'Cbreak ${test_file}1:2',
            'Cdisable 1',
            'Cdisable 2',
            'Cenable 2',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            'line=1  id=3  name=2',
            'line=2  id=4  name=3',
            )
        self.cltest_redir(cmd, expected, 'line 1\nline 2\n')

    def test_008(self):
        """The help command"""
        cmd = [
            'edit ${test_file}1',
            'Chelp',
            'call Wait_eop()',
            'edit (clewn)_console | $$ | ?(simple) help?+1,$$-1w!  ${test_out}',
            'qa!',
            ]
        expected = (
            'break -- Set a breakpoint at a specified line.',
            'continue -- Continue the program being debugged, also used to start the program.',
            'dbgvar -- Add a variable to the debugger variable buffer.',
            'delvar -- Delete a variable from the debugger variable buffer.',
            'disable -- Disable one breakpoint.',
            'dumprepr -- Print debugging information on netbeans and the debugger.',
            'enable -- Enable one breakpoint.',
            'help -- Print help on the simple commands.',
            'interrupt -- Interrupt the execution of the debugged program.',
            'loglevel -- Get or set the pyclewn log level.',
            'mapkeys -- Map the pyclewn keys.',
            'print -- Print a value.',
            'quit -- Quit the current simple session.',
            'sigint -- Send a <C-C> character to the debugger (not implemented).',
            'step -- Step program until it reaches a different source line.',
            'symcompletion -- Populate the break and clear commands with symbols completion (not implemented).',
            'unmapkeys -- Unmap the pyclewn keys.',
            )
        self.cltest_redir(cmd, expected, 'line 1\n')

    def test_009(self):
        """The interrupt command"""
        cmd = [
            'edit ${test_file}1',
            'Cbreak ${test_file}1:1',
            'Ccontinue',
            'Cdumprepr',
            'call Wait_eop()',
            'edit (clewn)_console | $$ | ?\'inferior\': Target:?w! ${test_out}',
            'Cinterrupt',
            'Cdumprepr',
            'call Wait_eop()',
            'edit (clewn)_console | $$ | ?\'inferior\': Target:?w! >> ${test_out}',
            'qa!',
            ]
        expected = (
            "'inferior': Target: {'running': True, 'closed': False},",
            "'inferior': Target: {'running': False, 'closed': False},",
            )
        self.cltest_redir(cmd, expected, 'line 1\n')

    def test_010(self):
        """The mapkeys command"""
        cmd = [
            'edit ${test_file}1',
            'Cmapkeys',
            'call Wait_eop()',
            'edit (clewn)_console | $$ | ?mapkeys?,$$-1w!  ${test_out}',
            'qa!',
            ]
        expected = (
            "  C-B : break $${fname}:$${lnum} # set breakpoint at current line",
            "  C-E : clear $${fname}:$${lnum} # clear breakpoint at current line",
            "  C-P : print $${text}           # print value of selection at mouse position",
            "  C-Z : interrupt                # interrupt the execution of the target",
            "  S-C : continue",
            "  S-Q : quit",
            "  S-S : step",
            )
        self.cltest_redir(cmd, expected, 'line 1\n')

    def test_011(self):
        """The print command"""
        cmd = [
            'edit ${test_file}1',
            'Cprint foobar',
            'call Wait_eop()',
            'edit (clewn)_console | $$-2w! ${test_out}',
            'qa!',
            ]
        expected = (
            'foobar',
            )
        self.cltest_redir(cmd, expected, 'line 1\n')

    def test_012(self):
        """The step command"""
        cmd = [
            'edit ${test_file}1',
            'Cbreak ${test_file}1:2',
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
        self.cltest_redir(cmd, expected, 'line 1\nline 2\n')

    def test_013(self):
        """The unmapkeys command"""
        cmd = [
            'edit ${test_file}1',
            'Cmapkeys',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'Cunmapkeys',
            'map <C-B>',
            'qa!',
            ]
        expected = (
            'No mapping found',
            )
        self.cltest_redir(cmd, expected, 'line 1\n')

    @skipIf(use_select_emulation, 'when using select emulation')
    def test_014(self):
        """Maximum number of lines in the console buffer"""
        sys.argv.extend(['--maxlines=70'])
        cmd = [
            'edit ${test_file}1',
            'let index = 0',
            'while index < 50',
            '  let index = index + 1',
            '  Cmapkeys',
            'endwhile',
            'call Wait_eop()',
            'edit (clewn)_console | $$',
            'redir! > ${test_out}',
            'file',
            'qa!',
            ]
        expected = (
            # Cmapkeys outputs 8 lines, thus: 9 * 8 + 1 = 73 lines
            '"(clewn)_console" [readonly] line 73 of 73',
            )
        self.cltest_redir(cmd, expected)

    def test_015(self):
        """The first command on a file loaded at startup succeeds"""
        self.setup_vim_arg("testsuite/foobar.c")
        cmd = [
            'Chelp',
            'call Wait_eop()',
            'edit (clewn)_console | $$',
            'w! ${test_out}',
            'qa!',
            ]
        expected = (
            '(simple) help',
            'break -- Set a breakpoint at a specified line.',
            'continue -- Continue the program being debugged, also used to start the program.',
            'dbgvar -- Add a variable to the debugger variable buffer.',
            'delvar -- Delete a variable from the debugger variable buffer.',
            'disable -- Disable one breakpoint.',
            'dumprepr -- Print debugging information on netbeans and the debugger.',
            'enable -- Enable one breakpoint.',
            'help -- Print help on the simple commands.',
            'interrupt -- Interrupt the execution of the debugged program.',
            'loglevel -- Get or set the pyclewn log level.',
            'mapkeys -- Map the pyclewn keys.',
            'print -- Print a value.',
            'quit -- Quit the current simple session.',
            'sigint -- Send a <C-C> character to the debugger (not implemented).',
            'step -- Step program until it reaches a different source line.',
            'symcompletion -- Populate the break and clear commands with symbols completion (not implemented).',
            'unmapkeys -- Unmap the pyclewn keys.',
            )
        self.cltest_redir(cmd, expected)

