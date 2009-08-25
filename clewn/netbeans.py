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
"""The netbeans protocol implementation."""

import sys
import os.path
import logging
import re
import socket
import asyncore
import asynchat
import difflib

import misc
import clewn
from misc import (
        quote as _quote,
        unquote as _unquote,
        DOUBLEQUOTE as _DOUBLEQUOTE,
        )

NETBEANS_VERSION = '2.3'
FRAME_ANNO_ID = 'frame'
CONSOLE = '(clewn)_console'
CONSOLE_MAXLINES = 10000
VARIABLES_BUFFER = '(clewn)_dbgvar'

RE_AUTH = r'^\s*AUTH\s*(?P<passwd>\S+)\s*$'                     \
          r'# RE: password authentication'
RE_RESPONSE = r'^\s*(?P<seqno>\d+)\s*(?P<args>.*)\s*$'          \
              r'# RE: a netbeans response'
RE_EVENT = r'^\s*(?P<buf_id>\d+):(?P<event>\S+)=(?P<seqno>\d+)' \
           r'\s*(?P<args>.*)\s*$'                               \
           r'# RE: a netbeans event message'
RE_LNUMCOL = r'^(?P<lnum>\d+)/(?P<col>\d+)'                     \
             r'# RE: lnum/col'
RE_CLEWNAME = r'^\s*(?P<path>.*)\(clewn\)_\w+$'                 \
              r'# RE: a valid ClewnBuffer name'

# compile regexps
re_auth = re.compile(RE_AUTH, re.VERBOSE)
re_response = re.compile(RE_RESPONSE, re.VERBOSE)
re_event = re.compile(RE_EVENT, re.VERBOSE)
re_lnumcol = re.compile(RE_LNUMCOL, re.VERBOSE)
re_clewname = re.compile(RE_CLEWNAME, re.VERBOSE)

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('nb')
logger = logging.getLogger('nb')
def debug(msg, *args, **kwargs):
    """Force NBDEBUG log level for debug messages."""
    logger.log(misc.NBDEBUG, msg, *args, **kwargs)

def evt_ignore(buf_id, msg, arg_list):
    """Ignore not implemented received events."""
    pass

def parse_msg(msg):
    """Parse a received netbeans message.

    Return the (None,) tuple or the tuple:
        is_event: boolean
            True: an event - False: a reply
        buf_id: int
            netbeans buffer number
        event: str
            event name
        seqno: int
            netbeans sequence number
        nbstring: str
            the netbeans string
        arg_list: list
            list of remaining args after the netbeans string

    """
    matchobj = re_event.match(msg)
    if matchobj:
        # an event
        buf_id = matchobj.group('buf_id')
        event = matchobj.group('event')
    else:
        # a reply
        buf_id = '0'
        event = ''
        matchobj = re_response.match(msg)
    if not matchobj:
        error('discarding invalid netbeans message: "%s"', msg)
        return (None,)

    seqno = matchobj.group('seqno')
    args = matchobj.group('args').strip()
    try:
        buf_id = int(buf_id)
        seqno = int(seqno)
    except ValueError:
        assert False, 'error in regexp'

    # a netbeans string
    nbstring = ''
    if args and args[0] == _DOUBLEQUOTE:
        end = args.rfind(_DOUBLEQUOTE)
        if end != -1 and end != 0:
            nbstring = args[1:end]
            nbstring = _unquote(nbstring)
        else:
            end = -1
    else:
        end = -1
    arg_list = args[end+1:].split()

    return (matchobj.re is re_event), buf_id, event, seqno, nbstring, arg_list

def is_clewnbuf(bufname):
    """Return True if bufname is the name of a clewn buffer."""
    matchobj = re_clewname.match(bufname)
    if matchobj:
        path = matchobj.group('path')
        if not path or os.path.exists(path):
            return True
    return False

