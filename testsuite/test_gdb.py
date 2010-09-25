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
import unittest
import testsuite.test_support as test_support

import clewn.gdb as gdb
import clewn.misc as misc
from test_support import ClewnTestCase, TESTFN_FILE, TESTFN_OUT

if os.name == 'nt':
    debuggee = 'file ${cwd}testsuite/foobar.exe'
else:
    debuggee = 'file ${cwd}testsuite/foobar'

gdb_v = gdb.gdb_version('gdb')

class GdbTestCase(ClewnTestCase):
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

    def test_completion(self):
        """The gdb commands completion in vim"""
        self.cltest_redir(
            ':redir! > ${test_out}\n'
            ':command Chelp\n'
            ':command Cfile\n'
            ':command Cmapkeys\n'
            ':qa!\n',

            'Name        Args Range Complete  Definition\n'
            'Chelp       *          custom    call s:nbcommand("help", <f-args>)\n'
            'Name        Args Range Complete  Definition\n'
            'Cfile       *          file      call s:nbcommand("file", <f-args>)\n'
            'Name        Args Range Complete  Definition\n'
            'Cmapkeys    *                    call s:nbcommand("mapkeys", <f-args>)\n'
            )

    def test_not_gdb(self):
        """The 'true' program is not a gdb program"""
        sys.argv.extend(['--pgm=true'])
        self.cltest_logfile(
            ':qa!\n',

            'gdb  CRITICAL cannot find the gdb version\n',

            'error'
            )

    def test_bad_gdbpath(self):
        """The gdb program is not a valid pathname"""
        foobar = 'path_to_nowhere%sfoobar' % os.sep
        sys.argv.extend(['--pgm=' + foobar])
        self.cltest_logfile(
            ':qa!\n',

            'gdb CRITICAL cannot start gdb as "%s"\n' % foobar,

            'error'
            )

    def test_initial_setup(self):
        """Test the height, width and confirm setup"""
        self.cltest_redir(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cshow height\n'
            ':Cshow width\n'
            ':Cshow confirm\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$ | ?show height?,$$w!  ${test_out}\n'
            ':qa!\n',

            '(gdb) show height\n'
            'Number of lines gdb thinks are in a page is unlimited.\n'
            '(gdb) show width\n'
            'Number of characters gdb thinks are in a line is unlimited.\n'
            '(gdb) show confirm\n'
            'Whether to confirm potentially dangerous operations is off.\n',

            'line 1\n'
            )

    def test_new_session(self):
        """Test that after quit, a new gdb session can be started"""
        self.cltest_logfile(
            ':edit ${test_file}1\n'
            ':sleep ${time}\n'
            ':Cshow height\n'
            ':Cquit\n'
            ':Cshow height\n'
            ':sleep ${time}\n'
            ':qa!\n',

            'new "gdb" instance\n',

            'info',

            'line 1\n'
            )

    def test_sigint(self):
        """The program is interrupted with the sigint command"""
        self.setup_gdb_args()
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Crun\n'
            ':sleep ${time}\n'
            ':Csigint\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$ | ?SIGINT?,?SIGINT?w!  ${test_out}\n'
            ':qa!\n',

            'Program received signal SIGINT, Interrupt.\n'
            )

    def test_gdb_arglist(self):
        """The gdb program can be run with --args argument list"""
        self.setup_gdb_args('--args testsuite/foobar 55')
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cbreak foo\n'
            ':Crun\n'
            ':Cprint max\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$ | $$-1w!  ${test_out}\n'
            ':qa!\n',

            '$$1 = 55\n'
            )

    def test_gdb_illegal(self):
        """Illegal commands are rejected"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cset con\n'       # set confirm command
            ':C she\n'          # shell command
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$ | ?con?,$$-1w!  ${test_out}\n'
            ':qa!\n',

            '(gdb) set con\n'
            'Illegal argument in pyclewn.\n'
            '(gdb) she\n'
            'Illegal command in pyclewn.\n'
            )

    def test_symbols_completion(self):
        """The break and clear commands symbols completion"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':redir! > ${test_out}\n'
            ':Csymcompletion\n'
            ':\n\n'
            ':qa!\n',

            'symbols fetched for break and clear completion\n'
            )

    def test_oob_command(self):
        """Checking result of oob commands"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak main\n'
            ':Crun\n'
            ':Cdumprepr\n'
            ':sleep ${time}\n'
            ":edit (clewn)_console | $$ | ?'info'?,/'version'/w!  ${test_out}\n"
            ':qa!\n',

            "'file': {'file': 'foobar.c',\n"
            "         'fullname': '${cwd}testsuite/foobar.c',\n"
            "         'line': '4'},\n"
            "'frame': {'line': '9', 'file': 'foobar.c', 'func': 'main', 'level': '0'},\n"
            )

    def test_oob_command_v_64(self):
        """Checking result of oob commands"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak main\n'
            ':Crun\n'
            ':sleep ${time}\n'
            ':Cdumprepr\n'
            ':sleep ${time}\n'
            ":edit (clewn)_console | $$ | ?'info'?,/'version'/w!  ${test_out}\n"
            ':qa!\n',

            "'file': {'file': 'foobar.c',\n"
            "         'fullname': '${cwd}testsuite/foobar.c',\n"
            "         'line': '4'},\n"
            "'frame': {'file': 'foobar.c',\n"
            "          'fullname': '${cwd}testsuite/foobar.c',\n"
            "          'func': 'main',\n"
            "          'level': '0',\n"
            "          'line': '9'},\n"
            "'frameloc': {'lnum': 9,\n"
            "             'pathname': '${cwd}testsuite/foobar.c'},\n"
            )

    def test_oob_command_v_70(self):
        """Checking result of oob commands"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak main\n'
            ':Crun\n'
            ':sleep ${time}\n'
            ':Cdumprepr\n'
            ':sleep ${time}\n'
            ":edit (clewn)_console | $$ | ?'info'?,/'version'/w!  ${test_out}\n"
            ':qa!\n',

            "'file': {'file': 'foobar.c',\n"
            "         'fullname': '${cwd}testsuite/foobar.c',\n"
            "         'line': '9'},\n"
            "'frame': {'file': 'foobar.c',\n"
            "          'fullname': '${cwd}testsuite/foobar.c',\n"
            "          'func': 'main',\n"
            "          'level': '0',\n"
            "          'line': '9'},\n"
            "'frameloc': {'lnum': 9,\n"
            "             'pathname': '${cwd}testsuite/foobar.c'},\n"
            )

    def test_frame_sign(self):
        """Check frame sign"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak main\n'
            ':Crun\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':qa!\n',

            "Signs for testsuite/foobar.c:\n"
            "    line=9  id=3  name=3\n"
            "    line=9  id=1  name=1\n"
            )

    def test_annotation_lvl1(self):
        """Check annotations level 1 are removed"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak main\n'
            ':Crun\n'
            ':Cstep\n'
            ':Cstep\n'
            ':sleep ${time}\n'
            ":edit (clewn)_console | $$ | /(gdb) step/,$$w!  ${test_out}\n"
            ':qa!\n',

            "(gdb) step\n"
            "(gdb) step\n"
            )

    def test_disable_bp(self):
        """Check disable breakpoint"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak main\n'
            ':Cdisable 1\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':qa!\n',

            "Signs for testsuite/foobar.c:\n"
            "line=9  id=2  name=2\n"
            )

    def test_delete_once(self):
        """Check breakpoint delete once"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak main\n'
            ':Cenable delete 1\n'
            ':Crun\n'
            ':Cstep\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':qa!\n',

            "Signs for testsuite/foobar.c:\n"
            "line=10  id=3  name=3\n"
            )

    def test_breakpoint_open_file(self):
        """Check setting a breakpoint open the source file"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak foo\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':qa!\n',

            "Signs for ${cwd}testsuite/foo.c:\n"
            "line=30  id=1  name=1\n"
            )

    def test_delete_bp(self):
        """Check delete breakpoint"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak main\n'
            ':Cbreak main\n'
            ':Cdelete 1\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':qa!\n',

            "Signs for testsuite/foobar.c:\n"
            "line=9  id=3  name=3\n"
            )

    def test_clear_on_frame(self):
        """Check clearing breakpoints on the frame sign line"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak main\n'
            ':Crun\n'
            ':Cclear\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':qa!\n',

            "Signs for testsuite/foobar.c:\n"
            "line=9  id=3  name=3\n"
            )

    def test_break_completion(self):
        """Check break completion on overloaded functions"""
        self.cltest_logfile(
            ':edit testsuite/overloaded.cc\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/overloaded\n'
            ':Csymcompletion\n'
            ':\n\n'
            ':qa!\n',

            'gdb  DEBUG   ~"break test()\\n"\n'
            'gdb  DEBUG   ~"break test(int)\\n"\n'
            'gdb  DEBUG   ~"break test(int, int)\\n"\n',

            'debug'
            )

    def test_varobj(self):
        """Check varobj creation, folding and deletion"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak foo\n'
            ':Crun\n'
            ':Cstep\n'
            ':Cstep\n'
            ':Cstep\n'
            ':Cdbgvar map\n'
            ':sleep ${time}\n'
            ':Cfoldvar 1\n'
            ':sleep ${time}\n'
            ':Cdelvar var1.value\n'
            ':sleep ${time}\n'
            ":buffer (clewn)_dbgvar | 1,$$w!  ${test_out}\n"
            ':qa!\n',

            "[-] var1: (map_t) map ={=} {...}\n"
            "   *  var1.key: (int) key ={=} 1\n"
            )

    def test_varobj_fold(self):
        """Check varobj folding"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak foo\n'
            ':Crun\n'
            ':Cstep\n'
            ':Cstep\n'
            ':Cstep\n'
            ':Cdbgvar map\n'
            ':Cdbgvar map\n'
            ':sleep ${time}\n'
            ':Cfoldvar 2\n'
            ':sleep ${time}\n'
            ':Cfoldvar 1\n'
            ':sleep ${time}\n'
            ':Cfoldvar 1\n'
            ':sleep ${time}\n'
            ':buffer (clewn)_dbgvar | 1,3w!  ${test_out}\n'
            ':qa!\n',

            "[+] var1: (map_t) map ={=} {...}\n"
            "[-] var2: (map_t) map ={=} {...}\n"
            "   *  var2.key  : (int   ) key   ={=} 1\n"
            )

    def test_varobj_hilite(self):
        """Check varobj hiliting"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak bar\n'
            ':Crun\n'
            ':Cstep\n'
            ':Cdbgvar i\n'
            ':sleep ${time}\n'
            ":edit (clewn)_dbgvar | 1,$$w!  ${test_out}\n"
            ':Cstep\n'
            ':Cstep\n'
            ':sleep ${time}\n'
            ":edit (clewn)_dbgvar | 1,$$w! >> ${test_out}\n"
            ':Cfinish\n'
            ':sleep ${time}\n'
            ":edit (clewn)_dbgvar | 1,$$w! >> ${test_out}\n"
            ':qa!\n',

            " *  var1: (int) i ={*} 0\n"
            " *  var1: (int) i ={=} 1\n"
            " *  var1: (int) i ={-} 1\n"
            )

    def test_tabedit_bug(self):
        """Check robustness against vim 'tabedit (clewn)_dbgvar' bug"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak foo\n'
            ':Crun\n'
            ':Cdbgvar map\n'
            ':sleep ${time}\n'
            ":edit (clewn)_dbgvar\n"
            ":tabedit (clewn)_dbgvar\n"
            ':Cshow annotate\n'
            ':sleep ${time}\n'
            ":1,$$w! >> ${test_out}\n"
            ':qa!\n',

            "[+] var1: (map_t) map ={=} {...}\n"
            )

    def test_watch_print(self):
        """Watched variables are updated when changed with the print command"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak main\n'
            ':Crun\n'
            ':Cdbgvar len\n'
            ':sleep ${time}\n'
            ':Cprint len=555\n'
            ':sleep ${time}\n'
            ":edit (clewn)_dbgvar | 1,$$w! >> ${test_out}\n"
            ':qa!\n',

            " *  var1: (int) len ={*} 555"
            )

    def test_frame_print(self):
        """Returning to the correct frame location after a print command"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak main\n'
            ':Cbreak foo\n'
            ':Crun\n'
            ':sleep ${time}\n'
            ':Cprint foo(\\"toto\\", 1)\n'
            ':Ccontinue\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':sign list\n'
            ':qa!\n',

            '--- Signs ---\n'
            'Signs for testsuite/foobar.c:\n'
            '    line=9  id=5  name=5\n'
            '    line=9  id=1  name=1\n'
            'Signs for ${cwd}testsuite/foo.c:\n'
            '    line=30  id=3  name=3\n'
            'sign 1 text=1  texthl=NB_1\n'
            'sign 2 text=1  texthl=NB_2\n'
            'sign 3 text=2  texthl=NB_3\n'
            'sign 4 text=2  texthl=NB_4\n'
            'sign 5 text==> texthl=NB_0\n'
            )

    def test_multiple_choice(self):
        """Set automatically all breakpoints on a multiple choice"""
        self.cltest_redir(
            ':edit testsuite/overloaded.cc\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/overloaded\n'
            ':Cbreak A::test\n'
            ':sleep ${time}\n'
            ':sleep ${time}\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':qa!\n',

            '--- Signs ---\n'
            'Signs for testsuite/overloaded.cc:\n'
            '    line=3  id=3  name=3\n'
            '    line=4  id=5  name=5\n'
            '    line=5  id=1  name=1\n'
            )

    def test_project_cmd(self):
        """Check the project command"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak main\n'
            ':Cbreak foo\n'
            ':Cset args foo \\"1 2 3\\" bar\n'
            ':Cproject ${test_out}\n'
            ':sleep ${time}\n'
            ':qa!\n',

            'cd ${cwd}\n'
            + debuggee + '\n'
            'set args foo "1 2 3" bar\n'
            'break ${cwd}testsuite/foobar.c:9\n'
            'break ${cwd}testsuite/foo.c:30\n'
            )

    def test_project_cmd_unique_bp(self):
        """Check the project command saves at most one breakpoint per line"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak foo\n'
            ':Cbreak foo\n'
            ':Cbreak foo\n'
            ':Cbreak main\n'
            ':Cproject ${test_out}\n'
            ':sleep ${time}\n'
            ':qa!\n',

            debuggee + '\n'
            'break ${cwd}testsuite/foo.c:30\n'
            'break ${cwd}testsuite/foobar.c:9\n'
            )

    def test_project_option_load(self):
        """Project option sources a project file"""
        self.setup_project_tests('%s1' % TESTFN_FILE)
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cecho\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':qa!\n',

            '--- Signs ---\n'
            'Signs for testsuite/foobar.c:\n'
            '    line=9  id=1  name=1\n'
            'Signs for ${cwd}testsuite/foo.c:\n'
            '    line=30  id=3  name=3\n',

            'cd testsuite\n'
            'file foobar\n'
            'break main\n'
            'break foo\n'
            )

    def test_project_option_save(self):
        """Project option saves a project file"""
        self.setup_project_tests(TESTFN_OUT)
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak main\n'
            ':Cbreak foo\n'
            ':Cset args foo \\"1 2 3\\" bar\n'
            ':sleep ${time}\n'
            ':Cquit\n'
            ':sleep ${time}\n'
            ':qa!\n',

            'cd ${cwd}\n'
            + debuggee + '\n'
            'set args foo "1 2 3" bar\n'
            'break ${cwd}testsuite/foobar.c:9\n'
            'break ${cwd}testsuite/foo.c:30\n'
            )

    def test_project_option_vimquit(self):
        """Project option saves a project file on quitting from Vim"""
        self.setup_project_tests(TESTFN_OUT)
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak main\n'
            ':sleep ${time}\n'
            ':sleep ${time}\n'
            ':qa!\n',

            'cd ${cwd}\n'
            + debuggee + '\n'
            'break ${cwd}testsuite/foobar.c:9\n'
            )

    def test_quit_display(self):
        """The quit command prints a separation line"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cquit\n'
            ':sleep ${time}\n'
            ':edit (clewn)_console | $$ | w!  ${test_out}\n'
            ':qa!\n',

            '===========\n'
            )

    def test_cwindow_command(self):
        """The cwindow command opens the quickfix window of breakpoints"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':sleep ${time}\n'
            ':Cfile testsuite/foobar\n'
            ':Cbreak foo\n'
            ':Cbreak bar\n'
            ':Cbreak bar\n'
            ':Cdisable 1\n'
            ':Cdelete 2\n'
            ':sleep ${time}\n'
            ':Ccwindow\n'
            ':sleep ${time}\n'
            ":1,$$w! >> ${test_out}\n"
            ':qa!\n',

            "${cwd}testsuite/foo.c|30| breakpoint 1 disabled\n"
            "${cwd}testsuite/bar.c|5| breakpoint 3 enabled\n"
            )


