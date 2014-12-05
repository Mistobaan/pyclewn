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

"""Pyclewn event loop."""

import os
import time
import select
import errno
import asyncore
import threading

from . import (misc, asyncproc)

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('loop')
Unused = critical
Unused = error
Unused = warning
Unused = info
Unused = debug

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

class Poll:
    """A Poll instance manages a select thread.

    Instance attributes:
        socket_map: dict
            the asyncore map

    """

    def __init__(self, socket_map):
        """Constructor."""
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

