# vi:set ts=8 sts=4 sw=4 et tw=80:
"""
Test the simple debugger.
"""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import sys
from unittest import skipIf

from .test_support import ClewnTestCase

class Simple(ClewnTestCase):
    """Test the Simple commands."""

    def __init__(self, *args, **kwds):
        ClewnTestCase.__init__(self, *args, **kwds)
        self.debugger = 'simple'
        self.netbeans_port = 3221

    def setUp(self):
        ClewnTestCase.setUp(self)
        sys.argv.append('simple')

    def test_001(self):
        """The break command"""
        cmd = [
            'Cbreak ${test_file}1:1',
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
            'Cbreak ${test_file}1:1',
            'Ccontinue',
            'Cdumprepr',
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
            'Cbreak ${test_file}1:1',
            'Cdbgvar testvar value',
            'Cdbgvar second value',
            'Cdbgvar last value',
            'Cstep',
            'Cstep',
            'Cstep',
            'Cstep',
            'Cstep',
            'edit (clewn)_variables | w! ${test_out}',
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
            'edit (clewn)_console | $$-7,$$-1w! ${test_out}',
            'edit (clewn)_variables',
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
            '"(clewn)_variables" [readonly] --No lines in buffer--',
            )
        self.cltest_redir(cmd, expected, 'line 1\n')

    def test_005(self):
        """The disable command"""
        cmd = [
            'edit ${test_file}1',
            'Cbreak ${test_file}1:1',
            'Cdisable 1',
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
            'edit (clewn)_console | $$ | ?(simple) help?+1,$$-1w!  ${test_out}',
            'qa!',
            ]
        expected = (
            'ballooneval -- Enable or disable showing text in Vim balloon.',
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
            'Cbreak ${test_file}1:1',
            'Ccontinue',
            'Cdumprepr',
            'edit (clewn)_console | $$ | ?\'inferior\': Target:?w! ${test_out}',
            'Cinterrupt',
            'Cdumprepr',
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
            'edit (clewn)_console | $$ | ?mapkeys?,$$-1w!  ${test_out}',
            'qa!',
            ]
        expected = (
            "  C-B : break $${fname}:$${lnum} # set breakpoint at current line",
            "  C-K : clear $${fname}:$${lnum} # clear breakpoint at current line",
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
            'Cbreak ${test_file}1:2',
            'Cstep',
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
            'redir! > ${test_out}',
            'Cunmapkeys',
            'map <C-B>',
            'qa!',
            ]
        expected = (
            'No mapping found',
            )
        self.cltest_redir(cmd, expected, 'line 1\n')

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
            'edit (clewn)_console | $$',
            'w! ${test_out}',
            'qa!',
            ]
        expected = (
            '(simple) help',
            'ballooneval -- Enable or disable showing text in Vim balloon.',
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

