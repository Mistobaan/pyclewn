"""Debugged script used by the test suite."""
import sys
import foo

def main():
    """Main."""
    run = sys.argv[1:] and sys.argv[1:][0]
    foo.foo(run, 'unused')
    print 'Terminated.'

if __name__ == '__main__':
    import clewn.vim as vim; vim.pdb(level='nbdebug', file='logfile')
    main()