class Buffer(dict):
    """A Vim buffer is a dictionary of annotations {anno_id: annotation}.

    Instance attributes:
        name: readonly property
            full pathname
        buf_id: int
            netbeans buffer number, starting at one
        nbsock: netbeans.Netbeans
            the netbeans socket
        registered: boolean
            True: buffer registered to Vim with netbeans
        editport: ClewnBuffer
            the ClewnBuffer associated with this Buffer instance
        lnum: int
            cursor line number
        col: int
            cursor column
        type_num: int
            last sequence number of a defined annotation
        bp_tnum: int
            sequence number of the enabled breakpoint annotation
            the sequence number of the disabled breakpoint annotation
            is bp_tnum + 1
        frame_tnum: int
            sequence number of the frame annotation

    """

    def __init__(self, name, buf_id, nbsock):
        """Constructor."""
        self.__name = name
        self.buf_id = buf_id
        self.nbsock = nbsock
        self.registered = False
        self.editport = None
        self.lnum = None
        self.col = None
        self.type_num = self.bp_tnum = self.frame_tnum = 0

    def define_frameanno(self):
        """Define the frame annotation."""
        if not self.frame_tnum:
            self.type_num += 1
            self.frame_tnum = self.type_num
            self.nbsock.send_cmd(self, 'defineAnnoType',
                '%d "frame" "" "=>" none %d' % (self.frame_tnum, 0xefb735))
        return self.frame_tnum

    def define_bpanno(self):
        """Define the two annotations for breakpoints."""
        if not self.bp_tnum:
            self.bp_tnum = self.type_num + 1
            self.type_num += 2 # two annotations are defined in sequence
            self.nbsock.send_cmd(self, 'defineAnnoType',
                '%d "bpEnabled" "" "bp" none %d' % (self.bp_tnum, 0x0c3def))
            self.nbsock.send_cmd(self, "defineAnnoType",
                '%d "bpDisabled" "" "bp" none %d' % (self.type_num , 0x3fef4b))
        return self.bp_tnum

    def add_anno(self, anno_id, lnum):
        """Add an annotation."""
        assert not anno_id in self.keys()
        if anno_id == FRAME_ANNO_ID:
            self[anno_id] = FrameAnnotation(self, lnum, self.nbsock)
        else:
            self[anno_id] = Annotation(self, lnum, self.nbsock)
        self.update(anno_id)

    def delete_anno(self, anno_id):
        """Delete an annotation."""
        assert anno_id in self.keys()
        self[anno_id].remove_anno()
        del self[anno_id]

    def update(self, anno_id=None, disabled=False):
        """Update the buffer with netbeans."""
        # open file in netbeans
        if not self.registered:
            self.nbsock.send_cmd(self, 'editFile', _quote(self.name))
            self.nbsock.send_cmd(self, 'putBufferNumber', _quote(self.name))
            self.nbsock.send_cmd(self, 'stopDocumentListen')
            self.registered = True

        # update annotations
        if anno_id:
            self[anno_id].update(disabled)
        else:
            for anno_id in self.keys():
                self[anno_id].update()

    def removeall(self, lnum=None):
        """Remove all netbeans annotations at line lnum.

        When lnum is None, remove all annotations.

        """
        for anno_id in self.keys():
            if lnum is None or self[anno_id].lnum == lnum:
                self[anno_id].remove_anno()

    # readonly property
    def getname(self):
        """Buffer full path name."""
        return self.__name
    name = property(getname, None, None, getname.__doc__)

class Annotation(object):
    """A netbeans annotation.

    Instance attributes:
        buf: Buffer
            buffer container
        lnum: int
            line number
        nbsock: netbeans.Netbeans
            the netbeans socket
        disabled: boolean
            True when the breakpoint is disabled
        sernum: int
            serial number of this placed annotation,
            used to be able to remove it
        is_set: boolean
            True when annotation has been added with netbeans

    """

    def __init__(self, buf, lnum, nbsock, disabled=False):
        """Constructor."""
        self.buf = buf
        self.lnum = lnum
        self.nbsock = nbsock
        self.disabled = disabled
        self.sernum = nbsock.last_sernum
        self.is_set = False

    def update(self, disabled=False):
        """Update the annotation."""
        if self.disabled != disabled:
            self.remove_anno()
            self.disabled = disabled
        if not self.is_set:
            typeNum = self.buf.define_bpanno()
            if self.disabled:
                typeNum += 1
            self.nbsock.send_cmd(self.buf, 'addAnno', '%d %d %d/0 -1'
                                % (self.sernum, typeNum, self.lnum))
            self.nbsock.last_buf = self.buf
            self.nbsock.last_buf.lnum = self.lnum
            self.nbsock.last_buf.col = 0

            self.nbsock.send_cmd(self.buf, 'setDot', '%d/0' % self.lnum)
            self.is_set = True

    def remove_anno(self):
        """Remove the annotation."""
        if self.buf.registered and self.is_set:
            self.nbsock.send_cmd(self.buf, 'removeAnno', str(self.sernum))
        self.is_set = False

    def __repr__(self):
        """Return breakpoint information."""
        state = 'enabled'
        if self.disabled:
            state = 'disabled'
        return 'bp %s at line %d' % (state, self.lnum)

