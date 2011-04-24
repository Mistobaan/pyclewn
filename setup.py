#!/usr/bin/env python

import sys
import os
import os.path
import string
import re
import __builtin__
import distutils.core as core

from os.path import join as pathjoin
from distutils.command.install import install as _install
from distutils.command.sdist import sdist as _sdist
from distutils.command.build_scripts import build_scripts as _build_scripts

import testsuite.regrtest as regrtest
import pyclewn_install
from clewn import *

DESCRIPTION = """Pyclewn allows using Vim as a front end to a debugger.
The debugger output is redirected to a Vim window, the pyclewn console.
The debugger commands are mapped to Vim user-defined commands
with a common letter prefix, and with completion available on the
commands and their first argument. The controlling terminal of the
program to debug is the terminal used to launch pyclewn, or any other
terminal when the debugger allows it.
"""

WINDOWS_INSTALL = """BEFORE INSTALLING:
Please make sure that Vim is in the PATH, otherwise the installation
will fail (see installation notes at
http://pyclewn.sourceforge.net/install.html).
"""

if os.name == 'nt':
    SCRIPTS = ['pyclewn', 'pyclewn_install.py']
    vimdir = 'pyclewn'
    LONG_DESCRIPTION = WINDOWS_INSTALL
else:
    SCRIPTS = ['pyclewn', 'runtime/bin/inferior_tty.py']
    vimdir = pyclewn_install.vimdir()
    LONG_DESCRIPTION = DESCRIPTION

DEBUGGERS = ('simple', 'gdb', 'pdb')
DATA_FILES = [
    (pathjoin(vimdir, 'plugin'), ['runtime/plugin/pyclewn.vim']),
    (pathjoin(vimdir, 'autoload'), ['runtime/autoload/pyclewn.vim']),
    (pathjoin(vimdir, 'doc'), ['runtime/doc/pyclewn.txt']),
    (pathjoin(vimdir, 'macros'),
        [('runtime/.pyclewn_keys.%s' % d) for d in DEBUGGERS]),
    (pathjoin(vimdir, 'syntax'), ['runtime/syntax/dbgvar.vim']),
    ]
if os.name == 'nt':
    DATA_FILES.append(pyclewn_install.icon(vimdir))

RE_VERSION = r'(?P<name>pyclewn-)(?P<num>\d+\.\d+)'     \
             r'# RE: pyclewn-d.d'

# compile regexps
re_version = re.compile(RE_VERSION, re.VERBOSE)

# installation path of pyclewn lib
pythonpath = None

class install(_install):
    """Specialized installer, check required Vim features support and
    rebuild help tags.

    """
    def run(self):
        global pythonpath
        pythonpath = self.install_purelib
        # rename the 'debugger' directory present in old versions
        debugger_dir = os.path.join(pythonpath, 'clewn', 'debugger')
        if os.path.isdir(debugger_dir):
            print >> sys.stderr, 'renaming the debugger directory'
            os.rename(debugger_dir, debugger_dir + '.orig')

        # substitute templates in the autoload plugin
        # this is done in the post-install script in Windows
        if os.name != 'nt':
            mapping = {'pgm': '"pyclewn"', 'start': ''}
            pyclewn_install.substitute_autoload('runtime', mapping)

        pyclewn_install.vim_features()
        _install.run(self)
        pyclewn_install.build_vimhelp()

def update_version(filename):
    """Update the version number in the content of filename."""
    content = []
    f = open(filename, 'r+')
    for line in f:
        line = re_version.sub(r'\g<name>' + __tag__, line)
        content.append(line)
    f.seek(0)
    f.writelines(content)
    f.close()

def keymap_files():
    """Build key map files for each debugger."""
    template = open('runtime/.pyclewn_keys.template').read()
    for d in DEBUGGERS:
        f = open('runtime/.pyclewn_keys.%s' % d, 'w')
        f.write(string.Template(template).substitute(clazz=d))
        # cannot use absolute imports with python 2.4, so we are stuck with pydb.py
        if d == 'pdb':
            d = 'pydb'
        module = __import__('clewn.%s' % d,  globals(), locals(), ['MAPKEYS'])
        mapkeys = getattr(module, 'MAPKEYS')
        for k in sorted(mapkeys):
            if len(mapkeys[k]) == 2:
                comment = ' # ' + mapkeys[k][1]
                f.write('# %s%s\n' %
                    (('%s : %s' % (k, mapkeys[k][0])).ljust(30), comment))
            else:
                f.write('# %s : %s\n' % (k, mapkeys[k][0]))

        f.close()

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

class sdist(_sdist):
    """Specialized sdister."""
    def run(self):
        update_version('runtime/plugin/pyclewn.vim')
        update_version('INSTALL')
        keymap_files()
        _sdist.run(self)

class Test(core.Command):
    """Run the test suite.
    """

    user_options = [
        ('test=', 't',
            'run a comma separated list of tests, for example             '
            '"--test=simple,gdb", all the tests are run when this option'
            ' is not present'),
        ('detail', 'd',
            'detailed test output, each test case is printed'),
    ]

    def initialize_options(self):
        self.test = None
        self.detail = 0

    def finalize_options(self):
        if self.test is not None:
            self.test = ['test_' + t for t in self.test.split(',')]
        if self.detail:
            self.detail = 1

    def run (self):
        """Run the test suite."""
        regrtest.run('testsuite', self.test, self.detail)

core.setup(
    cmdclass={'sdist': sdist,
              'build_scripts': build_scripts,
              'install': install,
              'test': Test},
    requires=['subprocess'],
    scripts=SCRIPTS,
    packages=['clewn'],
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
)

