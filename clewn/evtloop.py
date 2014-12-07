# vi:set ts=8 sts=4 sw=4 et tw=80:
"""
Pyclewn event loop.
"""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import time
import select
import errno
import asyncore
import threading

from . import misc

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('loop')

def get_asyncobj(fd, file_type, socket_map):
    """Return an asyncore instance from 'socket_map' if matching 'file_type'."""
    asyncobj = socket_map.get(fd)
    if asyncobj and isinstance(asyncobj.socket, file_type):
        return asyncobj
    return None

def strip_asyncobj(wtd, file_type, socket_map):
    """Remove all 'file_type' file descriptors in 'wtd'."""
    tmp_list = wtd[:]
    for fd in tmp_list:
        asyncobj = get_asyncobj(fd, file_type, socket_map)
        if asyncobj is not None:
            wtd.remove(fd)

class Poll(object):
    """A Poll instance manages a select thread.

    Instance attributes:
        socket_map: dict
            the asyncore map

    """

    def __init__(self, socket_map):
        self.socket_map = socket_map

    def close(self):
        """Terminate the select thread."""
        # This is a noop: Windows support has been removed => no select thread.

    def run(self, timeout=0.0):
        """Run the asyncore poll function."""
        if self.socket_map:
            r = []; w = []; e = []
            for fd, obj in self.socket_map.items():
                is_r = obj.readable()
                is_w = obj.writable()
                if is_r:
                    r.append(fd)
                if is_w:
                    w.append(fd)
                if is_r or is_w:
                    e.append(fd)
            if [] == r == w == e:
                time.sleep(timeout)
            else:
                try:
                    r, w, e = select.select(r, w, e, timeout)
                except select.error as err:
                    if err.args[0] != errno.EINTR:
                        raise
                    else:
                        return

            for fd in r:
                obj = self.socket_map.get(fd)
                if obj is None:
                    continue
                asyncore.read(obj)

            for fd in w:
                obj = self.socket_map.get(fd)
                if obj is None:
                    continue
                asyncore.write(obj)

            for fd in e:
                obj = self.socket_map.get(fd)
                if obj is None:
                    continue
                asyncore._exception(obj)

