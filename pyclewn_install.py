#!/usr/bin/env python
# $Id$
"""Windows install scripts.
"""

import sys
import os
import os.path
from os.path import join
from distutils import sysconfig
from distutils.dir_util import copy_tree
from distutils.dir_util import remove_tree
from distutils.file_util import copy_file

import clewn

ICON_NAME = 'clewn.ico'
PYCLEWN_SHORTCUT = 'Pyclewn.lnk'

class Error(Exception):
    """Pyclewn install exceptions."""
    pass

try:
    import subprocess
except ImportError, e:
    raise Error, ("%s: upgrade python to version 2.4 or above." % e)

def icon(vimdir):
    """Return icon file tuple to be used as data file in distutils setup."""
    return (vimdir, [join('images', ICON_NAME)])

def vim_features():
    """Abort if missing required Vim feature."""
    output = clewn.run_vim_cmd(['version'])

    print >> sys.stderr, 'checking netbeans support in gvim:',
    try:
        output.index('+netbeans_intg')
    except ValueError:
        raise Error, 'netbeans support in gvim is required'
    print >> sys.stderr, 'yes'

    print >> sys.stderr, 'checking auto commands support in gvim:',
    try:
        output.index('+autocmd')
    except ValueError:
        raise Error, 'auto commands support in gvim is required'
    print >> sys.stderr, 'yes'

def vimdir(dir=[]):
    """Return the vim runtime files directory."""
    # do it only once
    if not dir:
        if os.environ.has_key('vimdir'):
            dir.append(os.environ['vimdir'])
        else:
            path = clewn.run_vim_cmd(['echon $VIM'])
            dir.append(join(path, 'vimfiles'))
    return dir[0]

def build_vimhelp():
    """Add pyclewn help to Vim help."""
    helpdir = join(vimdir(), 'doc')
    print >> sys.stderr, 'running Vim help tags file generation in %s' % helpdir
    clewn.run_vim_cmd(['helptags ' + helpdir, 'echo v:version'])

def unlink(file):
    """Delete a file."""
    try:
        os.unlink(file)
    except OSError:
        pass

def install():
    """Write the bat file and copy the runtime files."""
    prefix = sysconfig.get_config_var('prefix')
    scripts = join(prefix, 'scripts')
    vim_features()

    # install runtime files
    runtime_dir = join(prefix, 'pyclewn')
    icon_file = join(runtime_dir, ICON_NAME)
    copy_file(icon_file, scripts)
    print >> sys.stderr, 'copying file %s' % icon_file
    unlink(icon_file)

    for file in copy_tree(runtime_dir, vimdir()):
        print >> sys.stderr, 'copying file %s' % file
    print >> sys.stderr, 'removing directory %s' % runtime_dir
    remove_tree(runtime_dir)

    build_vimhelp()

    # create pyclewn.bat
    pyexe = join(prefix, 'python.exe')
    scriptpy = join(scripts, 'pyclewn')
    f = open(join(scripts, 'pyclewn.bat'), 'w')
    f.write("@%s %s %%*\n" % (pyexe, scriptpy))
    f.close()

    # create Windows shortcut
    create_shortcut(
        join(scripts, 'pyclewn.bat'),
        'Pyclewn allows using Vim as a front end to a debugger.',
        PYCLEWN_SHORTCUT,
        r'--pgm=C:\mingw\bin\gdb.exe --daemon',
        '',
        join(scripts, ICON_NAME),
        0)

    # copy shortcut to Desktop when it does not exist
    desktop_path = get_special_folder_path('CSIDL_DESKTOPDIRECTORY')
    pyclewn_shortcut = join(desktop_path, PYCLEWN_SHORTCUT)
    if not os.path.exists(pyclewn_shortcut):
        copy_file(PYCLEWN_SHORTCUT, desktop_path)
        print >> sys.stderr, 'copying pyclewn to the desktop: %s' % pyclewn_shortcut

    # cleanup
    unlink(PYCLEWN_SHORTCUT)
    unlink(join(scripts, 'pyclewn_install.py'))
    unlink(join(scripts, 'pyclewn_install.pyc'))
    unlink(join(scripts, 'pyclewn_install.pyo'))

    print >> sys.stderr, 'pyclewn postinstall completed'

def uninstall():
    prefix = sysconfig.get_config_var('prefix')
    scripts = join(prefix, 'scripts')

    # remove scripts, icon and shortcut
    unlink(join(scripts, 'pyclewn'))
    unlink(join(scripts, 'pyclewn.bat'))
    unlink(join(scripts, ICON_NAME))
    unlink(join(scripts, 'pyclewn_install.py'))
    desktop_path = get_special_folder_path('CSIDL_DESKTOPDIRECTORY')
    unlink(join(desktop_path, PYCLEWN_SHORTCUT))

    # remove vim files and rebuild vim help
    unlink(join(join(vimdir(), 'doc'), 'pyclewn.txt'))
    unlink(join(join(vimdir(), 'syntax'), 'dbgvar.vim'))
    unlink(join(vimdir(), 'pyclewn.vim'))
    build_vimhelp()

if __name__ == '__main__':
    if os.name == 'nt':
        try:
            if sys.argv[1] == '-install':
                install()
            elif sys.argv[1] == '-remove':
                uninstall()
        except Exception, err:
            # let the python installer print the error
            print >> sys.stderr, err