class FrameAnnotation(misc.Singleton, Annotation):
    """The frame annotation is the sign set in the current frame."""

    def init(self, buf, lnum, nbsock):
        """Singleton initialisation."""
        unused = buf
        unused = lnum
        self.disabled = False
        self.sernum = nbsock.last_sernum
        self.nbsock = nbsock

    def __init__(self, buf, lnum, nbsock):
        """Constructor."""
        self.buf = buf
        self.lnum = lnum
        unused = nbsock
        self.disabled = False
        self.is_set = False
        # this happens when running regtests
        if self.nbsock is not nbsock:
            self.nbsock = nbsock
            self.sernum = nbsock.last_sernum

    def update(self, disabled=False):
        """Update the annotation."""
        unused = disabled
        if not self.is_set:
            typeNum = self.buf.define_frameanno()
            self.nbsock.send_cmd(self.buf, 'addAnno', '%d %d %d/0 -1'
                                % (self.sernum, typeNum, self.lnum))
            self.nbsock.last_buf = self.buf
            self.nbsock.last_buf.lnum = self.lnum
            self.nbsock.last_buf.col = 0

            self.nbsock.send_cmd(self.buf, 'setDot', '%d/0' % self.lnum)
            self.is_set = True

    def __repr__(self):
        """Return frame information."""
        return 'frame at line %d' % self.lnum

class LineCluster(object):
    """Group lines in a bounded list of elements of a maximum size.

    Instance attributes:
        nb_element: int
            maximum number of elements
        nb_lines: int
            maximum number of lines per element
        last_element: list
            the last element in the cluster
            each element is a list of [lines_count, bytes_count]
        cluster: list
            the list of elements

    """

    def __init__(self, nb_element, nb_lines):
        """Constructor."""
        self.nb_element = nb_element
        self.nb_lines = nb_lines
        self.last_element = [0, 0]
        self.cluster = [self.last_element]

    def append(self, msg):
        """Add 'msg' number of lines and bytes count to the last element.

        When the list of elements has reached its maximum size and the last
        element is full, the first element in the list is deleted and the number
        of bytes in this first element is returned.

        """
        self.last_element[0] += msg.count('\n')
        self.last_element[1] += len(msg)
        #print 'line_cluster: %d elements, lines/bytes %s, last_element %s' % (
        #            len(self.cluster),
        #            reduce(lambda x, y: [x[0]+y[0], x[1]+y[1]], self.cluster),
        #            self.last_element)
        if msg.endswith('\n') and self.last_element[0] >= self.nb_lines:
            self.last_element = [0, 0]
            self.cluster.append(self.last_element)
            if len(self.cluster) > self.nb_element:
                info('line_cluster: clearing %d lines', self.cluster[0][0])
                return self.cluster.pop(0)[1]
        return 0

