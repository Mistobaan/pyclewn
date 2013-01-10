"""Debugged script used by the test suite."""
import sys
from testsuite import foo

def main():
    """Main."""
    run = sys.argv[1:] and sys.argv[1:][0]
    do_sleep = sys.argv[2:] and sys.argv[2:][0]
    foo.foo(run, do_sleep, 'unused')
    print 'Terminated.'

if __name__ == '__main__':
    import clewn.vim as vim; vim.pdb(testrun=True,
                            level='nbdebug', file='logfile')
    main()
    next_line = 1

