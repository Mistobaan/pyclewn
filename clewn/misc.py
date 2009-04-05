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

import __builtin__
import sys
import os
import os.path
import re
import tempfile
import logging
import threading
import socket
import select
import errno
import asyncore
import asynchat
import subprocess
import atexit
import pprint
if os.name == 'posix':
    import fcntl

try:
    MAXFD = os.sysconf("SC_OPEN_MAX")
except:
    MAXFD = 256

DOUBLEQUOTE = '"'
QUOTED_STRING = r'"((?:\\"|[^"])+)"'
NBDEBUG = 5
NBDEBUG_LEVEL_NAME = 'nbdebug'
LOG_LEVELS = 'critical, error, warning, info, debug or ' + NBDEBUG_LEVEL_NAME

RE_TOKEN_SPLIT = r'"((?:\\"|[^"])+)"|\s*(\S+)\s*'               \
                 r'# RE: split a string in tokens, handling quotes'
RE_ESCAPE = r'["\n\t\r\\]'                                      \
            r'# RE: escaped characters in a string'
RE_UNESCAPE = r'\\["ntr\\]'                                     \
              r'# RE: escaped characters in a quoted string'
Unused = NBDEBUG
Unused = LOG_LEVELS

# compile regexps
re_quoted = re.compile(QUOTED_STRING, re.VERBOSE)
re_token_split = re.compile(RE_TOKEN_SPLIT, re.VERBOSE)
re_escape = re.compile(RE_ESCAPE, re.VERBOSE)
re_unescape = re.compile(RE_UNESCAPE, re.VERBOSE)
Unused = re_quoted

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
Unused = error
Unused = warning

# the global event that clewn_select is waiting on
_clewn_select_event = threading.Event()

# Peek thread states
STS_STARTED, STS_STOPPED = range(2)
# timers in Peek run method, in seconds
MAX_WAIT_TIME = 0.100
POLL_TIME = 0.010

def previous_evaluation(f, previous={}):
    """Decorator for functions returning previous result when args are unchanged."""
    def _dec(*args):
        """The decorator."""
        if previous.has_key(f) and previous[f][0] == args:
            return previous[f][1]
        previous[f] = [args]
        ret = f(*args)
        previous[f].append(ret)
        return ret
    return _dec

# 'any' new in python 2.5
if 'any' in __builtin__.__dict__.keys():
    misc_any = __builtin__.any
    Unused = misc_any
else:
    def misc_any(iterable):
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
        raise Error, ("uneven number of double quotes in '%s'" % string)

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

def norm_unixpath(line, ispath=False):
    """Convert backward slashes to forward slashes on Windows.

    If 'ispath' is True, then convert the whole line.
    Otherwise, this is done for all existing paths in line
    and handles quoted paths.
    """
    if os.name != 'nt':
        return line
    if ispath:
        return line.replace('\\', '/')

    # match is a list of tuples
    # first element of tuple is '' when it is a keyword
    # second element of tuple is '' when it is a quoted string
    match = re_token_split.findall(line)
    if not match:
        return line
    result = []
    changed = False
    for elem in match:
        quoted = False
        if not elem[0]:
            token = elem[1]
        elif not elem[1]:
            quoted = True
            token = elem[0]
        else:
            assert False
        if os.path.exists(token) and '\\' in token:
            token = token.replace('\\', '/')
            changed = True
        if quoted:
            token = '"' + token + '"'
        result.append(token)
    if not changed:
        return line
    return ' '.join(result)

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

def close_fds():
    """Close all file descriptors except stdin, stdout and stderr."""
    for i in xrange(3, MAXFD):
        try:
            os.close(i)
        except:
            pass

def last_traceback():
    """Return the last trace back."""
    t, v, tb = sys.exc_info()
    assert tb
    while tb:
        filename = tb.tb_frame.f_code.co_filename
        lnum = tb.tb_lineno
        last_tb = tb
        tb = tb.tb_next
    del tb

    return t, v, filename, lnum, last_tb


class Error(Exception):
    """Base class for misc exceptions in pyclewn."""

class PrettyPrinterString(pprint.PrettyPrinter):
    """Strings are printed with str() to avoid duplicate backslash."""

    def format(self, object, context, maxlevels, level):
        """Format un object."""
        unused = self
        if type(object) is str:
            return "'" + str(object) + "'", True, False
        return pprint._safe_repr(object, context, maxlevels, level)

