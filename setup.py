#!/usr/bin/env python
# $Id$

import sys
import os
import os.path
import string
import re
from distutils.command.install import install as _install
from distutils.command.sdist import sdist as _sdist
from distutils.command.build_scripts import build_scripts as _build_scripts
from distutils.core import setup
try:
    import subprocess
except ImportError, e:
    import sys
    print "%s: upgrade python to version 2.4 or above." % e
    sys.exit(1)


import clewn
# list of debuggers to include in the distribution
import clewn.gdb, clewn.debugger.simple

RE_VERSION = r'(?P<name>pyclewn-)(?P<num>\d+\.\d+)'     \
             r'# RE: pyclewn-d.d'

# compile regexps
re_version = re.compile(RE_VERSION, re.VERBOSE)

# installation path of pyclewn lib
pythonpath = None

def abort(msg):
    print msg
    sys.exit()

def vim_features():
    """Abort if missing required Vim feature."""
    args = ['gvim',  '-u', 'NONE', '--version']
    try:
        output = subprocess.Popen(args, stdout=subprocess.PIPE).communicate()[0]
    except OSError:
        abort('aborting install: cannot start gvim')

    print 'checking netbeans support in gvim:',
    try:
        output.index('+netbeans_intg')
    except ValueError:
        abort('no\n' 'aborting install: netbeans support in gvim is required')
    print 'yes'

    print 'checking auto commands support in gvim:',
    try:
        output.index('+autocmd')
    except ValueError:
        abort('no\n' 'aborting install: auto commands support in gvim is required')
    print 'yes'

def vimdir(dir=[]):
    """Return the vim runtime files directory."""
    # do it only once
    if not dir:
        if os.environ.has_key('vimdir'):
            dir.append(os.environ['vimdir'])
        else:
            content = clewn.run_vim_cmd(['echon $VIM'])
            if content:
                dir.append(os.path.join(content, 'vimfiles'))
            else:
                abort('aborting install: cannot get runtime files directory')
    return dir[0]

class install(_install):
    """Specialized installer, check required Vim features support and
    rebuild help tags.

    """
    def run(self):
        global pythonpath
        pythonpath = self.install_purelib

        vim_features()
        _install.run(self)
        helpdir = os.path.join(vimdir(), 'doc')
        print 'pyclewn help tags file generation in %s' % helpdir
        clewn.run_vim_cmd(['helptags ' + helpdir])

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
    classes = clewn.class_list()
    for clazz in classes:
        name = clazz.__name__.lower()
        f = open('runtime/.pyclewn_keys.' + name, 'w')
        f.write(string.Template(template).substitute(clazz=name))
        mapkeys = getattr(clazz, name + '_mapkeys')
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
    scripts=['pyclewn'],
    packages=['clewn', 'clewn.debugger'],

    # runtime files
    data_files=[(vimdir(), ['runtime/pyclewn.vim']),
        (os.path.join(vimdir(), 'doc'), ['runtime/doc/pyclewn.txt']),
        (os.path.join(vimdir(), 'syntax'), ['runtime/syntax/dbgvar.vim'])],

    # meta-data
    name='pyclewn',
    version=clewn.__version__,
    description='Pyclewn controls a debugger application'\
                            ' with gvim, through netbeans.',
    long_description=clewn.__doc__,
    platforms='all',
    license='GNU GENERAL PUBLIC LICENSE Version 2',
    author='Xavier de Gaye',
    author_email='xdegaye at users dot sourceforge dot net',
    url='http://pyclewn.sourceforge.net/',
)

