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

"""Test the simple application.

"""
import os
import sys
import unittest
from test.test_support import run_unittest

import clewn.debugger.simple
from testsuite.test_support import ClewnTestCase

class SimpleCommandsTestCase(ClewnTestCase):
    """Test the Simple commands."""

    def setUp(self):
        """Test setup."""
        ClewnTestCase.setUp(self)
        sys.argv.append('--simple')


    def test_break(self):
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

    def test_clear(self):
        """The clear command"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cbreak ${test_file}1:1\n'
            ':Cbreak ${test_file}1:2\n'
            ':Cbreak ${test_file}1:2\n'
            ':Cclear ${test_file}1:1\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':qa!\n',

            'line=2  id=3  name=1\n'
            'line=2  id=2  name=1',

            'line 1\n'
            'line 2\n'
            )

    def test_continue(self):
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

    def test_dbgvar(self):
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

    def test_delvar(self):
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

    def test_disable(self):
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

            'line=1  id=1  name=2',

            'line 1\n'
            )

    def test_dumprepr(self):
        """The dumprepr command"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cdumprepr\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$ | ?\'_bset\'?,?\'lnum\'?w!  ${test_out}\n'
            ':qa!\n',

            "{'_bset': {'(clewn)_console': {},\n"
            "           '(clewn)_dbgvar': {},\n"
            "           '${cwd}@test_file_1': {}},\n"
            " 'arglist': None,\n"
            " 'bp_id': 0,\n"
            " 'closed': False,\n"
            " 'daemon': False,\n"
            " 'inferior': Target: {'running': False, 'closed': False},\n"
            " 'last_balloon': '',\n"
            " 'lnum': 0,",

            'line 1\n'
            )

    def test_enable(self):
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

            'line=1  id=1  name=2\n'
            'line=2  id=2  name=1',

            'line 1\n'
            'line 2\n'
            )

    def test_help(self):
        """The help command"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Chelp\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$ | ?(simple) help?+1,$$-1w!  ${test_out}\n'
            ':qa!\n',

            'break -- Set a breakpoint at a specified line.\n'
            'clear -- Clear all breakpoints at a specified line.\n'
            'continue -- Continue the program being debugged, also used to start the program.\n'
            'dbgvar -- Add a variable to the debugger variable buffer.\n'
            'delvar -- Delete a variable from the debugger variable buffer.\n'
            'disable -- Disable one breakpoint.\n'
            'dumprepr -- Print debugging information on netbeans and the application.\n'
            'enable -- Enable one breakpoint.\n'
            'help -- Print help on the simple commands.\n'
            'interrupt -- Interrupt the execution of the debugged program.\n'
            'mapkeys -- Map the pyclewn keys.\n'
            'print -- Print a value.\n'
            'quit -- Quit the current simple session.\n'
            'sigint -- Send a <C-C> character to the debugger (not implemented).\n'
            'step -- Step program until it reaches a different source line.\n'
            'symcompletion -- Populate the break and clear commands with symbols completion (not implemented).\n'
            'unmapkeys -- Unmap the pyclewn keys, this vim command does not invoke pyclewn.\n',

            'line 1\n'
            )

    def test_interrupt(self):
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

    def test_mapkeys(self):
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

    def test_print(self):
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

    def test_quit_posix(self):
        """The quit command"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cbreak ${test_file}1:1\n'
            ':Cstep\n'
            ':Cdumprepr\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$ | ?\'_bset\'?,?\'inferior\': Target:?w! ${test_out}\n'
            ':Cquit\n'
            ':Cdumprepr\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$ | ?\'_bset\'?,?\'inferior\': Target:?w!  >> ${test_out}\n'
            ':qa!\n',

            "{'_bset': {'(clewn)_console': {},\n"
            "           '(clewn)_dbgvar': {},\n"
            "           '${cwd}@test_file_1': {1: bp enabled at line 1,\n"
            "                                     'frame': frame at line 1}},\n"
            " 'arglist': None,\n"
            " 'bp_id': 1,\n"
            " 'closed': False,\n"
            " 'daemon': False,\n"
            " 'inferior': Target: {'running': False, 'closed': False},\n"
            "{'_bset': {'(clewn)_console': {},\n"
            "           '(clewn)_dbgvar': {},\n"
            "           '${cwd}@test_file_1': {}},\n"
            " 'arglist': None,\n"
            " 'bp_id': 0,\n"
            " 'closed': False,\n"
            " 'daemon': False,\n"
            " 'inferior': Target: {'running': False, 'closed': False},\n",

            'line 1\n'
            )

    def test_quit(self):
        """The quit command"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cbreak ${test_file}1:1\n'
            ':Cstep\n'
            ':Cdumprepr\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$ | ?\'_bset\'?,?\'arglist\': None,?w! ${test_out}\n'
            ':Cquit\n'
            ':Cdumprepr\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$ | ?\'_bset\'?,?\'arglist\': None,?w!  >> ${test_out}\n'
            ':qa!\n',

            "{'_bset': {'(clewn)_console': {},\n"
            "           '(clewn)_dbgvar': {},\n"
            "           '${cwd}@test_file_1': {1: bp enabled at line 1,\n"
            "                                     'frame': frame at line 1}},\n"
            " 'arglist': None,\n"
            "{'_bset': {'(clewn)_console': {},\n"
            "           '(clewn)_dbgvar': {},\n"
            "           '${cwd}@test_file_1': {}},\n"
            " 'arglist': None,\n",

            'line 1\n'
            )

    def test_step(self):
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

            'line=1  id=2  name=3\n'
            'line=2  id=1  name=1',

            'line 1\n'
            'line 2\n'
            )

    def test_unmapkeys(self):
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

    def test_maxlines(self):
        """Maximum number of lines in the console buffer"""
        sys.argv.extend(['--maxlines=70'])
        self.cltest_redir(
            ':let index = 0\n'
            ':while index < 50\n'
            ':  let index = index + 1\n'
            ':  Cmapkeys\n'
            ':  sleep 20m\n'
            ':endwhile\n'
            ':sleep ${time}\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':file\n'
            ':qa!\n',

            # Cmapkeys outputs 8 lines, thus: 9 * 8 + 1 = 73 lines
            '"(clewn)_console" [readonly] line 73 of 73'
            )

    def test_firstcommand(self):
        """The first command on the [NoName] buffer succeeds"""
        self.cltest_redir(
            ':Chelp\n'
            ':sleep ${time}\n'
            ':sleep ${time}\n'
            ':w! ${test_out}\n'
            ':qa!\n',

            '(simple) help\n'
            'break -- Set a breakpoint at a specified line.\n'
            'clear -- Clear all breakpoints at a specified line.\n'
            'continue -- Continue the program being debugged, also used to start the program.\n'
            'dbgvar -- Add a variable to the debugger variable buffer.\n'
            'delvar -- Delete a variable from the debugger variable buffer.\n'
            'disable -- Disable one breakpoint.\n'
            'dumprepr -- Print debugging information on netbeans and the application.\n'
            'enable -- Enable one breakpoint.\n'
            'help -- Print help on the simple commands.\n'
            'interrupt -- Interrupt the execution of the debugged program.\n'
            'mapkeys -- Map the pyclewn keys.\n'
            'print -- Print a value.\n'
            'quit -- Quit the current simple session.\n'
            'sigint -- Send a <C-C> character to the debugger (not implemented).\n'
            'step -- Step program until it reaches a different source line.\n'
            'symcompletion -- Populate the break and clear commands with symbols completion (not implemented).\n'
            'unmapkeys -- Unmap the pyclewn keys, this vim command does not invoke pyclewn.'
            )


def test_main():
    """Run all the tests."""
    suite = unittest.TestSuite()
    suite.addTest(SimpleCommandsTestCase('test_break'))
    suite.addTest(SimpleCommandsTestCase('test_clear'))
    suite.addTest(SimpleCommandsTestCase('test_continue'))
    suite.addTest(SimpleCommandsTestCase('test_dbgvar'))
    suite.addTest(SimpleCommandsTestCase('test_delvar'))
    suite.addTest(SimpleCommandsTestCase('test_disable'))
    suite.addTest(SimpleCommandsTestCase('test_dumprepr'))
    suite.addTest(SimpleCommandsTestCase('test_enable'))
    suite.addTest(SimpleCommandsTestCase('test_help'))
    suite.addTest(SimpleCommandsTestCase('test_interrupt'))
    suite.addTest(SimpleCommandsTestCase('test_step'))
    suite.addTest(SimpleCommandsTestCase('test_mapkeys'))
    suite.addTest(SimpleCommandsTestCase('test_print'))
    if os.name == 'nt':
        suite.addTest(SimpleCommandsTestCase('test_quit'))
    else:
        suite.addTest(SimpleCommandsTestCase('test_quit_posix'))
    suite.addTest(SimpleCommandsTestCase('test_unmapkeys'))
    suite.addTest(SimpleCommandsTestCase('test_maxlines'))
    suite.addTest(SimpleCommandsTestCase('test_firstcommand'))
    run_unittest(suite)

if __name__ == "__main__":
    test_main()

