# vi:set ts=8 sts=4 sw=4 et tw=80:
"""
Supporting definitions for the pyclewn regression tests.
"""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from io import open

import sys
import os
import string
import time
import traceback
import random
from unittest import TestCase, TestResult
from unittest.result import failfast

import clewn.vim

LOGFILE = 'logfile'
TESTRUN_SLEEP_TIME = 800
SLOW_DOWN_TESTS = 40

# filenames used for testing
TESTFN = '@test'
TESTFN_FILE = TESTFN + '_file_'
TESTFN_OUT = TESTFN + '_out'

# Wait for pyclewn to process all the previous commands.
# Wait for the expected string passed as the argument to the function, or run
# the 'dumprepr' command and wait for the command.
WAIT_EOP = """
let g:testrun_key = ${key}
function Wait_eop(...)
   let g:testrun_key += 1
   let l:marker = "dumprepr " . g:testrun_key
   if a:0 == 0
       exe "C" . l:marker
   endif
   let l:start = localtime()
   let l:lnum = 1
   while 1
       " Allow vim to process netbeans events and messages.
       sleep 10m
       if ${timeout} > 0 && localtime() - l:start > ${timeout}
           break
       endif
       let l:lines = getbufline("(clewn)_console", l:lnum, "$$")
       let l:index = 0
       while l:index < len(l:lines)
          let l:line = l:lines[l:index]
           if a:0 != 0
               if l:line == a:1
                   return
               endif
           elseif l:line =~# l:marker
               return
           endif
          let l:index = l:index + 1
       endwhile
       if l:index != 0
           " The last line may be partially written, so include it in the next
           " search.
           let l:lnum = l:lnum + l:index - 1
       endif
   endwhile
endfunction
"""

GOTO_BUFFER = """
function Goto_buffer(name)
    for l:winidx in range(winnr('$$'))
        let l:winno = l:winidx + 1
        if bufname(winbufnr(l:winno)) == a:name
            exe l:winno . "wincmd w"
            return
        endif
    endfor
endfunction
"""

def cmd_append(commands, append, wait_for=None, cmd_list=None, exclude=None, do_all=False):
    """
    >>> commands = ['Cfoo', 'Cbar', 'Cquit', 'Cfoo', 'Cfoobar']
    >>> wait_for = {}
    >>> wait_for['Cquit'] = '=== End of gdb session ==='
    >>> exclude = ['Cfoobar']
    >>> commands = cmd_append(iter(commands), 'call Wait_eop()',
    ...                       wait_for=wait_for, exclude=exclude)
    >>> print('\\n'.join(commands))
    Cfoo
    Cbar
    call Wait_eop()
    Cquit
    call Wait_eop("=== End of gdb session ===")
    Cfoo
    call Wait_eop()
    Cfoobar

    >>> commands = cmd_append(iter(['Cfoo', 'Cbar']), 'sleep 100m',
    ...                            cmd_list=('Cfoo',))
    >>> print('\\n'.join(commands))
    Cfoo
    sleep 100m
    Cbar

    >>> commands = ['Cfoo', 'Cbar', 'Cfoobar']
    >>> exclude = ['Cbar']
    >>> commands = cmd_append(iter(commands), 'sleep 100m', exclude=exclude,
    ...                       do_all=True)
    >>> print('\\n'.join(commands))
    Cfoo
    sleep 100m
    Cbar
    Cfoobar
    sleep 100m
    """

    try:
        next_cmd = next(commands)
    except StopIteration:
        assert False

    while True:
        cmd = next_cmd
        yield cmd
        try:
            next_cmd = next(commands)
        except StopIteration:
            next_cmd = None

        if cmd_list:
            if cmd in cmd_list:
                yield append
        elif do_all:
            if cmd.startswith('C') and (not exclude or cmd not in exclude):
                yield append
        elif wait_for and cmd in wait_for:
            yield 'call Wait_eop("%s")' % wait_for[cmd]
        elif (cmd.startswith('C') and
                (not exclude or cmd not in exclude) and
                (not next_cmd or next_cmd in exclude or
                    next_cmd == 'Cquit' or
                    (not next_cmd.startswith('C') and
                        not next_cmd.startswith('call Wait_eop') and
                        not next_cmd.startswith('sleep')
                        ))):
            yield append

        if next_cmd is None:
            return

def get_description(test):
    """"Return a ClewnTestCase description."""
    description = test.shortDescription() or ''
    return '<%s:%s> %s' % (test.__class__.__name__, test.method, description)

