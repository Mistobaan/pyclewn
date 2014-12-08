# vi:set ts=8 sts=4 sw=4 et tw=80:
# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from io import open

import sys
import os
import string
import re
import subprocess
import importlib
import distutils.core as core

from os.path import join as pathjoin
from distutils.command.install import install as _install
from distutils.command.sdist import sdist as _sdist
from distutils.command.build_scripts import build_scripts as _build_scripts
from unittest import defaultTestLoader

from clewn import __version__, vim
import testsuite.test_support as test_support

DESCRIPTION = 'A Vim front-end to debuggers.'
LONG_DESCRIPTION = """Pyclewn allows using Vim as a front-end to a debugger.
The debugger output is redirected to a Vim window, the pyclewn console.
The debugger commands are mapped to Vim user-defined commands
with a common letter prefix, and with completion available on the
commands and their first argument. The controlling terminal of the
program to debug is the terminal used to launch pyclewn, or any other
terminal when the debugger allows it.
"""
DEBUGGERS = ('simple', 'gdb', 'pdb')
SCRIPTS = ['pyclewn', 'runtime/bin/inferior_tty.py']

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
        print('Vim user data files location: "%s"' % vimdir)
        vim_features()
        _install.run(self)
        build_vimhelp()

def keymap_files():
    """Build key map files for each debugger."""
    with open('runtime/.pyclewn_keys.template') as tf:
        template = tf.read()
        for d in DEBUGGERS:
            with open('runtime/.pyclewn_keys.%s' % d, 'w') as f:
                f.write(string.Template(template).substitute(clazz=d))
                module = importlib.import_module('.%s' % d, 'clewn')
                mapkeys = getattr(module, 'MAPKEYS')
                for k in sorted(mapkeys):
                    if len(mapkeys[k]) == 2:
                        comment = ' # ' + mapkeys[k][1]
                        f.write('# %s%s\n' % (('%s : %s' %
                                (k, mapkeys[k][0])).ljust(30), comment))
                    else:
                        f.write('# %s : %s\n' % (k, mapkeys[k][0]))

def insert_syspath(fname, after_future=True):
    sys_path = string.Template("sys.path.append('${pythonpath}')\n")
    sys_path = 'import sys; ' + sys_path.substitute(pythonpath=pythonpath)
    content = []
    past_future = False
    done = False
    with open(fname, 'r+') as f:
        for line in f:
            if line.find('from __future__ import') == 0:
                past_future = True
            elif not done and past_future:
                done = True
                content.append(sys_path)
            content.append(line)
            if not after_future and not done:
                done = True
                content.append(sys_path)
        if done:
            f.seek(0)
            f.writelines(content)
    return done

class build_scripts(_build_scripts):
    """Specialized scripts builder.

    """
    def run(self):
        """Add pythonpath to pyclewn script in a 'home scheme' installation."""
        _build_scripts.run(self)
        if pythonpath is not None and pythonpath not in sys.path:
            for script in self.scripts:
                fname = os.path.join(self.build_dir, os.path.basename(script))
                if not insert_syspath(fname):
                    insert_syspath(fname, after_future=False)

NOTTESTS = ('test_support',)

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
        keymap_files()
        _sdist.run(self)

class Test(core.Command):
    """Run the test suite.
    """

    user_options = [(str(x), str(y), str(z)) for (x, y, z) in
        (('test=', 't',
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
                     ' Pyclewn pdb\''),)
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

        testsuite = 'testsuite'
        tests = self.test or findtests(testsuite)
        if self.prefix:
            defaultTestLoader.testMethodPrefix = self.prefix
        for test in tests:
            the_module = importlib.import_module('.%s' % test, testsuite)
            suite = defaultTestLoader.loadTestsFromModule(the_module)
            if self.pdb and (len(tests) > 1 or suite.countTestCases() > 1):
                print('Only one test at a time can be debugged, use the'
                      ' \'--test=\' and \'--prefix=\' options to set'
                      ' this test.')
                return
            if test == 'test_gdb':
                subprocess.check_call(['make', '-C', testsuite])
            # run the test
            print(the_module.__name__)
            sys.stdout.flush()
            test_support.run_suite(suite, self.detail, self.stop, self.pdb)

core.setup(
    cmdclass={'sdist': sdist,
              'build_scripts': build_scripts,
              'install': install,
              'test': Test},
    scripts=SCRIPTS,
    packages=[str('clewn')],
    data_files=DATA_FILES,

    # meta-data
    name='pyclewn',
    version=__version__,
    description='Pyclewn allows using Vim as a front end to a debugger.',
    long_description=LONG_DESCRIPTION,
    platforms='all',
    license='GNU GENERAL PUBLIC LICENSE Version 2',
    author='Xavier de Gaye',
    author_email='xdegaye at users dot sourceforge dot net',
    url='http://pyclewn.sourceforge.net/',
    classifiers=[
        'Topic :: Software Development :: Debuggers',
        'Intended Audience :: Developers',
        'Operating System :: Unix',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Development Status :: 6 - Mature',
        'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
    ],
)

