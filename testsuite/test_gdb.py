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

import sys
import os
import unittest
from test.test_support import run_unittest

from clewn.misc import check_call
from testsuite.test_support import ClewnTestCase

class GdbTestCase(ClewnTestCase):
    """Test the gdb debugger."""

    def setUp(self):
        ClewnTestCase.setUp(self)
        sys.argv.append('--gdb')

    def setup_gdb_args(self, args=''):
        """Setup gdb args and redirect debuggee output to /dev/null."""
        if hasattr(os, 'devnull'):
            terminal = os.devnull
        else:
            terminal = '/dev/null'
        sys.argv.extend(['-a', ('-tty=%s %s' % (terminal, args))])

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

            'gdb CRITICAL this is not a gdb program\n',

            'error'
            )

    def test_bad_gdbpath(self):
        """The gdb program is not a valid pathname"""
        foobar = '/path/to/nowhere/foobar'
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
            ':Cshow height\n'
            ':sleep ${time}\n'
            ':Cshow width\n'
            ':sleep ${time}\n'
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
            ':Cshow height\n'
            ':sleep ${time}\n'
            ':Cquit\n'
            ':sleep ${time}\n'
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
            ':Cfile testsuite/foobar\n'
            ':sleep ${time}\n'
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
            ':Cbreak foo\n'
            ':sleep ${time}\n'
            ':Crun\n'
            ':sleep ${time}\n'
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
            ':Cfile testsuite/foobar\n'
            ':sleep ${time}\n'
            ':Cset con\n'       # set confirm command
            ':sleep ${time}\n'
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
            ':Cfile testsuite/foobar\n'
            ':sleep ${time}\n'
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
            ':Cfile testsuite/foobar\n'
            ':sleep ${time}\n'
            ':Cbreak main\n'
            ':sleep ${time}\n'
            ':Crun\n'
            ':sleep ${time}\n'
            ':Cdumprepr\n'
            ':sleep ${time}\n'
            ":edit (clewn)_console | $$ | ?'info'?,/'last_balloon'/w!  ${test_out}\n"
            ':qa!\n',

            "'file': {'file': 'foobar.c',\n"
            "         'fullname': '${cwd}testsuite/foobar.c',\n"
            "         'line': '4'},\n"
            "'frame': {'line': '9', 'file': 'foobar.c', 'func': 'main', 'level': '0'},\n"
            )

    def test_frame_sign(self):
        """Check frame sign"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':Cfile testsuite/foobar\n'
            ':sleep ${time}\n'
            ':Cbreak main\n'
            ':sleep ${time}\n'
            ':Crun\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':qa!\n',

            "Signs for testsuite/foobar.c:\n"
            "    line=9  id=2  name=3\n"
            "    line=9  id=1  name=1\n"
            )

    def test_annotation_lvl1(self):
        """Check annotations level 1 are removed"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':Cfile testsuite/foobar\n'
            ':sleep ${time}\n'
            ':Cbreak main\n'
            ':sleep ${time}\n'
            ':Crun\n'
            ':sleep ${time}\n'
            ':Cstep\n'
            ':sleep ${time}\n'
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
            ':Cfile testsuite/foobar\n'
            ':sleep ${time}\n'
            ':Cbreak main\n'
            ':sleep ${time}\n'
            ':Cdisable 1\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':qa!\n',

            "Signs for testsuite/foobar.c:\n"
            "line=9  id=1  name=2\n"
            )

    def test_delete_once(self):
        """Check breakpoint delete once"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':Cfile testsuite/foobar\n'
            ':sleep ${time}\n'
            ':Cbreak main\n'
            ':sleep ${time}\n'
            ':Cenable delete 1\n'
            ':sleep ${time}\n'
            ':Crun\n'
            ':sleep ${time}\n'
            ':Cstep\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':qa!\n',

            "Signs for testsuite/foobar.c:\n"
            "line=10  id=2  name=3\n"
            )

    def test_breakpoint_open_file(self):
        """Check setting a breakpoint open the source file"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':Cfile testsuite/foobar\n'
            ':sleep ${time}\n'
            ':Cbreak foo\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':qa!\n',

            "Signs for ${cwd}testsuite/foo.c:\n"
            "line=23  id=1  name=1\n"
            )

    def test_delete_bp(self):
        """Check delete breakpoint"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':Cfile testsuite/foobar\n'
            ':sleep ${time}\n'
            ':Cbreak main\n'
            ':sleep ${time}\n'
            ':Cbreak main\n'
            ':sleep ${time}\n'
            ':Cdelete 1\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':qa!\n',

            "Signs for testsuite/foobar.c:\n"
            "line=9  id=2  name=1\n"
            )

    def test_clear_on_frame(self):
        """Check clearing breakpoints on the frame sign line"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':Cfile testsuite/foobar\n'
            ':sleep ${time}\n'
            ':Cbreak main\n'
            ':sleep ${time}\n'
            ':Crun\n'
            ':sleep ${time}\n'
            ':Cclear\n'
            ':sleep ${time}\n'
            ':redir! > ${test_out}\n'
            ':sign place\n'
            ':qa!\n',

            "Signs for testsuite/foobar.c:\n"
            "line=9  id=2  name=3\n"
            )

    def test_break_completion(self):
        """Check break completion on overloaded functions"""
        self.cltest_logfile(
            ':edit testsuite/overloaded.cc\n'
            ':Cfile testsuite/overloaded\n'
            ':sleep ${time}\n'
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
            ':Cfile testsuite/foobar\n'
            ':sleep ${time}\n'
            ':Cbreak foo\n'
            ':sleep ${time}\n'
            ':Crun\n'
            ':sleep ${time}\n'
            ':Cstep\n'
            ':sleep ${time}\n'
            ':Cstep\n'
            ':sleep ${time}\n'
            ':Cstep\n'
            ':sleep ${time}\n'
            ':Cdbgvar map\n'
            ':sleep ${time}\n'
            ':Cfoldvar 1\n'
            ':sleep ${time}\n'
            ':Cdelvar var1.value\n'
            ':sleep ${time}\n'
            ":edit (clewn)_dbgvar | 1,$$w!  ${test_out}\n"
            ':qa!\n',

            "[-] var1: (map_t) map ={=} {...}\n"
            "   *  var1.key: (int) key ={=} 1\n"
            )

    def test_varobj_hilite(self):
        """Check varobj hiliting"""
        self.cltest_redir(
            ':edit testsuite/foobar.c\n'
            ':Cfile testsuite/foobar\n'
            ':sleep ${time}\n'
            ':Cbreak bar\n'
            ':sleep ${time}\n'
            ':Crun\n'
            ':sleep ${time}\n'
            ':Cstep\n'
            ':sleep ${time}\n'
            ':Cdbgvar i\n'
            ':sleep ${time}\n'
            ":edit (clewn)_dbgvar | 1,$$w!  ${test_out}\n"
            ':Cstep\n'
            ':sleep ${time}\n'
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
            ':Cfile testsuite/foobar\n'
            ':sleep ${time}\n'
            ':Cbreak foo\n'
            ':sleep ${time}\n'
            ':Crun\n'
            ':sleep ${time}\n'
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
            ':Cfile testsuite/foobar\n'
            ':sleep ${time}\n'
            ':Cbreak main\n'
            ':sleep ${time}\n'
            ':Crun\n'
            ':sleep ${time}\n'
            ':Cdbgvar len\n'
            ':sleep ${time}\n'
            ':Cprint len=555\n'
            ':sleep ${time}\n'
            ":edit (clewn)_dbgvar | 1,$$w! >> ${test_out}\n"
            ':qa!\n',

            " *  var1: (int) len ={*} 555"
            )