class ClewnTestCase(TestCase):
    """Pyclewn test case abstract class.

    In verbose mode, pyclewn runs at 'nbdebug' log level and the log is
    written to LOGFILE.

    """
    _verbose = False
    _debug = False

    def __init__(self, method='runTest'):
        TestCase.__init__(self, method)
        self.method = method
        self.pdb_script = None
        self.fnull = None
        self.debugger = None
        self.netbeans_port = 3219

    def setUp(self):
        """Setup pyclewn arguments."""
        sys.argv = [
            '-c',
            '--netbeans=:%d' % self.netbeans_port,
            '--cargs',
                '-u NORC -N '
                '-U NONE '
                '-s %s' % TESTFN,
        ]
        sys.argv.append('--editor=%s' % os.environ.get('EDITOR', 'gvim'))
        if self.debugger != 'pdb':
            sys.argv.append('--file=logfile')
            if self._verbose:
                sys.argv.append('--level=nbdebug')

    def setup_vim_arg(self, newarg):
        """Add a new Vim argument to the existing arguments."""
        argv = sys.argv
        i = argv.index('--cargs')
        argv.pop(i)
        assert len(argv) > i + 1
        args = argv.pop(i)
        args += ' ' + newarg
        argv.append('--cargs')
        argv.append(args)

    def tearDown(self):
        """Cleanup stuff after the test."""
        if self.fnull:
            self.fnull.close()
        for name in os.listdir(os.getcwd()):
            if name.startswith(TESTFN):
                try:
                    os.unlink(name)
                except OSError:
                    pass

    def clewn_test(self, commands, expected, outfile, *test):
        """The test method.

        arguments:
            commands: list of str
                the commands sourced by vim
            expected: list of str
                expected strings that must be found in outfile
            outfile: str
                the output file name
            test: argument list
                the content of the test files that vim is loading

        The result check ignores changes in the amount of white space
        (including new lines).

        """

        not_a_pyclewn_method = ['Cunmapkeys', 'Ccwindow', 'Cdefine',
                                'Ccommands', 'Cdocument']
        exclude = not_a_pyclewn_method + ['Csymcompletion']
        if self.debugger == 'pdb':
            exclude.extend(('Ccontinue', 'Cdetach'))
        wait_for = {}
        if self.debugger == 'gdb':
            wait_for['Cquit'] = '=== End of gdb session ==='
        commands = cmd_append(iter(commands), 'call Wait_eop()',
                              wait_for=wait_for, exclude=exclude)

        if self.debugger == 'pdb':
            commands = cmd_append(commands, 'sleep %dm' % TESTRUN_SLEEP_TIME,
                          cmd_list=('Pyclewn pdb', 'Cinterrupt', 'Ccontinue',
                                    'Cdetach'))

        # Slow down the tests.
        commands = cmd_append(commands, 'sleep %dm' % SLOW_DOWN_TESTS,
                              exclude=exclude, do_all=True)
        commands = '%s\n:%s\n:%s\n' % (
                                    '\n:'.join(WAIT_EOP.split('\n')),
                                    '\n:'.join(GOTO_BUFFER.split('\n')),
                                    '\n:'.join(commands))

        cwd = os.getcwd() + os.sep
        # Wait_eop timeout.
        if self._debug:
            timeout = -1
        else:
            timeout = 5
        commands = string.Template(commands).substitute(
                                    test_file=TESTFN_FILE,
                                    test_out=TESTFN_OUT,
                                    key=random.randint(0, 1000000000),
                                    timeout=timeout,
                                    sleep_time='%dm' % TESTRUN_SLEEP_TIME,
                                    cwd=cwd)
        #print(commands) # XXX

        # Write the commands.
        with open(TESTFN, 'w') as fp:
            fp.write(commands)

        # Write the test files.
        for i, t in enumerate(test):
            with open(TESTFN_FILE + str(i+1), 'w') as fp:
                fp.write(t)

        # Enable the debugging of this test case.
        if self._debug:
            clewn.vim.pdb()
        # Process the commands.
        vim = clewn.vim.main(True)
        # Remove the Vim script file in case the script failed to remove itself.
        if hasattr(vim, 'f_script'):
            del vim.f_script

        # Check the result.
        with open(outfile, 'r') as fp:
            output = fp.read()

        expected = '\n'.join(expected)
        expected = string.Template(expected).substitute(
                                            cwd=cwd, test_file=TESTFN_FILE)

        checked = ' '.join(expected.split()) in ' '.join(output.split())
        self.assertTrue(checked,
                "\n\n...Expected:\n%s \n\n...Got:\n%s" % (expected, output))

    def cltest_redir(self, commands, expected, *test):
        """Test result redirected by vim to TESTFN_OUT."""
        self.clewn_test(commands, expected, TESTFN_OUT, *test)

    def cltest_logfile(self, commands, expected, level, *test):
        """Test result in the log file."""
        sys.argv.append('--level=%s' % level)
        self.clewn_test(commands, expected, LOGFILE, *test)

