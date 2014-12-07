# vi:set ts=8 sts=4 sw=4 et tw=80:
"""
Gdb inferior terminal.
"""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import sys
import array
import errno
import pty
import signal
import fcntl
import asyncore
from termios import tcgetattr, tcsetattr, TCSADRAIN, TIOCGWINSZ, TIOCSWINSZ
from termios import error as termios_error
from termios import INLCR, ICRNL, IXON, IXOFF, IXANY,   \
        OPOST,                                          \
        ECHO, ECHONL, ICANON, ISIG, IEXTEN,             \
        VMIN, VTIME

from . import misc

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('tty')

# the command character: 'C-a'
CMD_CHAR = chr(1)

def close(fd):
    """Close the file descriptor."""
    if fd != -1:
        try:
            os.close(fd)
        except OSError:
            pass

pty_instance = None

def sigwinch_handler(*args):
    """Handle SIGWINCH."""
    if pty_instance and pty_instance.master_dsptch:
        pty_instance.master_dsptch.update_size()

class FileDispatcher(asyncore.file_dispatcher, object):
    """The FileDispatcher does input/output on a file descriptor.

    Read data into 'buf'.
    Write the content of the FileDispatcher 'source' buffer 'buf'.
    When 'enable_cmds' is True, handle the command character 'C-a'.
    """

    def __init__(self, fd, source=None, reader=True,
                            enable_cmds=False, map=None):
        asyncore.file_dispatcher.__init__(self, fd, map)
        self.source = source
        self.reader = reader
        self.enable_cmds = enable_cmds
        self.cmd_char_last = False
        self.close_tty = False
        self.buf = ''

    def readable(self):
        """A readable dispatcher."""
        return self.reader

    def writable(self):
        """A writable dispatcher."""
        return self.source and self.source.buf != ''

    def handle_read(self):
        """Process data available for reading."""
        try:
            data = self.socket.recv(1024).decode()
        except OSError as err:
            if err.errno != errno.EAGAIN and err.errno != errno.EINTR:
                if self.source.close_tty and err.errno == errno.EIO:
                    raise asyncore.ExitNow("[slave pseudo terminal closed,"
                            " pseudo tty management is terminated]")
                raise asyncore.ExitNow(err)
        else:
            if self.enable_cmds:
                if self.cmd_char_last:
                    self.cmd_char_last = False
                    if data == 'q':
                        raise asyncore.ExitNow(
                                '\n[pseudo tty management is terminated]')
                    elif data == 'c':
                        self.close_tty = True
                        return
                    elif data == 'a':
                        self.buf += CMD_CHAR
                        return
                    else:
                        self.buf += CMD_CHAR + data
                        return
                elif data == CMD_CHAR:
                    self.cmd_char_last = True
                    return
            self.buf += data

    def handle_write(self):
        """Write the content of the 'source' buffer."""
        buf = self.source.buf.encode()
        try:
            count = os.write(self.socket.fd, buf)
        except OSError as err:
            if err.errno != errno.EAGAIN and err.errno != errno.EINTR:
                raise asyncore.ExitNow(err)
        else:
            if count < len(buf):
                self.source.buf = buf[count:].decode()
            else:
                self.source.buf = ''

    def update_size(self):
        """Set the window size to match the size of its 'source'."""
        buf = array.array(str('h'), [0, 0, 0, 0])
        try:
            ret = fcntl.ioctl(self.source.socket.fd, TIOCGWINSZ, buf, 1)
            if ret == 0:
                fcntl.ioctl(self.socket.fd, TIOCSWINSZ, buf, 1)
            else:
                error('failed ioctl: %d', ret)
        except IOError as err:
            error('failed ioctl: %s', err)

class GdbInferiorPty(object):
    """Gdb inferior terminal."""

    def __init__(self, stderr_hdlr=None, map=None):
        self.stderr_hdlr = stderr_hdlr
        self.map = map
        self.master_fd = -1
        self.slave_fd = -1
        self.ptyname = ''
        self.stdin_dsptch = None
        self.master_dsptch = None
        self.orig_attr = None
        global pty_instance
        pty_instance = self

    def start(self):
        """Start the pty."""
        self.interconnect_pty()
        # postpone stderr logging while terminal is in raw mode
        if self.stderr_hdlr:
            self.stderr_hdlr.should_flush(False)
        self.stty_raw()

    def interconnect_pty(self, enable_cmds=False):
        """Interconnect pty with our terminal."""
        self.master_fd, self.slave_fd = pty.openpty()
        self.ptyname = os.ttyname(self.slave_fd)
        info('creating inferior pseudo tty \'%s\'', self.ptyname)
        self.stdin_dsptch = FileDispatcher(sys.stdin.fileno(),
                                    enable_cmds=enable_cmds, map=self.map)
        self.master_dsptch = FileDispatcher(self.master_fd,
                                    source=self.stdin_dsptch, map=self.map)
        FileDispatcher(sys.stdout.fileno(), source=self.master_dsptch,
                                                reader=False, map=self.map)

        # update pseudo terminal size
        self.master_dsptch.update_size()
        signal.signal(signal.SIGWINCH, sigwinch_handler)

    def stty_raw(self):
        """Set raw mode."""
        stdin_fd = sys.stdin.fileno()
        self.orig_attr = tcgetattr(stdin_fd)
        # use termio from the new tty and tailor it
        attr = tcgetattr(self.slave_fd)
        attr[0] &= ~(INLCR | ICRNL | IXON | IXOFF | IXANY)
        attr[1] &= ~OPOST
        attr[3] &= ~(ECHO | ECHONL | ICANON | ISIG | IEXTEN)
        attr[6][VMIN] = 1
        attr[6][VTIME] = 0
        tcsetattr(stdin_fd, TCSADRAIN, attr)

    def close(self):
        """Restore tty attributes and close pty."""
        global pty_instance
        pty_instance = None
        if self.orig_attr:
            try:
                tcsetattr(sys.stdin.fileno(), TCSADRAIN, self.orig_attr)
            except termios_error as err:
                error(err)
        close(self.master_fd)
        close(self.slave_fd)
        if self.stderr_hdlr:
            self.stderr_hdlr.should_flush(True)

