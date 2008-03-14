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
# $Id$

"""Pyclewn miscellaneous classes and functions."""

import os
import os.path
import re
import tempfile
import logging
import asyncore
import asynchat
import subprocess
import signal
import atexit

DOUBLEQUOTE = '"'
QUOTED_STRING = r'"((?:\\"|[^"])+)"'
NBDEBUG = 5
NBDEBUG_LEVEL_NAME = 'nbdebug'
LOG_LEVELS = 'critical, error, warning, info, debug or ' + NBDEBUG_LEVEL_NAME

RE_ESCAPE = r'["\n\t\r\\]'                                      \
            r'# RE: escaped characters in a string'
RE_UNESCAPE = r'\\["ntr\\]'                                     \
              r'# RE: escaped characters in a quoted string'
Unused = QUOTED_STRING
Unused = NBDEBUG
Unused = LOG_LEVELS

# compile regexps
re_escape = re.compile(RE_ESCAPE, re.VERBOSE)
re_unescape = re.compile(RE_UNESCAPE, re.VERBOSE)

def logmethods(name):
    """Return the set of logging methods for the 'name' logger."""
    logger = logging.getLogger(name)
    return (
        logger.critical,
        logger.error,
        logger.warning,
        logger.info,
        logger.debug,
    )

# set the logging methods
(critical, error, warning, info, debug) = logmethods('misc')

def any(iterable):
    """Return True if any element of the iterable is true."""
    for element in iterable:
        if element:
            return True
    return False

def escape_char(matchobj):
    """Escape special characters in string."""
    if matchobj.group(0) == '"': return r'\"'
    if matchobj.group(0) == '\n': return r'\n'
    if matchobj.group(0) == '\t': return r'\t'
    if matchobj.group(0) == '\r': return r'\r'
    if matchobj.group(0) == '\\': return r'\\'
    assert False

def quote(string):
    """Quote 'string' and escape special characters."""
    return '"%s"' % re_escape.sub(escape_char, string)

def dequote(string):
    """Return the list of whitespace separated tokens from string, handling
    double quoted substrings as a token.

    Note: '\' escaped double quotes are not handled.

    """
    split = string.split(DOUBLEQUOTE)
    if len(split) % 2 != 1:
        raise Error("uneven number of double quotes in '%s'" % string)

    tok_list = []
    previous = True
    for token in split:
        token.strip()
        if token and previous:
            previous = False
            tok_list[len(tok_list):] = token.split()
        else:
            previous = True
            if token:
                tok_list.append(token)
    return tok_list

def unescape_char(matchobj):
    """Remove escape on special characters in quoted string."""
    if matchobj.group(0) == r'\"': return '"'
    if matchobj.group(0) == r'\n': return '\n'
    if matchobj.group(0) == r'\t': return '\t'
    if matchobj.group(0) == r'\r': return '\r'
    if matchobj.group(0) == r'\\': return '\\'
    assert False

def unquote(string):
    """Remove escapes from escaped characters in a quoted string."""
    return '%s' % re_unescape.sub(unescape_char, string)

def parse_keyval(regexp, line):
    """Return a dictionary built from a string of 'key="value"' pairs.

    The regexp format is:
        r'(key1|key2|...)=%s' % QUOTED_STRING

    """
    parsed = regexp.findall(line)
    if parsed and isinstance(parsed[0], tuple) and len(parsed[0]) == 2:
        keyval_dict = {}
        for (key, value) in parsed:
            keyval_dict[key] = unquote(value)
        return keyval_dict
    debug('not an iterable of key/value pairs: "%s"', line)
    return None

# subprocess.check_call does not exist in Python 2.4
def check_call(*popenargs, **kwargs):
    """Run command with arguments.  Wait for command to complete.  If
    the exit code was zero then return, otherwise raise
    CalledProcessError.  The CalledProcessError object will have the
    return code in the returncode attribute.

    The arguments are the same as for the Popen constructor.  Example:

    check_call(["ls", "-l"])

    """
    retcode = subprocess.call(*popenargs, **kwargs)
    cmd = kwargs.get("args")
    if cmd is None:
        cmd = popenargs[0]
    if retcode:
        raise CalledProcessError(retcode, cmd)
    return retcode

def smallest_prefix(word, other):
    """Return the smallest prefix of 'word', not prefix of 'other'."""
    assert word
    if other.startswith(word):
        return ''
    for i in range(len(word)):
        p = word[0:i+1]
        if p != other[0:i+1]:
            break
    return p