class TextTestResult(TestResult):
    """A test result class that prints formatted text results to a stream."""
    separator1 = '=' * 70
    separator2 = '-' * 70

    def __init__(self, stream, verbose, stop_on_error):
        TestResult.__init__(self)
        self.stream = stream
        self.verbose = verbose
        self.failfast = stop_on_error

    def startTest(self, test):
        "Called when the given test is about to be run"
        TestResult.startTest(self, test)
        if self.verbose:
            self.stream.write(get_description(test))
            self.stream.write(' ... ')

    def addSuccess(self, test):
        "Called when a test has completed successfully"
        TestResult.addSuccess(self, test)
        if self.verbose:
            self.stream.write('ok\n')
        else:
            self.stream.write('.')
            self.stream.flush()

    @failfast
    def addError(self, test, err):
        """Called when an error has occurred."""
        TestResult.addError(self, test, err)
        if self.verbose:
            self.stream.write('ERROR\n')
        else:
            self.stream.write('E')
            self.stream.flush()

    @failfast
    def addFailure(self, test, err):
        """Called when an error has occurred."""
        exctype, value, _ = err
        # do not print the traceback on failure
        self.failures.append((test,
                ''.join(traceback.format_exception(exctype, value, None))))
        if self.verbose:
            self.stream.write('FAIL\n')
        else:
            self.stream.write('F')
            self.stream.flush()

    def addSkip(self, test, reason):
        """Called when a test is skipped."""
        TestResult.addSkip(self, test, reason)
        if self.verbose:
            self.stream.write('skipped (%s)\n' % reason)
        else:
            self.stream.write('s')
            self.stream.flush()

    def print_errors(self):
        """"Print the errors and failures."""
        self.stream.write('\n')
        self.print_error_list('ERROR', self.errors)
        self.print_error_list('FAIL', self.failures)

    def print_error_list(self, flavour, errors):
        """"Print the list of one flavour of errors."""
        for test, err in errors:
            self.stream.write(self.separator1)
            self.stream.write('\n%s: %s\n' % (flavour, get_description(test)))
            self.stream.write(self.separator2)
            self.stream.write('\n%s\n' % err)

class TextTestRunner(object):
    """A test runner class that prints results as they are run and a summary."""
    def __init__(self, verbose, stop_on_error, stream=sys.stderr):
        self.verbose = verbose
        self.stop_on_error = stop_on_error
        self.stream = stream

    def run(self, test):
        """Run the given test case or test suite."""
        result = TextTestResult(self.stream, self.verbose, self.stop_on_error)
        start = time.time()
        test(result)
        stop = time.time()
        elapsed = stop - start

        result.print_errors()

        # print the summary
        self.stream.write(result.separator2)
        run = result.testsRun
        self.stream.write('\nRan %d test%s in %.3fs\n\n' %
                            (run, run != 1 and 's' or '', elapsed))

        infos = []
        if not result.wasSuccessful():
            self.stream.write('FAILED')
            failed, errored = map(len, (result.failures, result.errors))
            if failed:
                infos.append('failures=%d' % failed)
            if errored:
                infos.append('errors=%d' % errored)
        else:
            self.stream.write('OK')
        skipped = len(result.skipped)
        if skipped:
            infos.append('skipped=%d' % skipped)
        if infos:
            self.stream.write(' (%s)\n' % (', '.join(infos),))
        else:
            self.stream.write('\n')
        return result

def run_suite(suite, verbose, stop_on_error, debug):
    """Run the suite."""
    ClewnTestCase._verbose = verbose
    ClewnTestCase._debug = debug
    TextTestRunner(verbose, stop_on_error).run(suite)

def _test():
    """Run the doctests."""
    import doctest
    doctest.testmod()

if __name__ == "__main__":
    _test()

