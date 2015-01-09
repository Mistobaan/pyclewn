# vi:set ts=8 sts=4 sw=4 et tw=80:
"""
Tty interconnection with a pty.
"""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import sys
import errno
import os
import pty
import asyncio
import termios
import stat
import array
import signal
import fcntl
from termios import (INLCR, ICRNL, IXON, IXOFF, IXANY, OPOST, ECHO, ECHONL,
                     ICANON, ISIG, IEXTEN, VMIN, VTIME, VINTR, VEOF,
                     TCSADRAIN, TIOCGWINSZ, TIOCSWINSZ)
FlowControlMixin = asyncio.streams.FlowControlMixin
StreamReader = asyncio.StreamReader
StreamReaderProtocol = asyncio.StreamReaderProtocol

from . import ClewnError, misc

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('tty')

BUFFER_SIZE = 8096
CTL_A = b'\x01'
usage = """Two characters sequence commands:
  '<Ctl-A> q' exit immediately
  '<Ctl-A> a' send a <Ctl-A> character
"""

class Channel(object):
    def __init__(self, name, fdin, fdout, reader=None, loop=None):
        self.name = name
        self.fdin = os.dup(fdin)
        misc.set_blocking(self.fdin, False)
        self.fdout = os.dup(fdout)
        misc.set_blocking(self.fdout, False)
        self.loop = loop
        if reader:
            self.reader = reader.stream_reader
            self.reader_proto = reader
        else:
            self.reader = StreamReader()
            self.reader_proto = StreamReaderProtocol(self.reader)
        self.writer_proto = FlowControlMixin(self.loop)
        mode = os.fstat(fdin).st_mode
        self.fdin_istty = stat.S_ISCHR(mode)
        mode = os.fstat(fdout).st_mode
        self.fdout_isfifo = stat.S_ISFIFO(mode)
        self.fdout_istty = stat.S_ISCHR(mode)

    @asyncio.coroutine
    def copy_in_to_out(self):
        transport = None
        try:
            f_in = os.fdopen(self.fdin, 'r')
            f_out = os.fdopen(self.fdout, 'w')
            yield from(self.loop.connect_read_pipe(
                                            lambda: self.reader_proto, f_in))

            if self.fdout_isfifo or self.fdout_istty:
                transport, protocol = yield from(self.loop.connect_write_pipe(
                                            lambda: self.writer_proto, f_out))
                writer = asyncio.StreamWriter(
                                transport, protocol, self.reader, self.loop)

                # Remove the reader added by connect_write_pipe() as a
                # workaround to Tulip issue 147:
                # "Fix _UnixWritePipeTransport to support TTY".
                if self.fdout_istty:
                    self.loop.remove_reader(f_out.fileno())

            while True:
                try:
                    chunk = yield from(self.reader.read(BUFFER_SIZE))
                except OSError as e:
                    # The read() syscall returns -1 when the slave side of the
                    # pty is closed.
                    if not self.fdin_istty or e.errno != errno.EIO:
                        raise
                    break
                if not chunk:
                    # An EOF character (Ctl-D) has been received by
                    # the pty_forkexec terminal interface (if any).
                    break
                if self.fdout_isfifo or self.fdout_istty:
                    writer.write(chunk)
                    yield from(writer.drain())
                else:
                    os.write(self.fdout, chunk)
        except asyncio.CancelledError:
            pass
        finally:
            if self.reader._transport:
                self.reader._transport.close()
            if transport:
                # When the slave side of the pty is closed, write() syscalls
                # to the pty return -1, EAGAIN, and the BlockingIOError
                # exception being ignored by 'writer', leads to an infinite
                # loop in 'to_pty' until the task is cancelled.
                # Abort the 'to_pty' channel transport.
                if self.name == 'to_pty':
                    transport.abort()
                else:
                    transport.close()

class InferiorTTY(StreamReaderProtocol, object):
    def __init__(self, stream_reader, cmds=False, stderr=None, loop=None):
        StreamReaderProtocol.__init__(self, stream_reader, loop=loop)
        self.stream_reader = stream_reader
        self.cmds = cmds
        self.stderr = stderr
        self.orig_attr = None
        self.cmd_char_last = False

        self.master_fd, self.slave_fd = pty.openpty()
        self.ptyname = os.ttyname(self.slave_fd)
        print('%s pseudo terminal created.' % self.ptyname)
        if self.cmds:
            print(usage)
        self.stty_raw()

        # Update pseudo terminal size.
        self.update_size()
        self.orig_sigwinch = signal.signal(signal.SIGWINCH, self.update_size)

    def connection_lost(self, exc):
        StreamReaderProtocol.connection_lost(self, exc)
        self.close()
        if exc:
            error('InferiorTTY: %s', exc)

    def connection_made(self, transport):
        StreamReaderProtocol.connection_made(self, transport)
        self.transport = transport

    def data_received(self, data):
        if self.cmds:
            if self.cmd_char_last:
                self.cmd_char_last = False
                if data == b'q':
                    self.transport.close()
                    return
                elif data == b'a':
                    data = CTL_A
                else:
                    data = CTL_A + data
            elif data == CTL_A:
                self.cmd_char_last = True
                return

        StreamReaderProtocol.data_received(self, data)

    def update_size(self, *args):
        """Set the window size to match the size of the terminal."""
        buf = array.array(str('h'), [0, 0, 0, 0])
        try:
            fcntl.ioctl(sys.stdin.fileno(), TIOCGWINSZ, buf, 1)
            fcntl.ioctl(self.master_fd, TIOCSWINSZ, buf, 1)
        except IOError as exc:
            error('update_size: %s', exc)

    def stty_raw(self):
        # Postpone stderr logging while the terminal is in raw mode.
        if self.stderr:
            self.stderr.should_flush(False)

        # Use settings from the new tty and tailor it to set raw mode on stdin.
        stdin_fd = sys.stdin.fileno()
        self.orig_attr = termios.tcgetattr(stdin_fd)
        attr = termios.tcgetattr(self.slave_fd)
        attr[0] &= ~(INLCR | ICRNL | IXON | IXOFF | IXANY)
        attr[1] &= ~OPOST
        attr[3] &= ~(ECHO | ECHONL | ICANON | ISIG | IEXTEN)
        attr[6][VMIN] = 1
        attr[6][VTIME] = 0
        termios.tcsetattr(stdin_fd, TCSADRAIN, attr)

    def close(self):
        if self.orig_attr:
            termios.tcsetattr(sys.stdin.fileno(), TCSADRAIN, self.orig_attr)
        if self.stderr:
            self.stderr.should_flush(True)
        signal.signal(signal.SIGWINCH, self.orig_sigwinch)
        os.close(self.master_fd)
        os.close(self.slave_fd)

def inferior_tty(stderr=None, loop=None, cmds=False):
    """Return two tasks that switch bytes between the tty and a pty."""
    if not os.isatty(sys.stdin.fileno()):
        raise ClewnError('stdin is not a tty')

    if not loop:
        loop = asyncio.get_event_loop()

    reader = InferiorTTY(StreamReader(), cmds=cmds, stderr=stderr, loop=loop)
    master_fd = reader.master_fd
    to_pty = Channel('to_pty', sys.stdin.fileno(), master_fd,
                     reader=reader, loop=loop)
    from_pty = Channel('from_pty', master_fd, sys.stdout.fileno(), loop=loop)
    tasks = [asyncio.Task(c.copy_in_to_out(), loop=loop) for
                                            c in (from_pty, to_pty)]
    return tasks, reader.ptyname

