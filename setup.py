import sys
if sys.version_info < (3, 0):
    sys.stderr.write("This version of pyclewn does not support Python 2.\n")
    sys.exit(1)
import os
import os.path
import string
import re
import subprocess
import distutils.core as core

from os.path import join as pathjoin
from distutils.command.install import install as _install
from distutils.command.sdist import sdist as _sdist
from distutils.command.build_scripts import build_scripts as _build_scripts
from unittest import defaultTestLoader

import clewn.vim as vim
import testsuite.test_support as test_support
from clewn import *


DESCRIPTION = """Pyclewn allows using Vim as a front end to a debugger.
The debugger output is redirected to a Vim window, the pyclewn console.
The debugger commands are mapped to Vim user-defined commands
with a common letter prefix, and with completion available on the
commands and their first argument. The controlling terminal of the
program to debug is the terminal used to launch pyclewn, or any other
terminal when the debugger allows it.
"""

DEBUGGERS = ('simple', 'gdb', 'pdb')
SCRIPTS = ['pdb-clone', 'pyclewn', 'runtime/bin/inferior_tty.py']
LONG_DESCRIPTION = DESCRIPTION

vimdir = os.environ.get('vimdir')
if not vimdir:
    path = vim.exec_vimcmd(['echon $VIM'])
    path = path.strip(' \t\r\n')
    if not os.path.isdir(path):
        nodir = ('Invalid data files path. $VIM="%s" is returned'
            ' by Vim, but this is not an existing directory.' % path)
        raise DistutilsExecError(nodir)
    vimdir = pathjoin(path, 'vimfiles')

DATA_FILES = [
    (pathjoin(vimdir, 'plugin'), ['runtime/plugin/pyclewn.vim']),
    (pathjoin(vimdir, 'autoload'), ['runtime/autoload/pyclewn.vim']),
    (pathjoin(vimdir, 'doc'), ['runtime/doc/pyclewn.txt']),
    (pathjoin(vimdir, 'macros'),
        [('runtime/.pyclewn_keys.%s' % d) for d in DEBUGGERS]),
    (pathjoin(vimdir, 'syntax'), ['runtime/syntax/dbgvar.vim']),
    ]

# installation path of pyclewn lib
pythonpath = None

def vim_features():
    """Abort if missing required Vim feature."""
    output = vim.exec_vimcmd(['version'])

    print('checking netbeans support in vim:', end=' ', file=sys.stderr)
    try:
        output.index('+netbeans_intg')
    except ValueError:
        raise DistutilsExecError('netbeans support in vim is required')
    print('yes', file=sys.stderr)

    print('checking auto commands support in vim:', end=' ', file=sys.stderr)
    try:
        output.index('+autocmd')
    except ValueError:
        raise DistutilsExecError('auto commands support in vim is required')
    print('yes', file=sys.stderr)

def build_vimhelp():
    """Add pyclewn help to Vim help."""
    helpdir = pathjoin(vimdir, 'doc')
    print('running Vim help tags file generation in %s' % helpdir, file=sys.stderr)
    vim.exec_vimcmd(['helptags ' + helpdir, 'echo v:version'])

class install(_install):
    """Specialized installer, check required Vim features support and
    rebuild help tags.

    """
    def run(self):
        global pythonpath
        pythonpath = self.install_platlib
        # rename the 'debugger' directory present in old versions
        debugger_dir = os.path.join(pythonpath, 'clewn', 'debugger')
        if os.path.isdir(debugger_dir):
            sys.stderr.write('renaming the debugger directory\n')
            os.rename(debugger_dir, debugger_dir + '.orig')

        print('Vim user data files location: "%s"' % vimdir)
        vim_features()
        _install.run(self)
        build_vimhelp()

def update_version(filename):
    """Update the version number in the content of filename."""
    content = []
    with open(filename, 'r+') as f:
        for line in f:
            line = line.replace('pyclewn-__tag__' , 'pyclewn-' + __tag__)
            content.append(line)
        f.seek(0)
        f.writelines(content)

def keymap_files():
    """Build key map files for each debugger."""
    with open('runtime/.pyclewn_keys.template') as tf:
        template = tf.read()
        for d in DEBUGGERS:
            with open('runtime/.pyclewn_keys.%s' % d, 'w') as f:
                f.write(string.Template(template).substitute(clazz=d))
                # cannot use absolute imports with python 2.4, so we are stuck
                # with pydb.py
                if d == 'pdb':
                    d = 'pydb'
                module = __import__('clewn.%s' % d,
                                    globals(), locals(), ['MAPKEYS'])
                mapkeys = getattr(module, 'MAPKEYS')
                for k in sorted(mapkeys):
                    if len(mapkeys[k]) == 2:
                        comment = ' # ' + mapkeys[k][1]
                        f.write('# %s%s\n' % (('%s : %s' %
                                (k, mapkeys[k][0])).ljust(30), comment))
                    else:
                        f.write('# %s : %s\n' % (k, mapkeys[k][0]))

