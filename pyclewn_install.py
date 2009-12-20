#!/usr/bin/env python
"""Windows install scripts.
"""

import sys
import os
import os.path
import distutils.sysconfig as sysconfig
import distutils.dir_util as dir_util
from os.path import join as pathjoin
from distutils.file_util import copy_file

import clewn.vim as vim

ICON_NAME = 'clewn.ico'
PYCLEWN_SHORTCUT = 'Pyclewn.lnk'

class ClewnInstallError(Exception):
    """Pyclewn install exceptions."""
    pass

def icon(vimdir):
    """Return icon file tuple to be used as data file in distutils setup."""
    return (vimdir, [pathjoin('images', ICON_NAME)])

def vim_features():
    """Abort if missing required Vim feature."""
    output = vim.exec_vimcmd(['version'])

    print >> sys.stderr, 'checking netbeans support in gvim:',
    try:
        output.index('+netbeans_intg')
    except ValueError:
        raise ClewnInstallError, 'netbeans support in gvim is required'
    print >> sys.stderr, 'yes'

    print >> sys.stderr, 'checking auto commands support in gvim:',
    try:
        output.index('+autocmd')
    except ValueError:
        raise ClewnInstallError, 'auto commands support in gvim is required'
    print >> sys.stderr, 'yes'

def vimdir(dir=[]):
    """Return the vim runtime files directory."""
    # do it only once
    if not dir:
        if os.environ.has_key('vimdir'):
            dir.append(os.environ['vimdir'])
        else:
            path = vim.exec_vimcmd(['echon $VIM'])
            dir.append(pathjoin(path, 'vimfiles'))
    return dir[0]

def build_vimhelp():
    """Add pyclewn help to Vim help."""
    helpdir = pathjoin(vimdir(), 'doc')
    print >> sys.stderr, 'running Vim help tags file generation in %s' % helpdir
    vim.exec_vimcmd(['helptags ' + helpdir, 'echo v:version'])

def unlink(filename):
    """Delete a file."""
    try:
        os.unlink(filename)
    except OSError:
        pass

def install():
    """Write the bat file and copy the runtime files."""
    prefix = sysconfig.get_config_var('prefix')
    scripts = pathjoin(prefix, 'scripts')
    vim_features()

    # install runtime files
    runtime_dir = pathjoin(prefix, 'pyclewn')
    icon_file = pathjoin(runtime_dir, ICON_NAME)
    copy_file(icon_file, scripts)
    print >> sys.stderr, 'copying file %s' % icon_file
    unlink(icon_file)

    for filename in dir_util.copy_tree(runtime_dir, vimdir()):
        print >> sys.stderr, 'copying file %s' % filename
    print >> sys.stderr, 'removing directory %s' % runtime_dir
    dir_util.remove_tree(runtime_dir)

    build_vimhelp()

    # create pyclewn.bat
    pyexe = pathjoin(prefix, 'python.exe')
    scriptpy = pathjoin(scripts, 'pyclewn')
    f = open(pathjoin(scripts, 'pyclewn.bat'), 'w')
    f.write("@%s %s %%*\n" % (pyexe, scriptpy))
    f.close()

    # create Windows shortcut
    create_shortcut(
        pathjoin(scripts, 'pyclewn.bat'),
        'Pyclewn allows using Vim as a front end to a debugger.',
        PYCLEWN_SHORTCUT,
        r'--pgm=C:\mingw\bin\gdb.exe --daemon',
        '',
        pathjoin(scripts, ICON_NAME),
        0)

    # copy shortcut to Desktop when it does not exist
    desktop_path = get_special_folder_path('CSIDL_DESKTOPDIRECTORY')
    pyclewn_shortcut = pathjoin(desktop_path, PYCLEWN_SHORTCUT)
    if not os.path.exists(pyclewn_shortcut):
        copy_file(PYCLEWN_SHORTCUT, desktop_path)
        print >> sys.stderr, 'copying pyclewn to the desktop: %s' % pyclewn_shortcut

    # cleanup
    unlink(PYCLEWN_SHORTCUT)
    unlink(pathjoin(scripts, 'pyclewn_install.py'))
    unlink(pathjoin(scripts, 'pyclewn_install.pyc'))
    unlink(pathjoin(scripts, 'pyclewn_install.pyo'))

    print >> sys.stderr, 'pyclewn postinstall completed'

def uninstall():
    """Uninstall on Windows."""
    prefix = sysconfig.get_config_var('prefix')
    scripts = pathjoin(prefix, 'scripts')

    # remove scripts, icon and shortcut
    unlink(pathjoin(scripts, 'pyclewn'))
    unlink(pathjoin(scripts, 'pyclewn.bat'))
    unlink(pathjoin(scripts, ICON_NAME))
    unlink(pathjoin(scripts, 'pyclewn_install.py'))
    desktop_path = get_special_folder_path('CSIDL_DESKTOPDIRECTORY')
    unlink(pathjoin(desktop_path, PYCLEWN_SHORTCUT))

    # remove vim files and rebuild vim help
    unlink(pathjoin(pathjoin(vimdir(), 'doc'), 'pyclewn.txt'))
    unlink(pathjoin(pathjoin(vimdir(), 'syntax'), 'dbgvar.vim'))
    unlink(pathjoin(vimdir(), 'pyclewn.vim'))
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