def test_main():
    # run make on the testsuite
    check_call(['make', '-C', 'testsuite'])

    suite = unittest.TestSuite()
    suite.addTest(GdbTestCase('test_completion'))
    suite.addTest(GdbTestCase('test_not_gdb'))
    suite.addTest(GdbTestCase('test_bad_gdbpath'))
    suite.addTest(GdbTestCase('test_initial_setup'))
    suite.addTest(GdbTestCase('test_new_session'))
    suite.addTest(GdbTestCase('test_sigint'))
    suite.addTest(GdbTestCase('test_gdb_arglist'))
    suite.addTest(GdbTestCase('test_gdb_illegal'))
    suite.addTest(GdbTestCase('test_symbols_completion'))
    suite.addTest(GdbTestCase('test_oob_command'))
    suite.addTest(GdbTestCase('test_frame_sign'))
    suite.addTest(GdbTestCase('test_annotation_lvl1'))
    suite.addTest(GdbTestCase('test_disable_bp'))
    suite.addTest(GdbTestCase('test_delete_once'))
    suite.addTest(GdbTestCase('test_breakpoint_open_file'))
    suite.addTest(GdbTestCase('test_delete_bp'))
    suite.addTest(GdbTestCase('test_clear_on_frame'))
    suite.addTest(GdbTestCase('test_break_completion'))
    suite.addTest(GdbTestCase('test_varobj'))
    suite.addTest(GdbTestCase('test_varobj_hilite'))
    suite.addTest(GdbTestCase('test_tabedit_bug'))
    suite.addTest(GdbTestCase('test_watch_print'))
    run_unittest(suite)

if __name__ == '__main__':
    test_main()