def pformat(object, indent=1, width=80, depth=None):
    """Format a Python object into a pretty-printed representation."""
    return PrettyPrinterString(
                    indent=indent, width=width, depth=depth).pformat(object)

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
        if os.name == 'nt':
            self.set_terminator('\r\n')
        else:
            self.set_terminator('\n')

        if isinstance(f, file):
            self._fileno = f.fileno()
        else:
            self._fileno = f
        self.set_file(f)

        # set it to non-blocking mode
        if os.name == 'posix':
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
    """An abstract class to run a command with a process through async_chat.

    To implement a concrete subclass of ProcessChannel, one must implement
    the handle_line method that process the lines (new line terminated)
    received from the program stdout and stderr.

    Instance attributes:
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

    def __init__(self, argv):
        """Constructor."""
        assert argv
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
                            close_fds=(sys.platform != "win32"))
        self.fileasync = (FileAsynchat(proc.stdout, self, True),
                            FileAsynchat(proc.stdin, self, False))
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

class Peek(threading.Thread):
    """A generic peek thread as an abstract class."""

    def __init__(self, name):
        """Constructor."""
        threading.Thread.__init__(self, name=name)
        self.state = STS_STOPPED
        self.start_peeking = threading.Event()
        self.stop_peeking = threading.Event()
        self.have_started = threading.Event()
        self.have_stopped = threading.Event()

    def run(self):
        """The thread peeks the file object(s).

        The thread is notified by an event of the transition to perform:
            start_peeking
            stop_peeking
        The thread sends a _clewn_select_event to clewn_select when a read,
        write or except event is available.
        The thread reports its state with a have_started or have_stopped event.

        """
        info('thread started: %s', self)
        while self.isRunning():
            self.start_peeking.wait(MAX_WAIT_TIME)
            if not self.start_peeking.isSet():
                continue
            self.start_peeking.clear()
            self.have_started.set()

            try:
                while self.isRunning():
                    if self.peek():
                        _clewn_select_event.set()

                    self.stop_peeking.wait(POLL_TIME)
                    if self.stop_peeking.isSet():
                        self.stop_peeking.clear()
                        break
            finally:
                self.have_stopped.set()

        # logger may be closed when terminating pyclewn
        if not isinstance(self, SelectPeek):
            info('thread terminated: %s', self)

    def peek(self):
        """Peek the file object for one or more events.

        Return True when an event is available, False otherwise.

        """
        unused = self
        assert False, 'missing implementation of the peek method'

    def isRunning(self):
        """Return the thread status."""
        unused = self
        assert False, 'missing implementation of the isRunning method'

    def wait_event(self, event_name):
        """Blocking wait on event_name from the thread."""
        while True:
            # wait 10 seconds before reporting an error
            event = getattr(self, event_name)
            event.wait(10)
            if event.isSet():
                event.clear()
                return
            else:
                warning('no %s event from %s thread',
                                event_name, self.getName())

    def start_thread(self):
        """Called by clewn_select to start the thread."""
        if self.isAlive():
            # debug('ask the thread to start: %s', self)
            self.start_peeking.set()
            # debug('wait until thread have_started: %s', self)
            self.wait_event('have_started')
            # debug('the thread is now started: %s', self)
            self.state = STS_STARTED

    def stop_thread(self):
        """Called by clewn_select to stop the thread."""
        if self.state != STS_STARTED:
            return
        if self.isAlive():
            # debug('ask the thread to stop: %s', self)
            self.stop_peeking.set()
            # debug('wait until thread have_stopped: %s', self)
            self.wait_event('have_stopped')
            # debug('the thread is now stopped: %s', self)
            self.state = STS_STOPPED

class SelectPeek(Peek):
    """The select peek thread.

    The thread peeks on all waitable sockets set in clewn_select.

    """
    def __init__(self, fdmap):
        """Constructor."""
        Peek.__init__(self, 'socket')
        self.fdmap = fdmap
        self.iwtd = []
        self.owtd = []
        self.ewtd = []
        self.iwtd_out = []
        self.owtd_out = []
        self.ewtd_out = []

    def set_waitable(self, iwtd, owtd, ewtd):
        """Set each waitable file descriptor list."""
        self.iwtd = iwtd
        self.owtd = owtd
        self.ewtd = ewtd
        self.iwtd_out = []
        self.owtd_out = []
        self.ewtd_out = []

    def peek(self):
        """Run select on all sockets."""
        assert self.iwtd or self.owtd or self.ewtd
        # debug('%s, %s, %s', self.iwtd, self.owtd, self.ewtd)
        try:
            iwtd, owtd, ewtd = select.select(self.iwtd, self.owtd, self.ewtd, 0)
        except select.error, err:
            if err[0] != errno.EINTR:
                error('failed select call: ', err); raise
            else:
                return False
        if iwtd or owtd or ewtd:
            (self.iwtd_out, self.owtd_out, self.ewtd_out) = (iwtd, owtd, ewtd)
            return True
        return False

    def isRunning(self):
        """Return the thread status."""
        return len(self.fdmap)

    def stop_thread(self):
        """Called by clewn_select to stop the select thread."""
        Peek.stop_thread(self)
        # debug('select return: %s, %s, %s',
        #           self.iwtd_out, self.owtd_out, self.ewtd_out)
        return self.iwtd_out, self.owtd_out, self.ewtd_out

class PipePeek(Peek):
    """The abstract pipe peek class."""

    def __init__(self, fd, asyncobj):
        """Constructor."""
        Peek.__init__(self, 'pipe')
        self.fd = fd
        self.asyncobj = asyncobj
        self.read_event = False

    def isRunning(self):
        """Return the thread status."""
        return self.asyncobj.socket.connected

    def start_thread(self):
        """Called by clewn_select to start the thread."""
        self.read_event = False
        Peek.start_thread(self)

