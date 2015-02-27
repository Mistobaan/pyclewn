# vi:set ts=8 sts=4 sw=4 et tw=80:
"""
Test the gdb debugger.
"""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import sys
import os
from unittest import skipUnless, skipIf

import clewn.gdb as gdb
from .test_support import ClewnTestCase, TESTFN_FILE, TESTFN_OUT

debuggee = 'file ${cwd}testsuite/foobar'
expected_break_main = (
    '--- Signs ---',
    'Signs for testsuite/overloaded.cc:',
    '    line=16  id=2  name=2',
    '    line=16  id=1  name=1',
    )

gdb_v = gdb.gdb_version('gdb')

class Gdb(ClewnTestCase):
    """Test the gdb debugger."""

    def __init__(self, *args, **kwds):
        ClewnTestCase.__init__(self, *args, **kwds)
        self.debugger = 'gdb'
        self.netbeans_port = 3219

    def setUp(self):
        ClewnTestCase.setUp(self)
        sys.argv.append('--gdb=async')

    def setup_project_tests(self, project_file):
        """Setup a project test with its project file."""
        ASYNC_OPTION = '--gdb=async'
        if ASYNC_OPTION in sys.argv:
            assert sys.argv.pop() == ASYNC_OPTION
        sys.argv.append('--gdb=async,.%s%s' % (os.sep, project_file))

    def setup_gdb_args(self, args=''):
        """Setup gdb args and redirect debuggee output to /dev/null."""
        sys.argv.extend(['-a', ('-tty=%s %s' % (os.devnull, args))])

    def test_001a(self):
        """The gdb commands completion in vim"""
        cmd = [
            'redir! > ${test_out}',
            'command Chelp',
            'qa!',
            ]
        expected = (
            'Chelp       *          custom    call s:nbcommand("help", <f-args>)',
            )
        self.cltest_redir(cmd, expected)

    def test_001b(self):
        """The gdb commands completion in vim"""
        cmd = [
            'redir! > ${test_out}',
            'command Cfile',
            'qa!',
            ]
        expected = (
            'Cfile       *          file      call s:nbcommand("file", <f-args>)',
            )
        self.cltest_redir(cmd, expected)

    def test_001c(self):
        """The gdb commands completion in vim"""
        cmd = [
            'redir! > ${test_out}',
            'command Cmapkeys',
            'qa!',
            ]
        expected = (
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
            'qa!',
            ]
        expected = (
            'new "gdb" instance\n',
            )
        self.cltest_logfile(cmd, expected, 'info', 'line 1\n')

    def test_006(self):
        """The program is interrupted with the sigint command"""
        self.setup_gdb_args()
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Crun',
            'sleep ${sleep_time}',
            'Csigint',
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
            'Cbreak foo',
            'Crun',
            'Cprint max',
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
            'edit (clewn)_console | $$ | ?con?,$$-1w!  ${test_out}',
            'qa!',
            ]
        expected = (
            '(gdb) set con',
            'Illegal argument in pyclewn.',
            )
        self.cltest_redir(cmd, expected)

    def test_009(self):
        """The break and clear commands symbols completion"""
        cmd = [
            'Cfile testsuite/foobar',
            'redir! > ${test_out}',
            'Csymcompletion',
            '\n',
            'call Wait_eop()',
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
            )
        self.cltest_redir(cmd, expected)

    @skipUnless(gdb_v >= [7, 0],
                        'gdb version less recent than 7.0')
    def test_012(self):
        """Checking result of oob commands"""
        cmd = [
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Crun',
            'Cdumprepr',
            "edit (clewn)_console | $$ | ?'info'?,/'version'/w!  ${test_out}",
            'qa!',
            ]
        expected = (
            "'file': {'file': 'foobar.c',",
            "         'fullname': '${cwd}testsuite/foobar.c',",
            "         'line': '10'},",
            "'frame': {'file': 'foobar.c',",
            "          'fullname': '${cwd}testsuite/foobar.c',",
            "          'func': 'main',",
            "          'level': '0',",
            "          'line': '10'},",
            )
        self.cltest_redir(cmd, expected)

    def test_013(self):
        """Check frame sign"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Crun',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for testsuite/foobar.c:",
            "    line=10  id=1  name=3",
            "    line=10  id=2  name=1",
            )
        self.cltest_redir(cmd, expected)

    def test_014(self):
        """Check annotations level 1 are removed"""
        cmd = [
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Crun',
            'Cstep',
            'Cstep',
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
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for testsuite/foobar.c:",
            "line=10  id=3  name=2",
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
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for testsuite/foobar.c:",
            "line=11  id=1  name=3",
            )
        self.cltest_redir(cmd, expected)

    def test_017(self):
        """Check setting a breakpoint open the source file"""
        cmd = [
            'Cfile testsuite/foobar',
            'Cbreak foo',
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
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for testsuite/foobar.c:",
            "line=10  id=4  name=3",
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
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for testsuite/foobar.c:",
            "line=10  id=1  name=3",
            )
        self.cltest_redir(cmd, expected)

    def test_020(self):
        """Check break completion on overloaded functions"""
        cmd = [
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
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'Crun',
            'Cstep',
            'Cstep',
            'Cstep',
            'Cdbgvar map',
            'Cfoldvar 1',
            'Cdelvar var1.value',
            'buffer (clewn)_variables | 1,$$w!  ${test_out}',
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
            'buffer (clewn)_variables | 1,3w!  ${test_out}',
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
            'buffer (clewn)_variables | 1,3w!  ${test_out}',
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
            'buffer (clewn)_variables | 1,2w!  ${test_out}',
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
            'buffer (clewn)_variables | 1,2w!  ${test_out}',
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
            'edit (clewn)_variables | 1,$$w!  ${test_out}',
            'Cstep',
            'Cstep',
            'Cstep',
            'Cstep',
            'Cstep',
            'edit (clewn)_variables | 1,$$w! >> ${test_out}',
            'Cfinish',
            'edit (clewn)_variables | 1,$$w! >> ${test_out}',
            'qa!',
            ]
        expected = (
            " *  var1: (int) i ={*} 0",
            " *  var1: (int) i ={*} 1",
            " *  var1: (int) i ={-} 1",
            )
        self.cltest_redir(cmd, expected)

    def test_027(self):
        """Check robustness against vim 'tabedit (clewn)_variables' bug"""
        cmd = [
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'Crun',
            'Cdbgvar map',
            'edit (clewn)_variables',
            'tabedit (clewn)_variables',
            'Cshow annotate',
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
            'edit (clewn)_variables | 1,$$w! >> ${test_out}',
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
            'redir! > ${test_out}',
            'sign place',
            'sign list',
            'qa!',
            ]
        expected = (
            '--- Signs ---',
            'Signs for testsuite/foobar.c:',
            '    line=10  id=1  name=5',
            '    line=10  id=2  name=1',
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
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Cbreak foo',
            'Cset args foo \\"1 2 3\\" bar',
            'Cproject ${test_out}',
            'qa!',
            ]
        expected = (
            'cd ${cwd}',
            debuggee,
            'set args foo "1 2 3" bar',
            'break ${cwd}testsuite/foobar.c:10',
            'break ${cwd}testsuite/foo.c:30',
            )
        self.cltest_redir(cmd, expected)

    def test_032(self):
        """Check the project command saves at most one breakpoint per line"""
        cmd = [
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'Cbreak foo',
            'Cbreak foo',
            'Cbreak main',
            'Cproject ${test_out}',
            'qa!',
            ]
        expected = (
            debuggee,
            'break ${cwd}testsuite/foo.c:30',
            'break ${cwd}testsuite/foobar.c:10',
            )
        self.cltest_redir(cmd, expected)

    def test_033(self):
        """Project option sources a project file"""
        self.setup_project_tests('%s1' % TESTFN_FILE)
        cmd = [
            'edit testsuite/foobar.c',
            'Cecho',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            '--- Signs ---',
            'Signs for testsuite/foobar.c:',
            '    line=10  id=2  name=1',
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
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Cbreak foo',
            'Cset args foo \\"1 2 3\\" bar',
            'Cquit',
            'qa!',
            ]
        expected = (
            'cd ${cwd}',
            debuggee,
            'set args foo "1 2 3" bar',
            'break ${cwd}testsuite/foobar.c:10',
            'break ${cwd}testsuite/foo.c:30',
            )
        self.cltest_redir(cmd, expected)

    def test_035(self):
        """Project option saves a project file on quitting from Vim"""
        self.setup_project_tests(TESTFN_OUT)
        cmd = [
            'Cfile testsuite/foobar',
            'Cbreak main',
            'qa!',
            ]
        expected = (
            'cd ${cwd}',
            debuggee,
            'break ${cwd}testsuite/foobar.c:10',
            )
        self.cltest_redir(cmd, expected)

    def test_036(self):
        """The quit command prints a separation line"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cquit',
            'edit (clewn)_console | $$ | w!  ${test_out}',
            'qa!',
            ]
        expected = (
            '=== End of gdb session ===\n',
            )
        self.cltest_redir(cmd, expected)

    def test_037(self):
        """Check number 1, adding breakpoints after a quit"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Cquit',
            'Cfile testsuite/foobar',
            'Cbreak ${cwd}testsuite/foobar.c:16',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for testsuite/foobar.c:",
            "line=16  id=2  name=1",
            )
        self.cltest_redir(cmd, expected)

    def test_038(self):
        """Check number 2, adding breakpoints after a quit"""
        cmd = [
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Cbreak foo',
            'Cquit',
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'Cbreak foo',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for ${cwd}testsuite/foo.c:",
            "line=30  id=4  name=3",
            "line=30  id=6  name=1",
            )
        self.cltest_redir(cmd, expected)

    def test_039(self):
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
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for testsuite/foobar.c:",
            "line=10  id=6  name=3",
            "line=10  id=2  name=1",
            )
        self.cltest_redir(cmd, expected)

    def test_040(self):
        """Check number 4, adding breakpoints after a quit"""
        cmd = [
            'edit testsuite/foobar.c',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Cbreak foo',
            'Cquit',
            'sleep ${sleep_time}',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Cbreak main',
            'Cquit',
            'sleep ${sleep_time}',
            'Cfile testsuite/foobar',
            'Cbreak main',
            'Cbreak foo',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for testsuite/foobar.c:",
            "line=10  id=2  name=1",
            "Signs for ${cwd}testsuite/foo.c:",
            "line=30  id=4  name=3",
            )
        self.cltest_redir(cmd, expected)

    def test_041(self):
        """Set a breakpoint in a template function"""
        cmd = [
            'Cfile testsuite/function_template',
            'Cbreak ${cwd}testsuite/function_template_sub/localmax.cpp:7',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for ${cwd}testsuite/function_template_sub/localmax.cpp:",
            "line=7  id=2  name=1",
            )
        self.cltest_redir(cmd, expected)

    def test_042(self):
        """Check starting the session with the 'sigint' command"""
        cmd = [
            'Csigint',
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        expected = (
            "Signs for ${cwd}testsuite/foo.c:",
            "line=30  id=2  name=1",
            )
        self.cltest_redir(cmd, expected)

    def test_043(self):
        """Check the frame command moves the cursor to the frame location"""
        cmd = [
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'Crun',
            'edit testsuite/foobar.c',
            'echo bufname("%")',
            'Cframe 0',
            'sleep ${sleep_time}',
            'redir! > ${test_out}',
            'echo bufname("%")',
            'qa!',
            ]
        expected = (
            "${cwd}testsuite/foo.c",
            )
        self.cltest_redir(cmd, expected)

    def test_044(self):
        """Set a breakpoint after a 'throw' catchpoint"""
        cmd = [
            'edit testsuite/overloaded.cc',
            'Cfile testsuite/overloaded',
            'Cstart',
            'Ccatch throw',
            'Cbreak main',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        self.cltest_redir(cmd, expected_break_main)

    def test_045(self):
        """Set a breakpoint after deleting a 'throw' catchpoint"""
        cmd = [
            'edit testsuite/overloaded.cc',
            'Cfile testsuite/overloaded',
            'Cstart',
            'Ccatch throw',
            'Cdelete 2',
            'Cbreak main',
            'redir! > ${test_out}',
            'sign place',
            'qa!',
            ]
        self.cltest_redir(cmd, expected_break_main)

    def test_046(self):
        """Test the (clewn)_breakpoints list buffer."""
        cmd = [
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'Cenable delete 1',
            'Cbreak foo',
            'Cbreak nanosleep',
            'Cbreak nanosleep',
            'Cbreak nanosleep',
            'Cdelete 3',
            'Crun',
            'Cdisable 2 4',
            'edit (clewn)_breakpoints | %w!  ${test_out}',
            'edit ${test_out}',
            r'%s/\(.*\) <.*>$$/\1',
            'write',
            'qa!',
            ]
        expected = (
            '2 breakpoint n 1 keep in foo at foo.c:30',
            '4 breakpoint n 0 keep in nanosleep',
            '5 breakpoint y 0 keep in nanosleep',
            )
        self.cltest_redir(cmd, expected)

    def test_047(self):
        """Test the (clewn)_backtrace list buffer."""
        cmd = [
            'Cfile testsuite/foobar',
            'Cbreak nanosleep',
            'Crun',
            'Cup',
            'edit (clewn)_backtrace | %w!  ${test_out}',
            'edit ${test_out}',
            r'%s/\(.*\) <.*>$$/\1',
            'write',
            'qa!',
            ]
        expected = (
            '  #0   in nanosleep',
            '* #1   in msleep at foo.c',
            '  #2   in foo at foo.c',
            '  #3   in main at foobar.c',
            )
        self.cltest_redir(cmd, expected)

    def test_048(self):
        """Test the <CR> map in (clewn)_backtrace."""
        cmd = [
            'Cfile testsuite/foobar',
            'Cbreak nanosleep',
            'Crun',
            'edit (clewn)_backtrace',
            '2',
            'exe "normal \<CR>"',
            'sleep ${sleep_time}',
            'redir! > ${test_out}',
            'echo bufwinnr("${cwd}testsuite/foo.c") != -1',
            'qa!',
            ]
        expected = (
            '1',
            )
        self.cltest_redir(cmd, expected)

    def test_049(self):
        """Test the (clewn)_threads list buffer."""
        cmd = [
            'Cfile %s' % sys.executable,
            'Cset args testsuite/foo_thread.py',
            'Cbreak sys_getrecursionlimit',
            'Cbreak sys_getdefaultencoding',
            'Crun',
            'edit (clewn)_threads | 2write! ${test_out}',
            'Ccontinue',
            'edit (clewn)_threads | 3write! >> ${test_out}',
            'edit ${test_out}',
            r'%s/\(python\).*in \(\S\+\).*$$/\1 \2',
            'write',
            'qa!',
            ]
        expected = (
            '* 1   python sys_getrecursionlimit',
            '* 2   python sys_getdefaultencoding',
            )
        self.cltest_redir(cmd, expected)

    def test_050(self):
        """Test the <CR> map in (clewn)_threads."""
        cmd = [
            'Cfile %s' % sys.executable,
            'Cset args testsuite/foo_thread.py',
            'Cbreak sys_getrecursionlimit',
            'Crun',
            'edit (clewn)_threads',
            '3',
            'exe "normal \<CR>"',
            'sleep ${sleep_time}',
            'call Edit_clewnbuffer("(clewn)_threads") | 2write! ${test_out}',
            'edit ${test_out}',
            r'%s/\(python\).*in \(\S\+\).*$$/\1 \2',
            'write',
            'qa!',
            ]
        expected = (
            '  1   python sys_getrecursionlimit',
            )
        self.cltest_redir(cmd, expected)

    def test_051(self):
        """Test the <CR> map in (clewn)_breakpoints."""
        cmd = [
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'Cstart',
            'edit (clewn)_breakpoints',
            '2',
            'exe "normal \<CR>"',
            'sleep ${sleep_time}',
            'redir! > ${test_out}',
            'echo bufwinnr("${cwd}testsuite/foo.c") != -1',
            'qa!',
            ]
        expected = (
            '1',
            )
        self.cltest_redir(cmd, expected)

    def test_052(self):
        """'Cbreak' as the first command, does highlight the breakpoint."""
        sys.argv.append('--args=testsuite/foobar')
        cmd = [
            'Cbreak foo',
            'redir! > ${test_out}',
            'echo bufwinnr("${cwd}testsuite/foo.c") != -1',
            'qa!',
            ]
        expected = (
            '1',
            )
        self.cltest_redir(cmd, expected)

    def test_053(self):
        """Test the watchpoints in the (clewn)_breakpoints list buffer."""
        cmd = [
            'Cfile testsuite/foobar',
            'Cbreak foo',
            'Cstart',
            'Cwatch -l len',
            'Cwatch -l len',
            'Cawatch -l len',
            'Crwatch -l len',
            'Cnext',
            'Cnext',
            'Cdisable 5 6',
            'Cdelete 3',
            'edit (clewn)_breakpoints | %w!  ${test_out}',
            'edit ${test_out}',
            r'%s/\(.*\) <.*>$$/\1',
            'write',
            'qa!',
            ]
        expected = (
            '1 breakpoint      y 0 keep   in foo at foo.c:30',
            '4 hw watchpoint   y 1 keep  -location len',
            '5 acc watchpoint  n 2 keep  -location len',
            '6 read watchpoint n 1 keep  -location len',
            )
        self.cltest_redir(cmd, expected)

