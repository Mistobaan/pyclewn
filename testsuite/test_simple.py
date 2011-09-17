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

from test_support import ClewnTestCase

class Simple(ClewnTestCase):
    """Test the Simple commands."""

    def setUp(self):
        """Test setup."""
        ClewnTestCase.setUp(self)
        sys.argv.append('--simple')


    def test_001(self):
        """The break command"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cbreak ${test_file}1:1\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':qa!\n',

            'line=1  id=1  name=1',

            'line 1\n'
            )

    def test_002(self):
        """The continue command"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cbreak ${test_file}1:1\n'
            ':Ccontinue\n'
            ':Cdumprepr\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$ | ?\'inferior\': Target:?w! ${test_out}\n'
            ':qa!\n',

            "'inferior': Target: {'running': True, 'closed': False}",

            'line 1\n'
            )

    def test_003(self):
        """The dbgvar command"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cbreak ${test_file}1:1\n'
            ':Cdbgvar testvar value\n'
            ':Cdbgvar second value\n'
            ':Cdbgvar last value\n'
            ':Cstep\n'
            ':Cstep\n'
            ':Cstep\n'
            ':Cstep\n'
            ':Cstep\n'
            ':sleep ${time}\n'
            ':edit (clewn)_dbgvar | w! ${test_out}\n'
            ':qa!\n',

            '     testvar ={=} 3\n'
            '      second ={*} 3\n'
            '        last ={=} 2\n',

            'line 1\n'
            )

    def test_004(self):
        """The delvar command"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cdbgvar testvar value\n'
            ':Cdelvar\n'
            ':Cdelvar unknown\n'
            ':Cdelvar testvar\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$-7,$$-1w! ${test_out}\n'
            ':edit (clewn)_dbgvar\n'
            ':redir! >> ${test_out}\n'
            ':file\n'
            ':qa!\n',

            '(simple) delvar\n'
            'Invalid arguments.\n'
            '(simple) delvar unknown\n'
            '"unknown" not found.\n'
            '(simple) delvar testvar\n'
            '"(clewn)_dbgvar" [readonly] --No lines in buffer--\n',

            'line 1\n'
            )

    def test_005(self):
        """The disable command"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cbreak ${test_file}1:1\n'
            ':Cdisable 1\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':qa!\n',

            'line=1  id=2  name=2',

            'line 1\n'
            )

    def test_006(self):
        """The dumprepr command"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cdumprepr\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$ | ?\'_bset\'?,?\'lnum\'?w!  ${test_out}\n'
            ':qa!\n',

            " 'bp_id': 0,\n"
            " 'closed': False,\n"
            " 'inferior': Target: {'running': False, 'closed': False},\n"
            " 'lnum': 0,",

            'line 1\n'
            )

    def test_007(self):
        """The enable command"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cbreak ${test_file}1:1\n'
            ':Cbreak ${test_file}1:2\n'
            ':Cdisable 1\n'
            ':Cdisable 2\n'
            ':Cenable 2\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':qa!\n',

            'line=1  id=2  name=2\n'
            'line=2  id=3  name=3',

            'line 1\n'
            'line 2\n'
            )

    def test_008(self):
        """The help command"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Chelp\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$ | ?(simple) help?+1,$$-1w!  ${test_out}\n'
            ':qa!\n',

            'break -- Set a breakpoint at a specified line.\n'
            'continue -- Continue the program being debugged, also used to start the program.\n'
            'dbgvar -- Add a variable to the debugger variable buffer.\n'
            'delvar -- Delete a variable from the debugger variable buffer.\n'
            'disable -- Disable one breakpoint.\n'
            'dumprepr -- Print debugging information on netbeans and the debugger.\n'
            'enable -- Enable one breakpoint.\n'
            'help -- Print help on the simple commands.\n'
            'interrupt -- Interrupt the execution of the debugged program.\n'
            'loglevel -- Get or set the pyclewn log level.\n'
            'mapkeys -- Map the pyclewn keys.\n'
            'print -- Print a value.\n'
            'quit -- Quit the current simple session.\n'
            'sigint -- Send a <C-C> character to the debugger (not implemented).\n'
            'step -- Step program until it reaches a different source line.\n'
            'symcompletion -- Populate the break and clear commands with symbols completion (not implemented).\n'
            'unmapkeys -- Unmap the pyclewn keys.\n',

            'line 1\n'
            )

    def test_009(self):
        """The interrupt command"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cbreak ${test_file}1:1\n'
            ':Ccontinue\n'
            ':Cdumprepr\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$ | ?\'inferior\': Target:?w! ${test_out}\n'
            ':Cinterrupt\n'
            ':Cdumprepr\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$ | ?\'inferior\': Target:?w! >> ${test_out}\n'
            ':qa!\n',

            "'inferior': Target: {'running': True, 'closed': False},\n"
            "'inferior': Target: {'running': False, 'closed': False},",

            'line 1\n'
            )

    def test_010(self):
        """The mapkeys command"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cmapkeys\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$ | ?mapkeys?,$$-1w!  ${test_out}\n'
            ':qa!\n',

            "  C-B : break $${fname}:$${lnum} # set breakpoint at current line\n"
            "  C-E : clear $${fname}:$${lnum} # clear breakpoint at current line\n"
            "  C-P : print $${text}           # print value of selection at mouse position\n"
            "  C-Z : interrupt                # interrupt the execution of the target\n"
            "  S-C : continue\n"
            "  S-Q : quit\n"
            "  S-S : step",

            'line 1\n'
            )

    def test_011(self):
        """The print command"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cprint foobar\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$-1w! ${test_out}\n'
            ':qa!\n',

            'foobar',

            'line 1\n'
            )

    def test_012(self):
        """The step command"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cbreak ${test_file}1:2\n'
            ':Cstep\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':qa!\n',

            'line=1  id=3  name=3\n'
            'line=2  id=1  name=1',

            'line 1\n'
            'line 2\n'
            )

    def test_013(self):
        """The unmapkeys command"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cmapkeys\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':Cunmapkeys\n'
            ':map <C-B>\n'
            ':qa!\n',

            'No mapping found',

            'line 1\n'
            )

    def test_014(self):
        """Maximum number of lines in the console buffer"""
        sys.argv.extend(['--maxlines=70'])
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':let index = 0\n'
            ':while index < 50\n'
            ':  let index = index + 1\n'
            ':  Cmapkeys\n'
            ':  sleep 20m\n'
            ':endwhile\n'
            ':sleep ${time}\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$\n'
            ':redir! > ${test_out}\n'
            ':file\n'
            ':qa!\n',

            # Cmapkeys outputs 8 lines, thus: 9 * 8 + 1 = 73 lines
            '"(clewn)_console" [readonly] line 73 of 73'
            )

    def test_015(self):
        """The first command on a file loaded at startup succeeds"""
        self.setup_vim_arg("testsuite/foobar.c")
        self.cltest_redir(
            ':Chelp\n'
            ':sleep ${time}\n'
            ':sleep ${time}\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$\n'
            ':w! ${test_out}\n'
            ':qa!\n',

            '(simple) help\n'
            'break -- Set a breakpoint at a specified line.\n'
            'continue -- Continue the program being debugged, also used to start the program.\n'
            'dbgvar -- Add a variable to the debugger variable buffer.\n'
            'delvar -- Delete a variable from the debugger variable buffer.\n'
            'disable -- Disable one breakpoint.\n'
            'dumprepr -- Print debugging information on netbeans and the debugger.\n'
            'enable -- Enable one breakpoint.\n'
            'help -- Print help on the simple commands.\n'
            'interrupt -- Interrupt the execution of the debugged program.\n'
            'loglevel -- Get or set the pyclewn log level.\n'
            'mapkeys -- Map the pyclewn keys.\n'
            'print -- Print a value.\n'
            'quit -- Quit the current simple session.\n'
            'sigint -- Send a <C-C> character to the debugger (not implemented).\n'
            'step -- Step program until it reaches a different source line.\n'
            'symcompletion -- Populate the break and clear commands with symbols completion (not implemented).\n'
            'unmapkeys -- Unmap the pyclewn keys.'
            )

