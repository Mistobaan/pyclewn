#!/usr/bin/env python
# $Id$

import sys
import os
import string
import re
from os.path import join
from distutils.command.install import install as _install
from distutils.command.sdist import sdist as _sdist
from distutils.command.build_scripts import build_scripts as _build_scripts
from distutils.core import setup
import pyclewn_install
from pyclewn_install import vimdir
from pyclewn_install import vim_features
from pyclewn_install import build_vimhelp

import clewn
# list of debuggers to include in the distribution
import clewn.gdb, clewn.debugger.simple

DESCRIPTION = """Pyclewn allows using Vim as a front end to a debugger.
The debugger output is redirected to a Vim window, the pyclewn console.
The debugger commands are mapped to Vim user-defined commands
with a common letter prefix, and with completion available on the
commands and their first argument. The controlling terminal of the
program to debug is the terminal used to launch pyclewn, or any other
terminal when the debugger allows it.
"""

WINDOWS_INSTALL = """BEFORE INSTALLING:
Please make sure that Gvim is in the PATH, otherwise the installation
will fail. Use the Control Panel on Windows XP to add the gvim directory
to %PATH%:
Control Panel > System > Advanced tab > Envt Variables > Edit "PATH"
"""

if os.name == 'nt':
    SCRIPTS = ['pyclewn', 'pyclewn_install.py']
    VIMDIR = ['pyclewn']
    LONG_DESCRIPTION = WINDOWS_INSTALL
else:
    SCRIPTS = ['pyclewn']
    VIMDIR = []
    LONG_DESCRIPTION = DESCRIPTION

def keys_filename(clazz):
    """Return the pyclewn_keys pathname for a given application class."""
    ext = clazz.__name__.lower()
    return 'runtime/.pyclewn_keys.' + ext

PYCLEWN_CLASSES = clewn.class_list()
DATA_FILES = [
    (vimdir(VIMDIR),
        ['runtime/pyclewn.vim']),
    (join(vimdir(VIMDIR), 'doc'),
        ['runtime/doc/pyclewn.txt']),
    (join(vimdir(VIMDIR), 'macros'),
        [keys_filename(clazz) for clazz in PYCLEWN_CLASSES]),
    (join(vimdir(VIMDIR), 'syntax'),
        ['runtime/syntax/dbgvar.vim'])]
if os.name == 'nt':
    DATA_FILES.append(pyclewn_install.icon(VIMDIR[0]))

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

        vim_features()
        _install.run(self)
        build_vimhelp()

def update_version(filename):
    """Update the version number in the content of filename."""
    content = []
    f = open(filename, 'r+')
    for line in f:
        line = re_version.sub(r'\g<name>' + clewn.__version__, line)
        content.append(line)
    f.seek(0)
    f.writelines(content)
    f.close()

def keymap_files():
    """Build key map files for each imported Application subclass."""
    template = open('runtime/.pyclewn_keys.template').read()
    for clazz in PYCLEWN_CLASSES:
        f = open(keys_filename(clazz), 'w')
        ext = clazz.__name__.lower()
        f.write(string.Template(template).substitute(clazz=ext))
        mapkeys = getattr(clazz, ext + '_mapkeys')
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
        update_version('runtime/pyclewn.vim')
        update_version('INSTALL')
        keymap_files()
        _sdist.run(self)

setup(
    cmdclass={'sdist': sdist, 'build_scripts': build_scripts, 'install': install},
    requires=['subprocess'],
    scripts=SCRIPTS,
    packages=['clewn', 'clewn.debugger'],
    data_files=DATA_FILES,

    # meta-data
    name='pyclewn',
    version=clewn.__version__,
    description='Pyclewn allows using Vim as a front end to a debugger.',
    long_description=LONG_DESCRIPTION,
    platforms='all',
    license='GNU GENERAL PUBLIC LICENSE Version 2',
    author='Xavier de Gaye',
    author_email='xdegaye at users dot sourceforge dot net',
    url='http://pyclewn.sourceforge.net/',
)

