# vi:set ts=8 sts=4 sw=4 et tw=80:
"""
The process module.
"""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import pty
import fcntl
import asyncio
import termios
import time
import signal
import warnings
from abc import ABCMeta, abstractmethod
FlowControlMixin = asyncio.streams.FlowControlMixin

from . import PY32, misc

CTL_C = b'\x03'
SYNC_STR_LEN= 1

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('proc')

def close_fds():
    """Close all file descriptors except stdin, stdout and stderr."""
    sc_open_max = -1
    try:
        sc_open_max = os.sysconf(str('SC_OPEN_MAX'))
    except ValueError:
        pass
    if sc_open_max < 0:
        sc_open_max = 256
    for i in range(3, sc_open_max):
        try:
            os.close(i)
        except OSError:
            pass

def daemonize():
    """Run as a daemon."""
    # Setup a pipe between the child and the parent, so that the parent knows
    # when the child is ready.
    pipe_r, pipe_w = os.pipe()

    pid = os.fork()
    if pid != 0:
        # The read returns when the child closes the pipe.
        os.close(pipe_w)
        os.read(pipe_r, 1)
        os.close(pipe_r)
        os._exit(os.EX_OK)

    os.close(pipe_r)
    # Change the process group in the child.
    try:
        os.setsid()
    except OSError:
        critical('cannot run as a daemon'); raise

    # Redirect the standard streams to devnull.
    fd = os.open(os.devnull, os.O_RDWR)
    os.dup2(fd, 0)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    os.close(fd)
    os.close(pipe_w)

class PtySocket(object):
    """A pty endpoint masquerading as a socket."""

    def __init__(self, fd, pgm=None):
        self.fd = fd
        self.pgm = pgm

    def fileno(self):
        return self.fd

    def recv(self, *args):
        return os.read(self.fd, *args)

    def send(self, *args):
        return os.write(self.fd, *args)

    def setblocking(self, blocking):
        misc.set_blocking(self.fd, blocking)

    def getsockname(self):
        return 'pty_socket'

    def getpeername(self):
        return str(self.pgm)

    def close(self):
        if self.fd < 0:
            return
        os.close(self.fd)
        self.fd = -1

    def __del__(self):
        if self.fd >= 0 and PY32:
            warnings.warn("unclosed file %r" % self, ResourceWarning)
        self.close()

