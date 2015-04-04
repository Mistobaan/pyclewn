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

__version__ = '2.2'

# Python 2.6 or older
PY26 = (sys.version_info < (2, 7))

# Python 3.0 or newer
PY3 = (sys.version_info >= (3,))

# Python 3.2 or newer
PY32 = (sys.version_info >= (3, 2))

# Python 3.3 or newer
PY33 = (sys.version_info >= (3, 3))

# Python 3.4 or newer
PY34 = (sys.version_info >= (3, 4))

text_type = str if PY3 else unicode

class ClewnError(Exception):
    """Base class for pyclewn exceptions."""

# Pyclewn uses OrderedDict (added in Python 3.1).
# Trollius fails on Python 3.1 and pip does not support it.
if PY26 or (PY3 and not PY32):
    raise NotImplementedError('Python 2.7 or Python 3.2 or newer is required.')

def get_vimball():
    """Create the vimball in the current directory."""
    from pkgutil import get_data
    vmb = 'pyclewn-%s.vmb' % __version__
    vimball = get_data(__name__, os.path.join('runtime', vmb))
    with open(vmb, 'wb') as f:
        f.write(vimball)
    print('Creation of', os.path.abspath(vmb))

