# vi:set ts=8 sts=4 sw=4 et tw=80:
#
# Copyright (C) 2007 Xavier de Gaye.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program (see the file COPYING); if not, write to the
# Free Software Foundation, Inc.,
# 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA
#
# $Id$

"""The clewn package.

"""
import os
import os.path
import tempfile
import sys as _sys
import inspect as _inspect
try:
    import subprocess
except ImportError, e:
    print "%s: upgrade python to version 2.4 or above." % e
    _sys.exit(1)

import application as _application

__version__ = '0.3'
__svn__ = '.' + '$Revision$'.strip('$').split()[1]
unused = __svn__
VIM_PGM = ['gvim',  '-u', 'NONE', '-esX', '-c', 'set cpo&vim']

def run_vim_cmd(cmd_list):
    """Run a list of vim commands and return its output."""
    assert isinstance(cmd_list, (list, tuple))
    tmpname = f = content = None
    try:
        try:
            fd, tmpname = tempfile.mkstemp(prefix='runvimcmd', suffix='.clewn')
            cmd_list[0:0] = ['redir! >' + tmpname]
            cmd_list.extend(['quit'])
            args = VIM_PGM[:]
            for cmd in cmd_list:
                args.extend(['-c', cmd])
            subprocess.Popen(args).wait()
            f = os.fdopen(fd)
            content = f.read()
        except (OSError, IOError):
            pass
    finally:
        if f:
            f.close()
        if os.path.exists(tmpname):
            os.unlink(tmpname)
    return content

def class_list():
    """Return the list of Application subclasses in the clewn package."""
    classes = []
    for name in _sys.modules:
        if name.startswith('clewn.'):
            module = _sys.modules[name]
            if module:
                classes.extend([obj for obj in module.__dict__.values()
                        if _inspect.isclass(obj)
                            and issubclass(obj, _application.Application)
                            and obj is not _application.Application])
    return classes

def python_version():
    """Python 2.4 or above is required by pyclewn."""
    # the subprocess module is required (new in python 2.4)
    return _sys.version_info >= (2, 4)

if not python_version():
    print python_version.__doc__
    _sys.exit()