class ClewnBuffer(object):
    """A ClewnBuffer instance is an edit port in gvim.

    Instance attributes:
        buf: Buffer
            the Buffer instance
        nbsock: netbeans.Netbeans
            the netbeans socket
        visible: boolean
            when True, the buffer is displayed in a Vim window
        nonempty_last: boolean
            when True, the last line in the vim buffer is non empty
        len: int
            buffer length
        dirty: boolean
            when True, must update the vim buffer

    """

    def __init__(self, name, nbsock):
        """Constructor."""
        assert is_clewnbuf(name)
        self.buf = nbsock.app._bset[name]
        self.buf.registered = False
        self.buf.editport = self
        self.nbsock = nbsock
        self.visible = False
        self.nonempty_last = False
        self.len = 0
        self.dirty = False

    def register(self):
        """Register the buffer with netbeans vim."""
        self.nbsock.send_cmd(self.buf, 'editFile', _quote(self.buf.name))
        self.nbsock.send_cmd(self.buf, 'setReadOnly', 'T')
        self.buf.registered = True

    def append(self, msg):
        """Append text to the end of the editport."""
        if not self.buf.registered:
            return
        if self.nonempty_last:
            self.nonempty_last = False
            self.len -= 1
        self.nbsock.send_cmd(self.buf, 'setReadOnly', 'F')
        self.nbsock.send_function(self.buf, 'insert',
                                    '%s %s' % (str(self.len), _quote(msg)))
        self.nbsock.send_cmd(self.buf, 'setReadOnly', 'T')
        if not msg.endswith('\n'):
            self.nonempty_last = True
            self.len += 1
        self.len += len(msg)

        # show the last line if the buffer is displayed in a gvim window
        if self.visible:
            self.nbsock.send_cmd(self.buf, 'setDot', str(self.len - 1))

    def update(self, content):
        """Update the buffer content in Vim."""
        unused = content
        self.dirty = False

    def remove(self, offset, count):
        """Remove 'count' bytes at 'offset'.

        Vim 7.1 remove implementation is buggy and cannot remove a single or
        partial line. In this case we insert first an empty line and remove all
        lines in one shot (NOTE that this implies this method MUST NOT be
        called when removing partial lines with a buggy vim 7.1).
        It is Ok with a more recent vim version.

        """
        send_function = self.nbsock.send_function
        if self.nbsock.remove_bug:
            send_function(self.buf, 'insert',
                            '%s %s' % (str(offset), _quote('\n')))
            send_function(self.buf, 'remove',
                            '%s %s' % (str(offset), str(count + 1)))
        else:
            send_function(self.buf, 'remove',
                            '%s %s' % (str(offset), str(count)))

    def clear(self, count=-1):
        """Clear the ClewnBuffer instance.

        When 'count' is -1, clear the whole buffer.
        Otherwise, delete the first 'count' bytes and set the cursor
        at the end of the buffer.

        """
        if not self.buf.registered:
            self.visible = False
        if count == -1:
            count = self.len
        assert 0 <= count <= self.len
        if count:
            if self.buf.registered:
                self.nbsock.send_cmd(self.buf, 'setReadOnly', 'F')
                self.remove(0, count)
                self.nbsock.send_cmd(self.buf, 'setReadOnly', 'T')
            self.len -= count
            if self.len == 0:
                self.nonempty_last = False
            elif self.visible:
                self.nbsock.send_cmd(self.buf, 'setDot', str(self.len - 1))
            info('%s length: %d bytes', self.buf.name, self.len)

    def eofprint(self, msg, *args):
        """Print at end of buffer and restore previous cursor position."""
        self.nbsock.send_cmd(None, 'startAtomic')
        if args:
            msg = msg % args
        self.append(msg)

        self.nbsock.goto_last()
        self.nbsock.send_cmd(None, 'endAtomic')

class Console(ClewnBuffer):
    """The clewn console.

    Instance attributes:
        line_cluster: LineCluster
            the object handling the Console maximum number of lines

    """

    def __init__(self, nbsock):
        """Constructor."""
        ClewnBuffer.__init__(self, CONSOLE, nbsock)
        self.visible = True
        self.line_cluster = LineCluster(10, self.nbsock.max_lines / 10)

    def append(self, msg):
        """Append text to the end of the editport."""
        ClewnBuffer.append(self, msg)
        self.clear(self.line_cluster.append(msg))