class Process(FlowControlMixin, object):
    """Abstract class implementing the Protocol of a spawned posix process.

    Instance attributes:
        pid: int
            spawned process pid
        pid_status: str
            wait status of the child as a string

    """

    __metaclass__ = ABCMeta

    def __init__(self, loop=None):
        FlowControlMixin.__init__(self, loop)
        self.loop = loop
        self.connect_task = None
        self._pgm = None
        self.pid = 0
        self.pid_status = ''
        self.socket = None
        self.transport = None
        self.addr = None
        self.ibuff = []

    def connection_made(self, transport):
        FlowControlMixin.connection_made(self, transport)
        self.transport = transport
        # Synchronize with the child.
        transport.write(SYNC_STR_LEN * b'A' + b'\n')
        self.addr = transport.get_extra_info('peername')
        info('connection to %s', str(self.addr))

    def connection_lost(self, exc):
        FlowControlMixin.connection_lost(self, exc)
        info('connection lost: %s', str(self.addr))
        if exc:
            error(exc)
        self.waitpid()
        self.close()

    def data_received(self, data):
        misc.handle_as_lines(data, self.ibuff, self.handle_line)

    def forkexec(self, args):
        master_fd, slave_fd = pty.openpty()
        ptyname = os.ttyname(slave_fd)

        # Don't map '\n' to '\r\n' - no echo.
        attr = termios.tcgetattr(slave_fd)
        if hasattr(termios, 'ONLCR'):
            attr[1] &= ~termios.ONLCR       # oflag
        attr[3] &= ~termios.ECHO            # lflags
        if hasattr(termios, 'ECHOCTL'):
            attr[3] &= ~termios.ECHOCTL
        attr[3] |= termios.ICANON
        attr[6][termios.VINTR] = CTL_C
        termios.tcsetattr(slave_fd, termios.TCSADRAIN, attr)

        self.pid = os.fork()
        if self.pid == 0:
            # Establish a new session.
            os.setsid()
            os.close(master_fd)

            # Grab control of the terminal.
            # (from `The GNU C Library' (glibc-2.3.1))
            try:
                fcntl.ioctl(slave_fd, termios.TIOCSCTTY)
            except IOError:
                # This might work (it does on Linux).
                if slave_fd != 0: os.close(0)
                if slave_fd != 1: os.close(1)
                if slave_fd != 2: os.close(2)
                newfd = os.open(ptyname, os.O_RDWR)
                os.close(newfd)

            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            close_fds()

            # Wait until the parent has setup the asyncio loop.
            os.read(0, SYNC_STR_LEN + 1)
            os.execvp(args[0], args)

        os.close(slave_fd)
        return master_fd

    @asyncio.coroutine
    def connect(self, args):
        yield from(self.loop.create_connection(lambda: self,
                                                   sock=self.socket))
        info('program args list: %s', str(args))

    def start(self, args):
        assert args
        self._pgm = os.path.basename(args[0])
        try:
            master_fd = self.forkexec(args)
        except OSError as exc:
            critical('cannot start process "%s": %s', self._pgm, exc); raise
        self.socket = PtySocket(master_fd, args)
        self.connect_task = asyncio.Task(self.connect(args), loop=self.loop)

    @abstractmethod
    def handle_line(self, line):
        pass

    def write(self, data):
        if self.transport:
            if not data.endswith('\n'):
                data += '\n'
            self.transport.write(data.encode())
        else:
            error('cannot write: %s', data)

    def sendintr(self):
        """Send a SIGINT interrupt to the program."""
        if self.transport:
            self.transport.write(CTL_C)

    def close(self):
        task = self.connect_task
        if task:
            if task.done() and not task.cancelled():
                exc = task.exception()
                if exc:
                    error('in Process task: %s', exc)
            else:
                task.cancel()
        if self.transport:
            self.transport.close()
            self.transport = None
        if self.socket:
            self.socket.close()

        # Gdb issues:
        # * gdb 7.6.1 sometimes get stuck in a futex call on terminating.
        #   So we need to kill it with SIGKILL.
        # * gdb 7.8.1 segfaults (in PyObject_Call()) when the SIGTERM is
        #   received within the processing of Py_Finalize() which is done on
        #   processing the 'quit' command. So we must not send the SIGTERM
        #   aggressively but wait for gdb to terminate nicely.
        start = time.time()
        do_kill = False
        killsig = None
        while self.pid != 0:
            if time.time() - start > 1:
                start = time.time()
                do_kill = True
                if killsig == signal.SIGTERM:
                    killsig = signal.SIGKILL
                elif killsig == signal.SIGKILL:
                    break
                else:
                    killsig = signal.SIGTERM
            try:
                if do_kill:
                    do_kill = False
                    os.kill(self.pid, killsig)
            except OSError:
                break
            else:
                time.sleep(.040)
                self.waitpid()

    def waitpid(self):
        if self.pid == 0:
            return

        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
        except OSError as exc:
            self.pid = 0
            error('waitpid: %s', exc)
            return

        if (pid, status) != (0, 0):
            self.pid = 0
            if os.WCOREDUMP(status):
                self.pid_status = ('%s process terminated with a core dump.'
                                % self._pgm)
            elif os.WIFSIGNALED(status):
                self.pid_status = (
                        '%s process terminated after receiving signal %d.'
                                % (self._pgm, os.WTERMSIG(status)))
            elif os.WIFEXITED(status):
                self.pid_status = ('%s process terminated with exit %d.'
                                % (self._pgm, os.WEXITSTATUS(status)))
            else:
                self.pid_status = '%s process terminated.' % self._pgm