def test_main():
    """Run all the tests."""
    # run make on the testsuite
    misc.check_call(['make', '-C', 'testsuite'])

    suite = unittest.TestSuite()
    suite.addTest(GdbTestCase('test_completion'))
    suite.addTest(GdbTestCase('test_not_gdb'))
    suite.addTest(GdbTestCase('test_bad_gdbpath'))
    suite.addTest(GdbTestCase('test_initial_setup'))
    suite.addTest(GdbTestCase('test_new_session'))
    if not os.environ.has_key('CLEWN_PIPES')            \
            and not os.environ.has_key('CLEWN_POPEN')   \
            and os.name != 'nt':
        suite.addTest(GdbTestCase('test_sigint'))
    suite.addTest(GdbTestCase('test_gdb_arglist'))
    suite.addTest(GdbTestCase('test_gdb_illegal'))
    suite.addTest(GdbTestCase('test_symbols_completion'))
    if gdb_v.split('.') < '6.4'.split('.'):
        suite.addTest(GdbTestCase('test_oob_command'))
    elif gdb_v.split('.') < '7.0'.split('.'):
        suite.addTest(GdbTestCase('test_oob_command_v_64'))
    else:
        suite.addTest(GdbTestCase('test_oob_command_v_70'))
    suite.addTest(GdbTestCase('test_frame_sign'))
    suite.addTest(GdbTestCase('test_annotation_lvl1'))
    suite.addTest(GdbTestCase('test_disable_bp'))
    suite.addTest(GdbTestCase('test_delete_once'))
    suite.addTest(GdbTestCase('test_breakpoint_open_file'))
    suite.addTest(GdbTestCase('test_delete_bp'))
    suite.addTest(GdbTestCase('test_clear_on_frame'))
    suite.addTest(GdbTestCase('test_break_completion'))
    suite.addTest(GdbTestCase('test_varobj'))
    suite.addTest(GdbTestCase('test_varobj_fold'))
    suite.addTest(GdbTestCase('test_varobj_hilite'))
    suite.addTest(GdbTestCase('test_tabedit_bug'))
    suite.addTest(GdbTestCase('test_watch_print'))
    suite.addTest(GdbTestCase('test_frame_print'))
    suite.addTest(GdbTestCase('test_multiple_choice'))
    suite.addTest(GdbTestCase('test_project_cmd'))
    suite.addTest(GdbTestCase('test_project_cmd_unique_bp'))
    suite.addTest(GdbTestCase('test_project_option_load'))
    suite.addTest(GdbTestCase('test_project_option_save'))
    suite.addTest(GdbTestCase('test_project_option_vimquit'))
    suite.addTest(GdbTestCase('test_quit_display'))
    suite.addTest(GdbTestCase('test_cwindow_command'))
    test_support.run_suite(suite)

if __name__ == '__main__':
    test_main()