class build_scripts(_build_scripts):
    """Specialized scripts builder.

    """
    def run(self):
        """Add pythonpath to pyclewn script in a 'home scheme' installation."""
        if pythonpath is not None and pythonpath not in sys.path:
            path_append = string.Template("sys.path.append('${pythonpath}')\n")
            self.executable += '\n\nimport sys\n'   \
                                + path_append.substitute(pythonpath=pythonpath)
        _build_scripts.run(self)

def hg_revert(pathnames):
    """Revert files in a mercurial repository."""
    # silently ignore all errors
    try:
        with open(os.devnull, 'r+') as fnull:
            for fname in pathnames:
                subprocess.call(['hg', 'revert', '--no-backup', fname],
                                stderr=fnull)
    except (IOError, OSError):
        pass

NOTTESTS = [
    'test_support',
    ]

def findtests(testdir, nottests=NOTTESTS):
    """Return a list of all applicable test modules."""
    names = os.listdir(testdir)
    tests = []
    for name in names:
        if name[:5] == 'test_' and name[-3:] == os.extsep + 'py':
            modname = name[:-3]
            if modname not in nottests:
                tests.append(modname)
    tests.sort()
    return tests

class sdist(_sdist):
    """Specialized sdister."""
    def run(self):
        update_version('runtime/plugin/pyclewn.vim')
        update_version('INSTALL')
        keymap_files()
        _sdist.run(self)
        hg_revert(('runtime/plugin/pyclewn.vim', 'INSTALL'))

class Test(core.Command):
    """Run the test suite.
    """

    user_options = [
        ('test=', 't',
            'run a comma separated list of tests, for example             '
            '"--test=simple,gdb", all the tests are run when this option'
            ' is not present'),
        ('prefix=', 'p', 'run only tests whose name starts with this prefix'),
        ('stop', 's', 'stop at the first test failure or error'),
        ('detail', 'd', 'detailed test output, each test case is printed'),
        ('pdb', 'b', 'debug a single test with pyclewn and pdb: start the'
                     ' test with \'python setup.py test --test=gdb --pdb -p'
                     ' test_021\''
                     ' then start a Vim instance and run'
                     ' \':let g:pyclewn_connection="localhost:3220:foo" |'
                     ' Pyclewn pdb\''),
    ]

    def initialize_options(self):
        self.test = None
        self.prefix = None
        self.stop = False
        self.detail = False
        self.pdb = False

    def finalize_options(self):
        if self.test is not None:
            self.test = ['test_' + t for t in self.test.split(',')]

    def run (self):
        """Run the test suite."""
        if self.pdb and self.test != ['test_gdb']:
            print('One can only debug a gdb test case for now.')
            return

        testdir = 'testsuite'
        tests = self.test or findtests(testdir)
        test_prefix = testdir + '.'
        if self.prefix:
            defaultTestLoader.testMethodPrefix = self.prefix
        for test in tests:
            abstest = test_prefix + test
            the_package = __import__(abstest, globals(), locals(), [])
            the_module = getattr(the_package, test)
            suite = defaultTestLoader.loadTestsFromModule(the_module)
            if self.pdb and (len(tests) > 1 or suite.countTestCases() > 1):
                print('Only one test at a time can be debugged, use the'
                      ' \'--test=\' and \'--prefix=\' options to set'
                      ' this test.')
                return
            if test == 'test_gdb':
                subprocess.check_call(['make', '-C', 'testsuite'])
            # run the test
            print(abstest)
            sys.stdout.flush()
            test_support.run_suite(suite, self.detail, self.stop, self.pdb)

_bdb = core.Extension('_bdb',
                sources=['pdb_clone/_bdbmodule.c'],
                optional=True)

core.setup(
    cmdclass={'sdist': sdist,
              'build_scripts': build_scripts,
              'install': install,
              'test': Test},
    requires=['subprocess'],
    scripts=SCRIPTS,
    ext_modules = [_bdb],
    packages=['pdb_clone', 'clewn'],
    data_files=DATA_FILES,

    # meta-data
    name='pyclewn',
    version=__tag__,
    description='Pyclewn allows using Vim as a front end to a debugger.',
    long_description=LONG_DESCRIPTION,
    platforms='all',
    license='GNU GENERAL PUBLIC LICENSE Version 2',
    author='Xavier de Gaye',
    author_email='xdegaye at users dot sourceforge dot net',
    url='http://pyclewn.sourceforge.net/',
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 3'
    ],
)