def smallpref_inlist(word, strlist):
    """Return the smallest prefix of 'word' that allows completion in 'strlist'.

    Return 'word', when it is a prefix of one of the keywords in 'strlist'.

    """
    assert strlist
    assert word not in strlist
    s = sorted(strlist + [word])
    i = s.index(word)
    previous = next = ''
    if i > 0:
        previous = smallest_prefix(word, s[i - 1]) or word
    if i < len(s) - 1:
        next = smallest_prefix(word, s[i + 1]) or word
    return max(previous, next)

def unlink(filename):
    """Unlink a file."""
    if filename and os.path.exists(filename):
        try:
            os.unlink(filename)
        except OSError:
            pass

def daemonize():
    """Run as a daemon."""
    CHILD = 0
    if os.name == 'posix':
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


class Error(Exception):
    """Base class for exceptions in pyclewn."""

class CalledProcessError(Error):
    """This exception is raised when a process run by check_call() returns
    a non-zero exit status.  The exit status will be stored in the
    returncode attribute.

    """

    def __init__(self, returncode, cmd):
        """Constructor."""
        Error.__init__(self)
        self.returncode = returncode
        self.cmd = cmd

    def __str__(self):
        """Return the error message."""
        return "Command '%s' returned non-zero exit status %d"  \
                                        % (self.cmd, self.returncode)

class TmpFile(file):
    """An instance of this class is a writtable temporary file object."""

    def __init__(self, prefix):
        """Constructor."""
        self.tmpname = None
        try:
            fd, self.tmpname = tempfile.mkstemp('.clewn', prefix)
            os.close(fd)
            file.__init__(self, self.tmpname, 'w')
        except (OSError, IOError):
            unlink(self.tmpname)
            critical('cannot create temporary file'); raise
        else:
            atexit.register(unlink, self.tmpname)

    def __del__(self):
        """Unlink the file."""
        unlink(self.tmpname)

class Singleton(object):
    """A singleton, there is only one instance of this class."""

    def __new__(cls, *args, **kwds):
        """Create the single instance."""
        it = cls.__dict__.get("__it__")
        if it is not None:
            return it
        cls.__it__ = it = object.__new__(cls)
        it.init(*args, **kwds)
        return it

    def init(self, *args, **kwds):
        """Override in subclass."""
        pass