class DebuggerVarBuffer(ClewnBuffer):
    """The debugger variable buffer.

    Instance attributes:
        linelist: list
            the vim buffer content as a sequence of newline terminated strings
        foldlnum: int
            line number of the current fold operation
        differ: difflib.Differ
            a differ object to compare two sequences of lines

    """

    def __init__(self, nbsock):
        """Constructor."""
        ClewnBuffer.__init__(self, VARIABLES_BUFFER, nbsock)
        self.linelist = []
        self.foldlnum = None
        self.differ = difflib.Differ()

    def append(self, msg):
        """Append 'msg' to the end of the buffer."""
        assert msg.endswith('\n')
        ClewnBuffer.append(self, msg)
        self.linelist.extend(msg.splitlines(1))

    def clear(self, len=-1):
        """Clear the buffer."""
        ClewnBuffer.clear(self, len)
        self.linelist = []

    def update(self, content):
        """Update the vim buffer with the new content."""
        self.dirty = False
        if not self.buf.registered:
            return

        offset = 0
        readonly = True
        newlist = content.splitlines(1)
        send_cmd = self.nbsock.send_cmd
        send_function = self.nbsock.send_function
        try:
            for line in self.differ.compare(self.linelist, newlist):
                assert len(line) > 2

                if line.startswith('  '):
                    offset += len(line) - 2
                elif line.startswith('+ '):
                    if readonly:
                        send_cmd(None, 'startAtomic')
                        send_cmd(self.buf, 'setReadOnly', 'F')
                        readonly = False
                    delta = len(line) - 2

                    send_function(self.buf, 'insert',
                                    '%s %s' % (str(offset), _quote(line[2:])))
                    self.len += delta
                    offset += delta
                elif line.startswith('- '):
                    if readonly:
                        send_cmd(self.buf, 'setReadOnly', 'F')
                        readonly = False
                    delta = len(line) - 2
                    self.remove(offset, delta)
                    self.len -= delta
                elif line.startswith('? '):
                    pass    # skip line not present in either input sequence
                else:
                    assert False, "line not prefixed by the differ instance"
        finally:
            if not readonly:
                send_cmd(self.buf, 'setReadOnly', 'T')
                self.nbsock.goto_last()
                send_cmd(None, 'endAtomic')

        self.linelist = newlist

class Reply(object):
    """Abstract class. A Reply instance is a callable used to process
    the result of a  function call in the reply received from netbeans.

    Instance attributes:
        buf: Buffer
            the buffer in use when the function is invoked
        seqno: int
            netbeans sequence number
        nbsock: netbeans.Netbeans
            the netbeans socket
    """

    def __init__(self, buf, seqno, nbsock):
        """Constructor."""
        self.buf = buf
        self.seqno = seqno
        self.nbsock = nbsock

    def clear_onerror(self, err):
        """Clear the clewn buffer on error in the reply."""
        clewnbuffer = self.buf.editport
        assert clewnbuffer is not None
        clewnbuffer.dirty = True
        clewnbuffer.clear()
        err += '\nThe buffer will be restored on the next gdb command.'
        self.nbsock.show_balloon(err)
        error(err)

    def __call__(self, seqno, nbstring, arg_list):
        """Process the netbeans reply."""
        unused = self
        unused = seqno
        unused = nbstring
        unused = arg_list
        raise NotImplementedError('must be implemented in subclass')

class insertReply(Reply):
    """Check the reply to an insert function."""

    def __call__(self, seqno, nbstring, arg_list):
        """Check the reply to an insert or remove netbeans function."""
        unused = nbstring
        if seqno != self.seqno:
             error('%s: invalid sequence number on edit', self.buf.name)
             return
        if len(arg_list):
            err = '%s: got edit error from netbeans: %s' %      \
                            (self.buf.name, ' '.join(arg_list))
            self.nbsock.send_function(self.buf, 'getLength')
            self.clear_onerror(err)

# Check the reply to a remove function.
removeReply = insertReply

class getLengthReply(Reply):
    """Check the reply to a getLength function."""

    def __call__(self, seqno, nbstring, arg_list):
        """Check the length of the Vim buffer."""
        unused = nbstring
        if seqno != self.seqno:
            error('%s: invalid sequence number on getLength', self.buf.name)
            return
        clewnbuffer = self.buf.editport
        assert clewnbuffer is not None
        assert len(arg_list) == 1
        length = int(arg_list[0])
        if clewnbuffer.len != length:
            err= '%s: invalid buffer length.\n'     \
                 '(pyclewn:%d - vim: %d)' %         \
                 (self.buf.name, clewnbuffer.len, length)
            clewnbuffer.len = length
            self.clear_onerror(err)

class Server(asyncore.dispatcher):
    """Accept a connection on the netbeans port

    Instance attributes:
        _nb: Netbeans
            the netbeans data socket
    """

    def __init__(self, nb):
        """Constructor."""
        asyncore.dispatcher.__init__(self)
        self._nb = nb
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)

    def handle_error(self):
        """Raise the exception."""
        unused = self
        raise

    def handle_expt(self):
        """We are not listening on exceptional conditions."""
        unused = self
        assert False, 'unhandled exceptional condition'

    def handle_read(self):
        """Not implemented."""
        unused = self
        assert False, 'unhandled read event in server'

    def handle_write(self):
        """Not implemented."""
        unused = self
        assert False, 'unhandled write event in server'

    def handle_connect(self):
        """Not implemented."""
        unused = self
        assert False, 'unhandled connect event in server'

    def handle_accept(self):
        """Accept the connection from Vim."""
        try:
            conn, addr = self.socket.accept()
            conn.setblocking(0)
            self._nb.set_socket(conn)
            self._nb.addr = addr
            self.close()
            info('connected to %s', str(addr))
        except socket.error:
            critical('error accepting a connection on the server socket'); raise

    def handle_close(self):
        """Handle an asyncore close event."""
        unused = self
        assert False, 'unhandled close event in server'

