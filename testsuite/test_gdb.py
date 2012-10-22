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

"""Test the gdb debugger.

"""
import sys
import os
from unittest2 import skipUnless, skipIf

import clewn.gdb as gdb
from test_support import ClewnTestCase, TESTFN_FILE, TESTFN_OUT

if os.name == 'nt':
    debuggee = 'file ${cwd}testsuite/foobar.exe'
    expected_break_main = (
        '--- Signs ---',
        'Signs for testsuite/overloaded.cc:',
        '    line=13  id=2  name=2',
        '    line=13  id=1  name=1',
        )
else:
    debuggee = 'file ${cwd}testsuite/foobar'
    expected_break_main = (
        '--- Signs ---',
        'Signs for testsuite/overloaded.cc:',
        '    line=16  id=2  name=2',
        '    line=16  id=1  name=1',
        )
use_select_emulation = ('CLEWN_PIPES' in os.environ or os.name == 'nt')

gdb_v = gdb.gdb_version('gdb')

class Gdb(ClewnTestCase):
    """Test the gdb debugger."""

    def setUp(self):
        """Test setup."""
        ClewnTestCase.setUp(self)
        sys.argv.append('--gdb=async')

    def setup_project_tests(self, project_file):
        """Setup a project test with its project file."""
        unused = self
        ASYNC_OPTION = '--gdb=async'
        if ASYNC_OPTION in sys.argv:
            assert sys.argv.pop() == ASYNC_OPTION
        sys.argv.append('--gdb=async,.%s%s' % (os.sep, project_file))

    def setup_gdb_args(self, args=''):
        """Setup gdb args and redirect debuggee output to /dev/null."""
        unused = self
        sys.argv.extend(['-a', ('-tty=%s %s' % (os.devnull, args))])

    def test_001(self):
        """The gdb commands completion in vim"""
        cmd = [
            'redir! > ${test_out}',
            'command Chelp',
            'command Cfile',
            'command Cmapkeys',
            'qa!',
            ]
        expected = (
            'Name        Args Range Complete  Definition',
            'Chelp       *          custom    call s:nbcommand("help", <f-args>)',
            'Name        Args Range Complete  Definition',
            'Cfile       *          file      call s:nbcommand("file", <f-args>)',
            'Name        Args Range Complete  Definition',
            'Cmapkeys  0                      call s:mapkeys()',
            )
        self.cltest_redir(cmd, expected)

    def test_002(self):
        """The 'true' program is not a gdb program"""
        sys.argv.extend(['--pgm=true'])
        cmd = [
            'qa!',
            ]
        expected = (
            '"cannot find the gdb version"',
            )
        self.cltest_logfile(cmd, expected, 'error')

    def test_003(self):
        """The gdb program is not a valid pathname"""
        foobar = 'path_to_nowhere%sfoobar' % os.sep
        sys.argv.extend(['--pgm=' + foobar])
        cmd = [
            'qa!',
            ]
        expected = (
            '"cannot start gdb as \"path_to_nowhere/foobar\""',
            )
        self.cltest_logfile(cmd, expected, 'error')

    def test_004(self):
        """Test the height, width and confirm setup"""
        cmd = [
            'edit ${test_file}1',
            'Cshow height',
            'Cshow width',
            'Cshow confirm',
            'call Wait_eop()',
            'edit (clewn)_console | $$ | ?show height?,$$w!  ${test_out}',
            'qa!',
            ]
        expected = (
            '(gdb) show height',
            'Number of lines gdb thinks are in a page is unlimited.',
            '(gdb) show width',
            'Number of characters gdb thinks are in a line is unlimited.',
            '(gdb) show confirm',
            'Whether to confirm potentially dangerous operations is off.',
            )
        self.cltest_redir(cmd, expected, 'line 1\n')

    def test_005(self):
        """Test that after quit, a new gdb session can be started"""
        cmd = [
            'edit ${test_file}1',
            'Cshow height',
            'Cquit',
            'Cshow height',
            'call Wait_eop()',
            'qa!',
            ]
        expected = (
            'new "gdb" instance\n',
            )
        self.cltest_logfile(cmd, expected, 'info', 'line 1\n')

    @skipUnless(('CLEWN_PIPES' not in os.environ
                        and 'CLEWN_POPEN' not in os.environ
                        and os.name != 'nt'),
                            'sigint is not supported on Windows')
    def test_006(self):
        """The program is interrupted with the sigint command"""
        self.setup_gdb_args()
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Crun',
            'Csigint',
            'call Wait_eop()',
            'edit (clewn)_console | $$ | ?SIGINT?,?SIGINT?w!  ${test_out}',
            'qa!',
            ]
        expected = (
            'Program received signal SIGINT, Interrupt.\n',
            )
        self.cltest_redir(cmd, expected)

    def test_007(self):
        """The gdb program can be run with --args argument list"""
        self.setup_gdb_args('--args testsuite/foobar 55')
        cmd = [
            'edit testsuite/foobar.c',
            'Cbreak foo',
            'Crun',
            'Cprint max',
            'call Wait_eop()',
            'edit (clewn)_console | $$ | $$-1w!  ${test_out}',
            'qa!',
            ]
        expected = (
            '$$1 = 55\n',
            )
        self.cltest_redir(cmd, expected)

    def test_008(self):
        """Illegal commands are rejected"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cset con',       # set confirm command
            'call Wait_eop()',
            'edit (clewn)_console | $$ | ?con?,$$-1w!  ${test_out}',
            'qa!',
            ]
        expected = (
            '(gdb) set con',
            'Illegal argument in pyclewn.',
            )
        self.cltest_redir(cmd, expected)

    @skipIf(use_select_emulation, 'when using select emulation')
    def test_009(self):
        """The break and clear commands symbols completion"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'Csymcompletion',
            '\n',
            'qa!',
            ]
        expected = (
            'symbols fetched for break and clear completion\n',
            )
        self.cltest_redir(cmd, expected)

    @skipUnless(gdb_v < [6, 4],
                        'gdb version more recent than 6.4')
    def test_010(self):
        """Checking result of oob commands"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Crun',
            'Cdumprepr',
            'call Wait_eop()',
            "edit (clewn)_console | $$ | ?'info'?,/'version'/w!  ${test_out}",
            'qa!',
            ]
        expected = (
            "'file': {'file': 'foobar.c',",
            "         'fullname': '${cwd}testsuite/foobar.c',",
            "         'line': '4'},",
            "'frame': {'line': '9', 'file': 'foobar.c', 'func': 'main', 'level': '0'},",
            )
        self.cltest_redir(cmd, expected)

    @skipUnless(gdb_v < [7, 0],
                        'gdb version more recent than 7.0')
    def test_011(self):
        """Checking result of oob commands"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Crun',
            'Cdumprepr',
            'call Wait_eop()',
            "edit (clewn)_console | $$ | ?'info'?,/'version'/w!  ${test_out}",
            'qa!',
            ]
        expected = (
            "'file': {'file': 'foobar.c',",
            "         'fullname': '${cwd}testsuite/foobar.c',",
            "         'line': '4'},",
            "'frame': {'file': 'foobar.c',",
            "          'fullname': '${cwd}testsuite/foobar.c',",
            "          'func': 'main',",
            "          'level': '0',",
            "          'line': '9'},",
            "'frame_location': {'lnum': 9,",
            "             'pathname': '${cwd}testsuite/foobar.c'},",
            )
        self.cltest_redir(cmd, expected)

    @skipUnless(gdb_v >= [7, 0],
                        'gdb version less recent than 7.0')
    def test_012(self):
        """Checking result of oob commands"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Crun',
            'Cdumprepr',
            'call Wait_eop()',
            "edit (clewn)_console | $$ | ?'info'?,/'version'/w!  ${test_out}",
            'qa!',
            ]
        expected = (
            "'file': {'file': 'foobar.c',",
            "         'fullname': '${cwd}testsuite/foobar.c',",
            "         'line': '9'},",
            "'frame': {'file': 'foobar.c',",
            "          'fullname': '${cwd}testsuite/foobar.c',",
            "          'func': 'main',",
            "          'level': '0',",
            "          'line': '9'},",
            "'frame_location': {'lnum': 9,",
            "             'pathname': '${cwd}testsuite/foobar.c'},",
            )
        self.cltest_redir(cmd, expected)

    def test_013(self):
        """Check frame sign"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Crun',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for testsuite/foobar.c:",
            "    line=9  id=1  name=3",
            "    line=9  id=2  name=1",
            )
        self.cltest_redir(cmd, expected)

    def test_014(self):
        """Check annotations level 1 are removed"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Crun',
            'Cstep',
            'Cstep',
            'call Wait_eop()',
            "edit (clewn)_console | $$ | /(gdb) step/,$$w!  ${test_out}",
            'qa!',
            ]
        expected = (
            "(gdb) step",
            "(gdb) step",
            )
        self.cltest_redir(cmd, expected)

    def test_015(self):
        """Check disable breakpoint"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Cdisable 1',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for testsuite/foobar.c:",
            "line=9  id=3  name=2",
            )
        self.cltest_redir(cmd, expected)

    def test_016(self):
        """Check breakpoint delete once"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Cenable delete 1',
            'Crun',
            'Cstep',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for testsuite/foobar.c:",
            "line=10  id=1  name=3",
            )
        self.cltest_redir(cmd, expected)

    def test_017(self):
        """Check setting a breakpoint open the source file"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for ${cwd}testsuite/foo.c:",
            "line=30  id=2  name=1",
            )
        self.cltest_redir(cmd, expected)

    def test_018(self):
        """Check delete breakpoint"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Cbreak main',
            'Cdelete 1',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for testsuite/foobar.c:",
            "line=9  id=4  name=3",
            )
        self.cltest_redir(cmd, expected)

    def test_019(self):
        """Check clearing breakpoints on the frame sign line"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Crun',
            'Cclear',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for testsuite/foobar.c:",
            "line=9  id=1  name=3",
            )
        self.cltest_redir(cmd, expected)

    @skipIf(use_select_emulation, 'when using select emulation')
    def test_020(self):
        """Check break completion on overloaded functions"""
        cmd = [
            'edit testsuite/overloaded.cc',
            'Cfile testsuite/overloaded',
            'Csymcompletion',
            '\n',
            'call Wait_eop()',
            'qa!',
            ]
        expected = (
            'gdb  DEBUG   ~"break test()\\n"',
            'gdb  DEBUG   ~"break test(int)\\n"',
            'gdb  DEBUG   ~"break test(int, int)\\n"',
            )
        self.cltest_logfile(cmd, expected, 'debug')

    def test_021(self):
        """Check varobj creation, folding and deletion"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'Crun',
            'Cstep',
            'Cstep',
            'Cstep',
            'Cdbgvar map',
            'Cfoldvar 1',
            'Cdelvar var1.value',
            'call Wait_eop()',
            'buffer (clewn)_dbgvar | 1,$$w!  ${test_out}',
            'qa!',
            ]
        expected = (
            "[-] var1: (map_t) map ={=} {...}",
            "   *  var1.key: (int) key ={=} 1",
            )
        self.cltest_redir(cmd, expected)

    def test_022(self):
        """Check varobj folding"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'Crun',
            'Cstep',
            'Cstep',
            'Cstep',
            'Cdbgvar map',
            'Cdbgvar map',
            'Cfoldvar 2',
            'Cfoldvar 1',
            'Cfoldvar 1',
            'call Wait_eop()',
            'buffer (clewn)_dbgvar | 1,3w!  ${test_out}',
            'qa!',
            ]
        expected = (
            "[+] var1: (map_t) map ={=} {...}",
            "[-] var2: (map_t) map ={=} {...}",
            "   *  var2.key  : (int   ) key   ={=} 1",
            )
        self.cltest_redir(cmd, expected)

    def test_023(self):
        """Check deleting the last varobj"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'Crun',
            'Cdbgvar map',
            'Cdbgvar map',
            'Cdbgvar map',
            'Cfoldvar 2',
            'Cstep',
            'Cstep',
            'Cstep',
            'Cdelvar var3',
            'call Wait_eop()',
            'buffer (clewn)_dbgvar | 1,3w!  ${test_out}',
            'qa!',
            ]
        expected = (
            "[+] var1: (map_t) map ={=} {...}",
            "[-] var2: (map_t) map ={=} {...}",
            "   *  var2.key  : (int   ) key   ={=} 1",
            )
        self.cltest_redir(cmd, expected)

    def test_024(self):
        """Check deleting the first varobj"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'Crun',
            'Cdbgvar map',
            'Cdbgvar map',
            'Cdbgvar map',
            'Cfoldvar 2',
            'Cstep',
            'Cstep',
            'Cstep',
            'Cdelvar var1',
            'call Wait_eop()',
            'buffer (clewn)_dbgvar | 1,2w!  ${test_out}',
            'qa!',
            ]
        expected = (
            "[-] var2: (map_t) map ={=} {...}",
            "   *  var2.key  : (int   ) key   ={=} 1",
            )
        self.cltest_redir(cmd, expected)

    def test_025(self):
        """Check deleting a middle varobj"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'Crun',
            'Cdbgvar map',
            'Cdbgvar map',
            'Cdbgvar map',
            'Cfoldvar 2',
            'Cstep',
            'Cstep',
            'Cstep',
            'Cdelvar var2',
            'call Wait_eop()',
            'buffer (clewn)_dbgvar | 1,2w!  ${test_out}',
            'qa!',
            ]
        expected = (
            "[+] var1: (map_t) map ={=} {...}",
            "[+] var3: (map_t) map ={=} {...}",
            )
        self.cltest_redir(cmd, expected)

    def test_026(self):
        """Check varobj hiliting"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak bar',
            'Crun',
            'Cstep',
            'Cdbgvar i',
            'call Wait_eop()',
            'edit (clewn)_dbgvar | 1,$$w!  ${test_out}',
            'Cstep',
            'Cstep',
            'Cstep',
            'Cstep',
            'Cstep',
            'call Wait_eop()',
            'edit (clewn)_dbgvar | 1,$$w! >> ${test_out}',
            'Cfinish',
            'call Wait_eop()',
            'edit (clewn)_dbgvar | 1,$$w! >> ${test_out}',
            'qa!',
            ]
        expected = (
            " *  var1: (int) i ={*} 0",
            " *  var1: (int) i ={*} 1",
            " *  var1: (int) i ={-} 1",
            )
        self.cltest_redir(cmd, expected)

    @skipIf(True, 'test cancelled')
    def test_027(self):
        """Check robustness against vim 'tabedit (clewn)_dbgvar' bug"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'Crun',
            'Cdbgvar map',
            'edit (clewn)_dbgvar',
            'tabedit (clewn)_dbgvar',
            'Cshow annotate',
            'call Wait_eop()',
            '1,$$w! >> ${test_out}',
            'qa!',
            ]
        expected = (
            "[+] var1: (map_t) map ={=} {...}\n",
            )
        self.cltest_redir(cmd, expected)

    def test_028(self):
        """Watched variables are updated when changed with the print command"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Crun',
            'Cdbgvar len',
            'Cprint len=555',
            'call Wait_eop()',
            'edit (clewn)_dbgvar | 1,$$w! >> ${test_out}',
            'qa!',
            ]
        expected = (
            " *  var1: (int) len ={*} 555",
            )
        self.cltest_redir(cmd, expected)

    def test_029(self):
        """Returning to the correct frame location after a print command"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Cbreak foo',
            'Crun',
            'Cprint foo(\\"toto\\", 1)',
            'Ccontinue',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'sign list',
            'qa!',
            ]
        expected = (
            '--- Signs ---',
            'Signs for testsuite/foobar.c:',
            '    line=9  id=1  name=5',
            '    line=9  id=2  name=1',
            'Signs for ${cwd}testsuite/foo.c:',
            '    line=30  id=4  name=3',
            'sign 1 text=1  texthl=NB_2',
            'sign 2 text=1  texthl=NB_3',
            'sign 3 text=2  texthl=NB_4',
            'sign 4 text=2  texthl=NB_5',
            'sign 5 text==> texthl=NB_0',
            )
        self.cltest_redir(cmd, expected)

    @skipUnless(gdb_v <= [7, 3],
        'gdb 7.4 introduces the concept of a breakpoint with multiple signs')
    def test_030(self):
        """Set automatically all breakpoints on a multiple choice"""
        cmd = [
            'edit testsuite/overloaded.cc',
            'Cfile testsuite/overloaded',
            'Cbreak A::test',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            '--- Signs ---',
            'Signs for testsuite/overloaded.cc:',
            '    line=3  id=4  name=3',
            '    line=4  id=6  name=5',
            '    line=5  id=2  name=1',
            )
        self.cltest_redir(cmd, expected)

    def test_031(self):
        """Check the project command"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Cbreak foo',
            'Cset args foo \\"1 2 3\\" bar',
            'Cproject ${test_out}',
            'call Wait_eop()',
            'qa!',
            ]
        expected = (
            'cd ${cwd}',
            debuggee,
            'set args foo "1 2 3" bar',
            'break ${cwd}testsuite/foobar.c:9',
            'break ${cwd}testsuite/foo.c:30',
            )
        self.cltest_redir(cmd, expected)

    def test_032(self):
        """Check the project command saves at most one breakpoint per line"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'Cbreak foo',
            'Cbreak foo',
            'Cbreak main',
            'Cproject ${test_out}',
            'call Wait_eop()',
            'qa!',
            ]
        expected = (
            debuggee,
            'break ${cwd}testsuite/foo.c:30',
            'break ${cwd}testsuite/foobar.c:9',
            )
        self.cltest_redir(cmd, expected)

    def test_033(self):
        """Project option sources a project file"""
        self.setup_project_tests('%s1' % TESTFN_FILE)
        cmd = [
            'edit testsuite/foobar.c',
            'Cecho',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            '--- Signs ---',
            'Signs for testsuite/foobar.c:',
            '    line=9  id=2  name=1',
            'Signs for ${cwd}testsuite/foo.c:',
            '    line=30  id=4  name=3',
            )
        self.cltest_redir(cmd, expected,
            'cd testsuite\n'
            'file foobar\n'
            'break main\n'
            'break foo\n'
            )

    def test_034(self):
        """Project option saves a project file"""
        self.setup_project_tests(TESTFN_OUT)
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Cbreak foo',
            'Cset args foo \\"1 2 3\\" bar',
            'Cquit',
            'call Wait_eop()',
            'qa!',
            ]
        expected = (
            'cd ${cwd}',
            debuggee,
            'set args foo "1 2 3" bar',
            'break ${cwd}testsuite/foobar.c:9',
            'break ${cwd}testsuite/foo.c:30',
            )
        self.cltest_redir(cmd, expected)

    def test_035(self):
        """Project option saves a project file on quitting from Vim"""
        self.setup_project_tests(TESTFN_OUT)
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'call Wait_eop()',
            'qa!',
            ]
        expected = (
            'cd ${cwd}',
            debuggee,
            'break ${cwd}testsuite/foobar.c:9',
            )
        self.cltest_redir(cmd, expected)

    def test_036(self):
        """The quit command prints a separation line"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cquit',
            'call Wait_eop()',
            'edit (clewn)_console | $$ | w!  ${test_out}',
            'qa!',
            ]
        expected = (
            '===========\n',
            )
        self.cltest_redir(cmd, expected)

    def test_037(self):
        """The cwindow command opens the quickfix window of breakpoints"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'Cbreak bar',
            'Cbreak bar',
            'Cdisable 1',
            'Cdelete 2',
            'call Wait_eop()',
            'Ccwindow',
            '5buffer',
            '1,$$w! >> ${test_out}',
            'qa!',
            ]
        expected = (
            "${cwd}testsuite/foo.c|30| breakpoint 1 disabled",
            "${cwd}testsuite/bar.c|5| breakpoint 3 enabled",
            )
        self.cltest_redir(cmd, expected)

    def test_038(self):
        """Check number 1, adding breakpoints after a quit"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Cquit',
            'Cfile testsuite/foobar',
            'Cbreak ${cwd}testsuite/foobar.c:16',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for testsuite/foobar.c:",
            "line=16  id=2  name=1",
            )
        self.cltest_redir(cmd, expected)

    @skipIf(use_select_emulation, 'when using select emulation')
    def test_039(self):
        """Check number 2, adding breakpoints after a quit"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Cbreak foo',
            'Cquit',
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'Cbreak foo',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for ${cwd}testsuite/foo.c:",
            "line=30  id=6  name=1",
            "line=30  id=4  name=3",
            )
        self.cltest_redir(cmd, expected)

    def test_040(self):
        """Check number 3, adding breakpoints after a quit"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Cbreak foo',
            'Cquit',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Cbreak main',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for testsuite/foobar.c:",
            "line=9  id=6  name=3",
            "line=9  id=2  name=1",
            )
        self.cltest_redir(cmd, expected)

    def test_041(self):
        """Check number 4, adding breakpoints after a quit"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Cbreak foo',
            'Cquit',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Cbreak main',
            'Cquit',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Cbreak foo',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for testsuite/foobar.c:",
            "line=9  id=2  name=1",
            "Signs for ${cwd}testsuite/foo.c:",
            "line=30  id=4  name=3",
            )
        self.cltest_redir(cmd, expected)

    def test_042(self):
        """Set a breakpoint in a template function"""
        cmd = [
            'edit testsuite/function_template.cpp',
            'Cfile testsuite/function_template',
            'Cbreak ${cwd}testsuite/function_template_sub/localmax.cpp:7',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for ${cwd}testsuite/function_template_sub/localmax.cpp:",
            "line=7  id=2  name=1",
            )
        self.cltest_redir(cmd, expected)

    def test_043(self):
        """Check starting the session with the 'sigint' command"""
        cmd = [
            'edit testsuite/foobar.c',
            'Csigint',
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for ${cwd}testsuite/foo.c:",
            "line=30  id=2  name=1",
            )
        self.cltest_redir(cmd, expected)

    def test_044(self):
        """Check the frame command moves the cursor to the frame location"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'Crun',
            'call Wait_eop()',
            'edit testsuite/foobar.c',
            'echo bufname("%")',
            'Cframe',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'echo bufname("%")',
            'qa!',
            ]
        expected = (
            "${cwd}testsuite/foo.c",
            )
        self.cltest_redir(cmd, expected)

    def test_045(self):
        """Set a breakpoint after a 'throw' catchpoint"""
        cmd = [
            'edit testsuite/overloaded.cc',
            'Cfile testsuite/overloaded',
            'Cstart',
            'Ccatch throw',
            'Cbreak main',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        self.cltest_redir(cmd, expected_break_main)

    def test_046(self):
        """Set a breakpoint after deleting a 'throw' catchpoint"""
        cmd = [
            'edit testsuite/overloaded.cc',
            'Cfile testsuite/overloaded',
            'Cstart',
            'Ccatch throw',
            'Cdelete 2',
            'Cbreak main',
            'call Wait_eop()',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        self.cltest_redir(cmd, expected_break_main)