if os.name == 'posix':
    import fcntl

    def sigchld_handler(signum=signal.SIGCHLD, frame=None, process=None, l=[]):
        """The SIGCHLD handler is also used to register the ProcessChannel."""
        # takes advantage of the fact that the 'l' default value
        # is evaluated only once
        unused = frame
        if process is not None and isinstance(process, ProcessChannel):
            l[0:len(l)] = [process]
            return

        if len(l) and signum == signal.SIGCHLD:
            l[0].waitpid()

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
            """Constructor."""
            self.fobj = None
            if isinstance(f, file):
                self.fobj = f
                self.fd = f.fileno()
            else:
                self.fd = f
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

    class FileAsynchat(asynchat.async_chat):
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

        def __init__(self, f, channel, reader=None):
            """Constructor."""
            asynchat.async_chat.__init__(self)
            self.channel = channel
            self.reader = reader
            self.connected = True
            self.ibuff = []
            self.set_terminator('\n')

            if isinstance(f, file):
                self._fileno = f.fileno()
            else:
                self._fileno = f
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
            unused = self
            raise

        def handle_expt(self):
            """Process a select exception."""
            unused = self
            assert False, 'unhandled exception'

        def handle_connect(self):
            """Process a connect event."""
            unused = self
            assert False, 'unhandled connect event'

        def handle_accept(self):
            """Process an accept event."""
            unused = self
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
            self.ibuff.append(data)

        def found_terminator(self):
            """Have the ProcessChannel instance process the received data."""
            msg = "".join(self.ibuff)
            self.ibuff = []
            self.channel.handle_line(msg)

    class ProcessChannel(object):
        """An abstract class to run a process and communicate with it, through asynchat.

        An attempt is made to start the program with a pseudo tty. We fall back
        to pipes when the first method fails.

        To implement a concrete subclass of ProcessChannel, one must implement
        the handle_line method that process the lines (new line terminated)
        received from the program stdout and stderr.

        Instance attributes:
            argv: tuple or list
                argv arguments
            pgm: str
                process name
            fileasync: tuple
                the readable and writable instances of FileAsynchat helpers
            pid: int
                spawned process pid
            sig_handler: function
                default SIGCHLD signal handler
            ttyname: str
                pseudo tty name

        """

        INTERRUPT_CHAR = chr(3)     # <Ctl-C>

        def __init__(self, argv):
            """Constructor."""
            assert argv
            self.argv = argv
            self.pgm = os.path.basename(self.argv[0])
            self.fileasync = None
            self.pid = 0
            self.sig_handler = None
            self.ttyname = None

        def forkexec(self):
            """Fork and exec the program after setting the pseudo tty attributes.

            Return the pseudo tty file descriptor.

            """
            import pty, termios

            fd, slave_fd = pty.openpty()
            self.ttyname = os.ttyname(slave_fd)

            # don't map '\n' to '\r\n' - no echo - INTR is <C-C>
            try:
                attr = termios.tcgetattr(fd)
                attr[1] = attr[1] & ~termios.ONLCR  # oflag
                attr[3] = attr[3] & ~termios.ECHO   # lflags
                attr[6][termios.VINTR] = self.INTERRUPT_CHAR
                termios.tcsetattr(fd, termios.TCSADRAIN, attr)
            except termios.error:
                critical("failed to set termios attributes to pseudo tty")

            self.pid = os.fork()
            if self.pid == 0:
                # establish a new session
                os.setsid()
                os.close(fd)

                # grab control of terminal
                # (from `The GNU C Library' (glibc-2.3.1))
                try:
                    fcntl.ioctl(slave_fd, termios.TIOCSCTTY)
                    info("terminal control with TIOCSCTTY ioctl call")
                except:
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
                if (slave_fd > 2):
                    os.close(slave_fd)

                # exec program
                os.execvp(self.pgm, self.argv)
                critical('failed to execvp "%"', self.pgm); raise

            return fd

        def start(self):
            """Spawn the process and connect its stdio to our fileasync tuple."""
            # register self to the sigchld_handler
            sigchld_handler(process=self)
            # register the sigchld_handler
            self.sig_handler = signal.signal(signal.SIGCHLD, sigchld_handler)

            try:
                try:
                    # uncomment the following line to force using pipes
                    #raise ImportError

                    # use a pseudo tty
                    pty = FileAsynchat(self.forkexec(), self)
                    self.fileasync = (pty, pty)
                    info('starting "%s" with a pseudo tty', self.pgm)

                except (ImportError, OSError):

                    # fall back to using pipes
                    self.ttyname = None
                    proc = subprocess.Popen(self.argv,
                                        stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT)
                    self.fileasync = (FileAsynchat(proc.stdout, self, True),
                                        FileAsynchat(proc.stdin, self, False))
                    self.pid = proc.pid
                    info('starting "%s" with two pipes', self.pgm)

            except OSError:
                critical('cannot start process "%"', self.pgm); raise

            info('program argv list: %s', str(self.argv))

        def waitpid(self):
            """Wait on the process."""
            if self.pid != 0:
                pid, status = os.waitpid(self.pid, os.WNOHANG)
                if (pid, status) != (0, 0):
                    self.pid = 0
                    if self.sig_handler is not None:
                        signal.signal(signal.SIGCHLD, self.sig_handler)
                    self.close()

                    if os.WCOREDUMP(status):
                        info("process %s terminated with a core dump",
                                self.pgm)
                    elif os.WIFSIGNALED(status):
                        info("process %s terminated after receiving signal %d",
                                self.pgm, os.WTERMSIG(status))
                    elif os.WIFEXITED(status):
                        info("process %s terminated with exit %d",
                                self.pgm, os.WEXITSTATUS(status))
                    else:
                        info("process %s terminated", self.pgm)

        def close(self):
            """Close the channel an wait on the process."""
            if self.fileasync is not None:
                # it is safe to close the same FileAsynchat twice
                self.fileasync[0].close()
                self.fileasync[1].close()
                self.fileasync = None
                self.waitpid()

        def sendintr(self):
            """Send a SIGINT interrupt to the program."""
            if self.ttyname is not None:
                self.fileasync[1].send(self.INTERRUPT_CHAR)

        def handle_line(self, line):
            """Process the line received from the program stdout and stderr."""
            unused = line
            if self.fileasync is not None:
                raise NotImplementedError('handle_line in ProcessChannel')

        def write(self, data):
            """Write a chunk of data to the process stdin."""
            if self.fileasync is not None:
                if not data.endswith('\n'):
                    data += '\n'
                self.fileasync[1].push(data)

