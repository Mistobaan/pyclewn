# vi:set ts=8 sts=4 sw=4 et tw=80:
"""
Low level module providing async_chat process communication and the use of pipes
for communicating with the forked process.
"""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import os.path
import time
import threading
import socket
import select
import errno
import asynchat
import subprocess
import fcntl
from abc import ABCMeta, abstractmethod

from . import misc

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('proc')

class FileWrapper(object):
    """Emulate a socket with a file descriptor or file object.

    Here we override just enough to make a file look like a socket for the
    purposes of asyncore.

    Instance attributes:
        fd: int
            file descriptor
        fobj: file
            file object instance

    """

    def __init__(self, f):
        self.fobj = None
        if isinstance(f, int):
            self.fd = f
        else:
            self.fobj = f
            self.fd = f.fileno()
        self.connected = True

    def recv(self, *args):
        """Receive data from the file."""
        return os.read(self.fd, *args)

    def send(self, *args):
        """Send data to the file."""
        return os.write(self.fd, *args)

    read = recv
    write = send

    def close(self):
        """Close the file."""
        if self.connected:
            self.connected = False
            if self.fobj is not None:
                self.fobj.close()
            else:
                os.close(self.fd)

    def fileno(self):
        """Return the file descriptor."""
        return self.fd

class FileAsynchat(asynchat.async_chat, object):
    """Instances of FileAsynchat are added to the asyncore socket_map.

    A FileAsynchat instance is a ProcessChannel helper, and a wrapper
    for a pipe or a pty.  When it is a pipe, it may be readable or writable.
    When it is a pseudo tty it is both.

    Instance attributes:
        f: int or file
            file descriptor or file object
        channel: ProcessChannel
            the cooperating ProcessChannel instance
        reader: True, False or None
            None: readable and writable (pty)
            True: readable
            False: writable
        ibuff: list
            list of strings read from the pipe or pty

    """

    def __init__(self, f, channel, reader=None, map=None):
        asynchat.async_chat.__init__(self, map=map)
        self.channel = channel
        self.reader = reader
        self.connected = True
        self.ibuff = []
        self.set_terminator(b'\n')

        if isinstance(f, int):
            self._fileno = f
        else:
            self._fileno = f.fileno()
        self.set_file(f)

        # set it to non-blocking mode
        flags = fcntl.fcntl(self._fileno, fcntl.F_GETFL, 0)
        flags = flags | os.O_NONBLOCK
        fcntl.fcntl(self._fileno, fcntl.F_SETFL, flags)

    def set_file(self, f):
        """Set the file descriptor."""
        self.socket = FileWrapper(f)
        self.add_channel()

    def recv(self, buffer_size):
        """Receive data from the file."""
        try:
            return asynchat.async_chat.recv(self, buffer_size)
        except OSError:
            self.close()
            return ''

    def send(self, data):
        """Send data to the file."""
        try:
            return asynchat.async_chat.send(self, data)
        except OSError:
            self.close()
            return 0

    def handle_error(self):
        """Process an error."""
        raise

    def handle_expt(self):
        """Process a select exception."""
        assert False, 'unhandled exception'

    def handle_connect(self):
        """Process a connect event."""
        assert False, 'unhandled connect event'

    def handle_accept(self):
        """Process an accept event."""
        assert False, 'unhandled accept event'

    def handle_close(self):
        """Process a close event."""
        self.close()

    def readable(self):
        """Is the file readable."""
        if self.reader is False:
            return False
        return asynchat.async_chat.readable(self)

    def writable(self):
        """Is the file writable."""
        if self.reader is True:
            return False
        return asynchat.async_chat.writable(self)

    def collect_incoming_data(self, data):
        """Called with data holding an arbitrary amount of received data."""
        self.ibuff.append(data.decode())

    def found_terminator(self):
        """Have the ProcessChannel instance process the received data."""
        msg = "".join(self.ibuff)
        self.ibuff = []
        self.channel.handle_line(msg)

    def push(self, data):
        """Push the data to be sent."""
        asynchat.async_chat.push(self, data.encode())

class ProcessChannel(object):
    """An abstract class to run a command with a process through async_chat.

    To implement a concrete subclass of ProcessChannel, one must implement
    the handle_line method that process the lines (new line terminated)
    received from the program stdout and stderr.

    Instance attributes:
        socket_map: dict
            the asyncore socket dictionary
        argv: tuple or list
            argv arguments
        pgm_name: str
            process name
        fileasync: tuple
            the readable and writable instances of FileAsynchat helpers
        pid: int
            spawned process pid
        ttyname: str
            pseudo tty name

    """

    __metaclass__ = ABCMeta

    def __init__(self, socket_map, argv):
        assert argv
        self.socket_map = socket_map
        self.argv = argv
        self.pgm_name = os.path.basename(self.argv[0])
        self.fileasync = None
        self.pid = 0
        self.ttyname = None

    def popen(self):
        """Spawn a process using pipes."""
        proc = subprocess.Popen(self.argv,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            close_fds=True)
        self.fileasync = (FileAsynchat(
                                proc.stdout, self, True, self.socket_map),
                          FileAsynchat(
                                proc.stdin, self, False, self.socket_map))
        self.pid = proc.pid
        info('starting "%s" with two pipes', self.pgm_name)

    def start(self):
        """Spawn the process and connect its stdio to our fileasync tuple."""
        try:
            self.popen()
        except OSError:
            critical('cannot start process "%s"', self.pgm_name); raise
        info('program argv list: %s', str(self.argv))

    def close(self):
        """Close the channel an wait on the process."""
        if self.fileasync is not None:
            # it is safe to close the same FileAsynchat twice
            self.fileasync[0].close()
            self.fileasync[1].close()
            self.fileasync = None

    def sendintr(self):
        """Cannot send an interrupt to the program."""
        pass

    @abstractmethod
    def handle_line(self, line):
        """Process the line received from the program stdout and stderr."""
        pass

    def write(self, data):
        """Write a chunk of data to the process stdin."""
        if self.fileasync is not None:
            if not data.endswith('\n'):
                data += '\n'
            self.fileasync[1].push(data)

