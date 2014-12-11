# vi:set ts=8 sts=4 sw=4 et tw=80:
"""
Pyclewn posix miscellaneous classes and functions.
"""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from io import open

import os
import sys
import time
import logging
import signal
import select
import errno
import fcntl
import termios
import platform
import traceback

from . import misc, asyncproc

try:
    MAXFD = os.sysconf(str("SC_OPEN_MAX"))
except ValueError:
    MAXFD = 256

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('psix')

def platform_data():
    """Return platform information."""
    return 'platform: %s' % platform.platform()

def close_fds():
    """Close all file descriptors except stdin, stdout and stderr."""
    for i in range(3, MAXFD):
        try:
            os.close(i)
        except OSError:
            pass

def daemonize():
    """Run as a daemon."""
    CHILD = 0
    # setup a pipe between the child and the parent,
    # so that the parent knows when the child has done
    # the setsid() call and is allowed to exit
    pipe_r, pipe_w = os.pipe()

    pid = os.fork()
    if pid != CHILD:
        # the read returns when the child closes the pipe
        os.close(pipe_w)
        os.read(pipe_r, 1)
        os.close(pipe_r)
        os._exit(os.EX_OK)

    # close stdin, stdout and stderr
    try:
        devnull = os.devnull
    except AttributeError:
        devnull = '/dev/null'
    fd = os.open(devnull, os.O_RDWR)
    os.close(0)
    os.close(1)
    os.close(2)
    os.dup(fd)      # replace stdin  (file descriptor 0)
    os.dup(fd)      # replace stdout (file descriptor 1)
    os.dup(fd)      # replace stderr (file descriptor 2)
    os.close(fd)    # don't need this now that we've duplicated it

    # change our process group in the child
    try:
        os.setsid()
    except OSError:
        critical('cannot run as a daemon'); raise
    os.close(pipe_r)
    os.close(pipe_w)

def sigchld_handler(signum=signal.SIGCHLD, frame=None, process=None, l=[]):
    """The SIGCHLD handler is also used to register the ProcessChannel."""
    # takes advantage of the fact that the 'l' default value
    # is evaluated only once
    if process is not None and isinstance(process, asyncproc.ProcessChannel):
        l[0:len(l)] = [process]
        return

    if len(l) and signum == signal.SIGCHLD:
        l[0].waitpid()

class ProcessChannel(asyncproc.ProcessChannel):
    """Run a posix process and communicate with it through asynchat.

    An attempt is made to start the program with a pseudo tty. We fall back
    to pipes when the first method fails.

    Instance attributes:
        sig_handler: function
            default SIGCHLD signal handler
        debug: boolean
            when True, print logs
        pid_status: str
            wait status of child termination as a string

    """

    INTERRUPT_CHAR = b'\x03'    # <Ctl-C>

    def __init__(self, socket_map, argv):
        asyncproc.ProcessChannel.__init__(self, socket_map, argv)
        self.sig_handler = None
        self.debug = (logging.getLogger().getEffectiveLevel() <= logging.INFO)
        self.pid_status = ''

    def forkexec(self):
        """Fork and exec the program after setting the pseudo tty attributes.

        Return the master pseudo tty file descriptor.

        """
        import pty
        master_fd, slave_fd = pty.openpty()
        self.ttyname = os.ttyname(slave_fd)

        # don't map '\n' to '\r\n' - no echo - INTR is <C-C>
        attr = termios.tcgetattr(slave_fd)
        attr[1] = attr[1] & ~termios.ONLCR  # oflag
        attr[3] = attr[3] & ~termios.ECHO   # lflags
        attr[6][termios.VINTR] = self.INTERRUPT_CHAR
        termios.tcsetattr(slave_fd, termios.TCSADRAIN, attr)

        self.pid = os.fork()
        if self.pid == 0:
            # establish a new session
            os.setsid()
            os.close(master_fd)

            # grab control of terminal
            # (from `The GNU C Library' (glibc-2.3.1))
            try:
                fcntl.ioctl(slave_fd, termios.TIOCSCTTY)
                # do not use the logger in the child, for some reason this
                # causes the next log entry from the father to get lost
                # info("terminal control with TIOCSCTTY ioctl call")
            except IOError:
                # this might work (it does on Linux)
                if slave_fd != 0: os.close(0)
                if slave_fd != 1: os.close(1)
                if slave_fd != 2: os.close(2)
                newfd = os.open(self.ttyname, os.O_RDWR)
                os.close(newfd)

            # slave becomes stdin/stdout/stderr of child
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            close_fds()

            # exec program
            try:
                os.execvp(self.argv[0], self.argv)
            except OSError:
                os._exit(os.EX_OSERR)

        return master_fd

    def ptyopen(self):
        """Spawn a process using a pseudo tty.

        Fall back to using pipes when failing to setup a pty.

        """
        try:
            master = self.forkexec()
        except (ImportError, OSError, os.error, termios.error):
            error("failed to setup a pseudo tty, falling back to pipes:")
            error(traceback.format_tb(sys.exc_info()[2])[-1])
            self.popen()
        else:
            pty = asyncproc.FileAsynchat(master, self, map=self.socket_map)
            self.fileasync = (pty, pty)
            info('starting "%s" with a pseudo tty', self.pgm_name)

    def popen(self):
        """Spawn a process using pipes."""
        self.ttyname = None
        asyncproc.ProcessChannel.popen(self)

    def start(self):
        """Start with a pseudo tty and fall back to pipes if that fails."""
        # register self to the sigchld_handler
        sigchld_handler(process=self)
        # register the sigchld_handler
        self.sig_handler = signal.signal(signal.SIGCHLD, sigchld_handler)

        try:
            self.ptyopen()
        except OSError:
            critical('cannot start process "%s"', self.pgm_name); raise
        info('program argv list: %s', str(self.argv))

    def waitpid(self, nohang=os.WNOHANG):
        """Wait on the process."""
        if self.pid != 0:
            try:
                pid, status = os.waitpid(self.pid, nohang)
            except OSError as err:
                # may be called by sigchld_handler while in close()
                if err.errno == errno.ECHILD:
                    return
                raise
            if (pid, status) != (0, 0):
                self.pid = 0
                if self.sig_handler is not None:
                    signal.signal(signal.SIGCHLD, self.sig_handler)

                if os.WCOREDUMP(status):
                    self.pid_status = ('%s process terminated with a core dump.'
                                    % self.pgm_name)
                elif os.WIFSIGNALED(status):
                    self.pid_status = (
                            '%s process terminated after receiving signal %d.'
                                    % (self.pgm_name, os.WTERMSIG(status)))
                elif os.WIFEXITED(status):
                    self.pid_status = ('%s process terminated with exit %d.'
                                    % (self.pgm_name, os.WEXITSTATUS(status)))
                else:
                    self.pid_status = '%s process terminated.' % self.pgm_name

                self.close()

    def close(self):
        """Close the channel and wait on the process."""
        if self.fileasync is not None:
            asyncproc.ProcessChannel.close(self)

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
                try:
                    if do_kill:
                        do_kill = False
                        os.kill(self.pid, killsig)
                except OSError:
                    break
                else:
                    time.sleep(.040)
                    self.waitpid()
                if time.time() - start > 1:
                    do_kill = True
                    start = time.time()
                    if killsig == signal.SIGTERM:
                        killsig = signal.SIGKILL
                    elif killsig == signal.SIGKILL:
                        break
                    else:
                        killsig = signal.SIGTERM

    def sendintr(self):
        """Send a SIGINT interrupt to the program."""
        if self.ttyname is not None:
            self.fileasync[1].send(self.INTERRUPT_CHAR)

