# vi:set ts=8 sts=4 sw=4 et tw=80:
"""
The clewn package.
"""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import sys
import os
import tempfile
import subprocess
import errno

__all__ = [str(x) for x in
               ('__version__', 'PY3', 'PY26', 'text_type', 'ClewnError',)]

__version__ = '2.0'

# Python 2.6 or older
PY26 = (sys.version_info < (2, 7))

# Python 3.0 or newer
PY3 = (sys.version_info >= (3,))

# Python 3.1 or newer
PY31 = (sys.version_info >= (3, 1))

# Python 3.4 or newer
PY34 = (sys.version_info >= (3, 4))

text_type = str if PY3 else unicode

class ClewnError(Exception):
    """Base class for pyclewn exceptions."""

# pyclewn uses OrderedDict (added in Python 3.1).
if PY26 or (PY3 and not PY31):
    raise NotImplementedError('Python 2.7 or Python 3.1 or newer is required.')

def exec_vimcmd(commands, pathname='', error_stream=None):
    """Run a list of Vim 'commands' and return the commands output."""
    try:
        perror = error_stream.write
    except AttributeError:
        perror = sys.stderr.write

    if not pathname:
        pathname = os.environ.get('EDITOR', 'gvim')

    args = [pathname, '-u', 'NONE', '-esX', '-c', 'set cpo&vim']
    fd, tmpname = tempfile.mkstemp(prefix='runvimcmd', suffix='.clewn')
    commands.insert(0,  'redir! >%s' % tmpname)
    commands.append('quit')
    for cmd in commands:
        args.extend(['-c', cmd])

    output = f = None
    try:
        try:
            subprocess.Popen(args).wait()
            f = os.fdopen(fd)
            output = f.read()
        except (OSError, IOError) as err:
            if isinstance(err, OSError) and err.errno == errno.ENOENT:
                perror("Failed to run '%s' as Vim.\n" % args[0])
                perror("Please set the EDITOR environment variable or run "
                                "'pyclewn --editor=/path/to/(g)vim'.\n\n")
            else:
                perror("Failed to run Vim as:\n'%s'\n\n" % str(args))
                perror("Error; %s\n", err)
            raise
    finally:
        if f is not None:
            f.close()
        try:
            os.unlink(tmpname)
        except OSError:
            pass

    if not output:
        raise ClewnError(
            "Error trying to start Vim with the following command:\n'%s'\n"
            % ' '.join(args))

    return output

