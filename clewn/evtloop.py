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
if os.name == 'nt':
    from .nt import PipePeek
else:
    from .posix import PipePeek

from . import (misc, asyncproc)

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('loop')
Unused = critical
Unused = error
Unused = warning
Unused = info
Unused = debug

use_select_emulation = ('CLEWN_PIPES' in os.environ or os.name == 'nt')

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

def clewn_select(iwtd, owtd, ewtd, timeout, socket_map, select_thread):
    """Windows select emulation on pipes and sockets.

    The select_peeker thread, once created, is never destroyed.

    """
    select_peeker = None
    pipe_objects = []

    # pipes send only read events
    strip_asyncobj(owtd, asyncproc.FileWrapper, socket_map)
    strip_asyncobj(ewtd, asyncproc.FileWrapper, socket_map)

    # start the peek threads
    for fd in iwtd:
        asyncobj = get_asyncobj(fd, asyncproc.FileWrapper, socket_map)
        if asyncobj is not None:
            assert hasattr(asyncobj, 'reader') and asyncobj.reader
            if not hasattr(asyncobj, 'peeker'):
                asyncobj.peeker = PipePeek(asyncobj.socket.fileno(), asyncobj)
                asyncobj.peeker.start()
            pipe_objects.append(asyncobj)
            iwtd.remove(fd)
            asyncobj.peeker.start_thread()
    if iwtd or owtd or ewtd:
        select_peeker = select_thread

        if not select_peeker.isAlive():
            select_peeker.start()

        select_peeker.set_waitable(iwtd, owtd, ewtd)
        select_peeker.start_thread()

    # wait for events
    if select_peeker is None and not pipe_objects:
        time.sleep(timeout)
    else:
        asyncproc.Peek.select_event.wait(timeout)

    # stop the select threads
    iwtd = []
    owtd = []
    ewtd = []
    if select_peeker is not None:
        iwtd, owtd, ewtd = select_peeker.stop_thread()
    for asyncobj in pipe_objects:
        asyncobj.peeker.stop_thread()
        if asyncobj.peeker.read_event:
            iwtd.append(asyncobj.socket.fileno())
    asyncproc.Peek.select_event.clear()

    return iwtd, owtd, ewtd

class Poll:
    """A Poll instance manage a select thread."""

    def __init__(self, socket_map):
        """Constructor."""
        self.socket_map = socket_map
        if use_select_emulation:
            self.select_thread = None

    def close(self):
        """Terminate the select thread."""
        if use_select_emulation and not self.socket_map:
            if self.select_thread and self.select_thread.isAlive():
                self.select_thread.start_thread()

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
                    if use_select_emulation:
                        # when running the testsuite, replace
                        # the previous dead thread
                        if (not self.select_thread or not
                                    self.select_thread.isAlive()):
                            self.select_thread = asyncproc.SelectPeek(
                                                            self.socket_map)
                        r, w, e = clewn_select(r, w, e, timeout,
                                        self.socket_map, self.select_thread)
                    else:
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