class Netbeans(asynchat.async_chat, object):
    """A Netbeans instance exchanges netbeans messages on a socket.

    Instance attributes:
        last_sernum: readonly property
            last annotation serial number
        last_buf: Buffer
            the last buffer (non ClewnBuffer) where the cursor was positioned
        console: Console
            the pyclewn console
        dbgvarbuf: DebuggerVarBuffer
            the pyclewn debugger var buffer
        reply_fifo: fifo
            the fifo containing Reply instances used to check netbeans replies
        addr: tuple
            IP address: host, port tuple
        ready: boolean
            startupDone event has been received
        app: clewn.Application or subclass
            the application instance
        passwd: str
            netbeans password
        nbversion: str
            remote netbeans version
        ibuff: list
            list of strings received from netbeans
        seqno: int
            netbeans sequence number
        last_seqno: int
            last reply sequence number
        server: Server
            server socket listening on the netbeans port
        remove_bug: boolean
            True with vim 7.1 before patch 207
        max_lines: int
            Console maximum number of lines

    """

    def __init__(self):
        """Constructor."""
        asynchat.async_chat.__init__(self)

        self.__last_sernum = 0
        self.last_buf = None
        self.console = None
        self.dbgvarbuf = None
        self.reply_fifo = asynchat.fifo()
        self.addr = None
        self.ready = False
        self.app = None
        self.passwd = None
        self.nbversion = None
        self.ibuff = []
        self.seqno = 0
        self.last_seqno = 0
        self.remove_bug = True
        self.max_lines = CONSOLE_MAXLINES

        self.server = Server(self)
        self.set_terminator('\n')

    def set_application(self, application):
        """Notify of the current application."""
        self.app = application

    def nb_listen(self, host, port, passwd):
        """Have the server socket listen on the netbeans port."""
        self.passwd = passwd
        try:
            port = int(port)
        except ValueError:
            critical('"%s" is not a port number', port); raise
        try:
            self.server.set_reuse_addr()
            self.server.bind((host, port))
            self.server.listen(1)
            self.addr = host, port
        except socket.error:
            critical('cannot listen on "(%s, %s)"', host, port); raise

    def close(self):
        """Close netbeans the server and the application."""
        try:
            self.server.close()
            asynchat.async_chat.close(self)
            self.connected = False
        except AttributeError:
            pass

        # close the application on a netbeans disconnect
        if self.app is not None:
            self.app.close()

    def handle_error(self):
        """Raise the exception."""
        unused = self
        raise

    def handle_expt(self):
        """We are not listening on exceptional conditions."""
        unused = self
        assert False, 'unhandled exceptional condition'

    def handle_connect(self):
        """Not implemented."""
        unused = self

    def handle_accept(self):
        """Not implemented."""
        unused = self
        assert False, 'unhandled accept event'

    def handle_close(self):
        """Handle an async_chat close event."""
        info('netbeans socket disconnected')
        self.ready = False
        self.close()

    def collect_incoming_data(self, data):
        """Process async_chat received data."""
        self.ibuff.append(data)

    def found_terminator(self):
        """Process new line terminated netbeans message."""
        msg = "".join(self.ibuff)
        self.ibuff = []
        debug(msg)

        if not self.ready:
            self.open_session(msg)
            return

        if not self.app:
            warning('ignoring "%s": the application is not started', msg)
            return

        # handle variable number of elements in returned tuple
        is_event, buf_id, event, seqno, nbstring, arg_list =        \
                (lambda a, b=None, c=None, d=None, e=None, f=None:
                            (a, b, c, d, e, f))(*parse_msg(msg))

        if is_event is None:
            # ignore invalid message
            pass
        elif is_event:
            evt_handler = getattr(self, "evt_%s" % event, evt_ignore)
            evt_handler(buf_id, nbstring, arg_list)

        # a function reply: process the reply
        else:
            # vim may send multiple replies for one function request
            if seqno == self.last_seqno:
                return

            if self.reply_fifo.is_empty():
                raise clewn.Error, (
                        'got a reply with no matching function request')
            n, reply = self.reply_fifo.pop()
            unused = n
            reply(seqno, nbstring, arg_list)
            self.last_seqno = seqno


    def open_session(self, msg):
        """Process initial netbeans messages."""
        # 'AUTH changeme'
        matchobj = re_auth.match(msg)
        if matchobj:
            if matchobj.group('passwd') == self.passwd:
                return
            else:
                raise clewn.Error, ('invalid password: "%s"' % self.passwd)
        # '0:version=0 "2.3"'
        # '0:startupDone=0'
        else:
            # handle variable number of elements in returned tuple
            is_event, buf_id, event, seqno, nbstring, arg_list =        \
                    (lambda a, b=None, c=None, d=None, e=None, f=None:
                                (a, b, c, d, e, f))(*parse_msg(msg))
            unused = arg_list
            unused = buf_id
            unused = seqno

            if is_event:
                if event == "version":
                    if nbstring >= NETBEANS_VERSION:
                        self.nbversion = nbstring
                        return
                    else:
                        raise clewn.Error, (
                                'invalid netbeans version: "%s"' % nbstring)
                elif event == "startupDone":
                    self.ready = True
                    return
        raise clewn.Error, ('received unexpected message: "%s"' % msg)

    def goto_last(self):
        """Go to the last cursor position."""
        if self.last_buf is not None:
            self.send_cmd(self.last_buf, 'setDot', '%d/%d' %
                                    (self.last_buf.lnum, self.last_buf.col))

    #-----------------------------------------------------------------------
    #   Events
    #-----------------------------------------------------------------------
    def evt_balloonText(self, buf_id, nbstring, arg_list):
        """Process a balloonText netbeans event."""
        unused = arg_list
        unused = buf_id
        if not nbstring:
            error('empty string in balloonText')
        else:
            self.app.balloon_text(nbstring)

    def evt_disconnect(self, buf_id, nbstring, arg_list):
        """Process a disconnect netbeans event."""
        unused = arg_list
        unused = nbstring
        unused = buf_id
        self.close()

    def evt_fileOpened(self, buf_id, pathname, arg_list):
        """A file was opened by the user."""
        unused = arg_list
        if pathname:
            clewnbuf = is_clewnbuf(pathname)
            if os.path.isabs(pathname) or clewnbuf:
                if clewnbuf:
                    buf = self.app._bset[os.path.basename(pathname)]
                    if buf.editport is not None:
                        buf.editport.visible = True
                else:
                    buf = self.app._bset[pathname]

                if buf.buf_id != buf_id:
                    if buf_id == 0:
                        self.send_cmd(buf, 'putBufferNumber', _quote(pathname))
                        self.send_cmd(buf, 'stopDocumentListen')
                        buf.registered = True
                        buf.update()
                    else:
                        warning('got fileOpened with wrong bufId')
                elif clewnbuf and not isinstance(buf.editport, Console):
                    self.send_function(buf, 'getLength')

            else:
                warning('absolute pathname required')
        else:
            self.show_balloon(
                '\nYou cannot use netbeans on a "[No Name]" file.\n'
                'Please, edit a file.\n'
                )

    def is_editport_evt(self, cmd):
        """Return True when this is an editport open/close event.

        The event notifies clewn of a change in the state of the editport,
        as visible (open) or not visible (close) in a gvim window.

        """
        tokens = cmd.split('.')
        if len(tokens) == 3 and tokens[0] == 'ClewnBuffer':
            if tokens[2] == 'open':
                visible = True
            elif tokens[2] == 'close':
                visible = False
            else:
                return False
            try:
                clss = eval(tokens[1])
            except NameError:
                return False
            if not issubclass(clss, ClewnBuffer):
                return False
            for buf in self.app._bset.values():
                editport = buf.editport
                if editport and isinstance(editport, clss):
                    editport.visible = visible
                    return True
        return False

    def evt_keyAtPos(self, buf_id, nbstring, arg_list):
        """Process a keyAtPos netbeans event."""
        if self.console is None or not self.console.buf.registered:
            self.console = Console(self)
            self.console.register()

        if self.dbgvarbuf is None or not self.dbgvarbuf.buf.registered:
            self.dbgvarbuf = DebuggerVarBuffer(self)

        buf = self.app._bset.getbuf(buf_id)
        if buf is None:
            error('invalid bufId: "%d" in keyAtPos', buf_id)
        elif not nbstring:
            warning('empty string in keyAtPos')
        elif len(arg_list) != 2:
            warning('invalid arg in keyAtPos')
        else:
            matchobj = re_lnumcol.match(arg_list[1])
            if not matchobj:
                error('invalid lnum/col: %s', arg_list[1])
            else:
                lnum = int(matchobj.group('lnum'))
                col = int(matchobj.group('col'))
                if not buf.editport or not isinstance(buf.editport, Console):
                    self.last_buf = buf
                    self.last_buf.lnum = lnum
                    self.last_buf.col = col

                cmd, args = (lambda a='', b='':
                                    (a, b))(*nbstring.split(None, 1))

                if self.is_editport_evt(cmd):
                    return

                self.app.dispatch_keypos(cmd, args, buf, lnum)

    def evt_killed(self, buf_id, nbstring, arg_list):
        """A file was closed by the user."""
        unused = nbstring
        unused = arg_list
        # buffer killed by netbeans, signs are already removed by gvim
        buf = self.app._bset.getbuf(buf_id)
        if buf is None:
            error('invalid bufId: "%s" in killed', buf_id)
        else:
            buf.registered = False
            buf.removeall()

            if buf is self.last_buf:
                self.last_buf = None
            if buf.editport:
                buf.editport.clear()

    #-----------------------------------------------------------------------
    #   Commands - Functions
    #-----------------------------------------------------------------------

    def initiate_send (self):
        """Keep messages sent to gvim buffered in the fifo, while the netbeans
        connection is not ready.
        """
        if self.ready:
            try:
                asynchat.async_chat.initiate_send(self)
            except socket.error:
                self.close()

    def show_balloon(self, text):
        """Show the Vim balloon."""
        # do not show a balloon when the application is not started
        if not self.app or not self.app.started:
            return

        # restrict size to 2000 chars, about...
        size = 2000
        if len(text) > size:
            size //= 2
            text = text[:size] + '...' + text[-size:]
        self.send_cmd(None, 'showBalloon', _quote(text))

    def special_keys(self, key):
        """Send the specialKeys netbeans command."""
        self.send_cmd(None, 'specialKeys', _quote(key))

    def send_cmd(self, buf, cmd, args=''):
        """Send a command to gvim."""
        self.send_request('%d:%s!%d%s%s\n', buf, cmd, args)

    def send_function(self, buf, function, args=''):
        """Send a function call to gvim."""
        # race condition: queue the pending reply first, before the
        # reply received on the socket gets a chance to be processed
        try:
            clss = eval('%sReply' % function)
        except NameError:
            assert False, 'internal error, no reply class for %s' % function
        assert issubclass(clss, Reply)
        reply = clss(buf, self.seqno + 1, self)
        self.reply_fifo.push(reply)

        self.send_request('%d:%s/%d%s%s\n', buf, function, args)

    def send_request(self, fmt, buf, request, args):
        """Send a netbeans function or command."""
        self.seqno += 1
        buf_id = 0
        space = ' '
        if isinstance(buf, Buffer):
            buf_id = buf.buf_id
        if not args:
            space = ''
        msg = fmt % (buf_id, request, self.seqno, space, args)
        debug(msg.strip('\n'))
        self.push(msg)

    # readonly property
    def get_sernum(self):
        """Return a unique sernum."""
        self.__last_sernum += 1
        return self.__last_sernum

    last_sernum = property(get_sernum, None, None, 'last annotation serial number')

    def __repr__(self):
        """Return the async_chat representation."""
        return self.__str__()

    def __str__(self):
        """Return the string representation."""
        status = ''
        if self.ready:
            status = 'ready, netbeans version "%s"'                         \
                     ' (vim "netbeans remove function" bug: %s), remote '   \
                     % (self.nbversion, self.remove_bug)
        elif not self.connected and self.addr:
            status = 'listening to '
        elif self.connected:
            status = 'connected to '
        if self.addr is not None:
            status += str(self.addr)
        return status

