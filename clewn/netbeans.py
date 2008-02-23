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
from misc import (
        quote as _quote,
        unquote as _unquote,
        DOUBLEQUOTE as _DOUBLEQUOTE,
        )

NETBEANS_VERSION = '2.3'
FRAME_ANNO_ID = 'frame'
CONSOLE = '(clewn)_console'
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
RE_CLEWNAME = r'^\S*\(clewn\)_\w+$'                             \
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
    logger.log(misc.NBDEBUG, msg, *args, **kwargs)

def evt_ignore(buf_id, string, arg_list):
    """Ignore not implemented received events."""
    pass

def parse_msg(msg):
    """Parse a received netbeans message.

    Return the (None,) tuple or the tuple:
        is_event: boolean
            True: an event - False: a reply - None: an error
        buf_id: int
            netbeans buffer number
        event: string
            event name
        seqno: int
            netbeans sequence number
        string: str
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
        return None,

    seqno = matchobj.group('seqno')
    args = matchobj.group('args').strip()
    try:
        buf_id = int(buf_id)
        seqno = int(seqno)
    except ValueError:
        assert False, 'error in regexp'

    # a netbeans string
    string = ''
    if args and args[0] == _DOUBLEQUOTE:
        end = args.rfind(_DOUBLEQUOTE)
        if end != -1 and end != 0:
            string = args[1:end]
            string = _unquote(string)
        else:
            end = -1
    else:
        end = -1
    arg_list = args[end+1:].split()

    return (matchobj.re is re_event), buf_id, event, seqno, string, arg_list

def is_clewnbuf(bufname):
    """Return True if bufname is the name of a clewn buffer."""
    return re_clewname.match(bufname) is not None


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
        self.__name = name
        self.buf_id = buf_id
        self.nbsock = nbsock
        self.registered = False
        self.editport = None
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
            self.nbsock.last_buf = self
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
    def getname(self): return self.__name
    name = property(getname, None, None, 'buffer full path name')

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
            self.nbsock.send_cmd(self.buf, 'setDot', '%d/0' % self.lnum)
            self.is_set = True

    def remove_anno(self):
        """Remove the annotation."""
        if self.buf.registered and self.is_set:
            self.nbsock.send_cmd(self.buf, 'removeAnno', str(self.sernum))
        self.is_set = False

    def __repr__(self):
        state = 'enabled'
        if self.disabled:
            state = 'disabled'
        return 'bp %s at line %d' % (state, self.lnum)

class FrameAnnotation(misc.Singleton, Annotation):
    """The frame annotation is the sign set in the current frame."""

    def init(self, buf, lnum, nbsock):
        """Singleton initialisation."""
        self.sernum = nbsock.last_sernum
        self.nbsock = nbsock

    def __init__(self, buf, lnum, nbsock):
        self.buf = buf
        self.lnum = lnum
        self.disabled = False
        self.is_set = False
        # this happens when running regtests
        if self.nbsock is not nbsock:
            self.nbsock = nbsock
            self.sernum = nbsock.last_sernum

    def update(self, disabled=False):
        """Update the annotation."""
        if not self.is_set:
            typeNum = self.buf.define_frameanno()
            self.nbsock.send_cmd(self.buf, 'addAnno', '%d %d %d/0 -1'
                                % (self.sernum, typeNum, self.lnum))
            self.nbsock.last_buf = self.buf
            self.nbsock.send_cmd(self.buf, 'setDot', '%d/0' % self.lnum)
            self.is_set = True

    def __repr__(self):
        return 'frame at line %d' % self.lnum

class ClewnBuffer(object):
    """A ClewnBuffer instance is an edit port in gvim.

    Instance attributes:
        buf: Buffer
            the Buffer instance
        nbsock: netbeans.Netbeans
            the netbeans socket
        visible: boolean
            when True, the buffer is displayed in a Vim window
        len: int
            buffer length

    """

    def __init__(self, name, nbsock):
        assert is_clewnbuf(name)
        self.buf = nbsock.app._bset[name]
        self.buf.registered = False
        self.buf.editport = self
        self.nbsock = nbsock
        self.visible = False
        self.len = 0

    def register(self):
        """Register the buffer with netbeans vim."""
        self.nbsock.send_cmd(self.buf, 'setFullName', _quote(self.buf.name))
        self.nbsock.send_cmd(self.buf, 'setReadOnly', 'T')
        self.nbsock.send_cmd(self.buf, 'initDone', '')
        self.buf.registered = True

    def append(self, msg):
        """Append text to the end of the editport."""
        if not self.buf.registered:
            return
        self.nbsock.send_cmd(self.buf, 'setReadOnly', 'F')
        self.nbsock.send_function(self.buf, 'insert',
                                    '%s %s' % (str(self.len), _quote(msg)))
        self.nbsock.send_cmd(self.buf, 'setReadOnly', 'T')
        self.len += len(msg)

        # show the last line if the buffer is displayed in a gvim window
        if self.visible:
            self.nbsock.send_cmd(self.buf, 'setDot', str(self.len - 1))

    def clear(self):
        """Empty the editport."""
        self.len = 0
        if not self.buf.registered:
            return
        self.nbsock.send_cmd(self.buf, 'setReadOnly', 'F')
        self.nbsock.send_function(self.buf, 'remove', '0 ' + str(self.len))
        self.nbsock.send_cmd(self.buf, 'setReadOnly', 'T')

    def eofprint(self, msg, *args):
        self.nbsock.send_cmd(None, 'startAtomic')
        if args:
            msg = msg % args
        self.append(msg)

        self.nbsock.goto_last()
        self.nbsock.send_cmd(None, 'endAtomic')

class Console(ClewnBuffer):
    """The clewn console."""

    def __init__(self, nbsock):
        ClewnBuffer.__init__(self, CONSOLE, nbsock)
        self.visible = True

class DebuggerVarBuffer(ClewnBuffer):
    """The debugger variable buffer.

    Instance attributes:
        linelist: list
            the vim buffer content as a sequence of newline terminated strings
        differ: difflib.Differ
            a differ object to compare two sequences of lines

    """

    def __init__(self, nbsock):
        ClewnBuffer.__init__(self, VARIABLES_BUFFER, nbsock)
        self.linelist = []
        self.differ = difflib.Differ()

    def append(self, msg):
        assert msg.endswith('\n')
        ClewnBuffer.append(self)
        self.linelist.extend(msg.splitlines(1))

    def clear(self):
        ClewnBuffer.clear(self)
        self.linelist = []

    def update(self, content):
        """Update the vim buffer with the new content."""
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

                    # FIXME
                    # vim 7.1 remove implementation is bugged and cannot remove
                    # a single line, so insert first an empty line and
                    # remove both lines in one shot
                    #self.nbsock.send_function(self.buf, 'remove',
                    #                    str(offset) + ' ' + str(delta))
                    send_function(self.buf, 'insert',
                                        '%s %s' % (str(offset), _quote('\n')))
                    send_function(self.buf, 'remove',
                                        '%s %s' % (str(offset), str(delta + 1)))

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
        self.buf = buf
        self.seqno = seqno
        self.nbsock = nbsock

    def __call__(self, seqno, string, arg_list):
        """Process the netbeans reply."""
        raise NotImplementedError('must be implemented in subclass')

class insertReply(Reply):
    """Check the reply to an insert function."""

    def __call__(self, seqno, string, arg_list):
        error = None
        if seqno != self.seqno:
             error = 'invalid sequence number on editing %s' % self.buf.name
        if len(arg_list):
            error = 'error when editing %s: %s' % (self.buf.name,
                                                        ' '.join(arg_list))
        if error:
            self.nbsock.show_balloon('\n  %s  \n' % error)
            warning(error)
            if self.buf.editport:
                self.buf.editport.clear()

class removeReply(insertReply):
    """Check the reply to a remove function."""
    pass

class Server(asyncore.dispatcher):
    """Accept a connection on the netbeans port

    Instance attributes:
        _nb: Netbeans
            the netbeans data socket
    """

    def __init__(self, nb):
        asyncore.dispatcher.__init__(self)
        self._nb = nb
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)

    def handle_error(self):
        raise

    def handle_expt(self):
        raise NotImplementedError('unhandled exception in server')

    def handle_read(self):
        raise NotImplementedError('unhandled read event in server')

    def handle_write(self):
        raise NotImplementedError('unhandled write event in server')

    def handle_connect(self):
        raise NotImplementedError('unhandled connect event in server')

    def handle_accept(self):
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
        raise NotImplementedError('unhandled close event in server')

class Netbeans(asynchat.async_chat):
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
        app: clyapp.Application or subclass
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

    """

    def __init__(self):
        asynchat.async_chat.__init__(self, None)

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

        self.server = Server(self)
        self.set_terminator('\n')

    def set_application(self, application):
        self.app = application

    def listen(self, host, port, passwd):
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
        raise

    def handle_expt(self):
        raise NotImplementedError('unhandled exception')

    def handle_connect(self):
        pass

    def handle_accept(self):
        raise NotImplementedError('unhandled accept event')

    def handle_close(self):
        info('netbeans socket disconnected')
        self.ready = False
        self.close()

    def collect_incoming_data(self, data):
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
        is_event, buf_id, event, seqno, string, arg_list =          \
                (lambda a, b=None, c=None, d=None, e=None, f=None:
                            (a, b, c, d, e, f))(*parse_msg(msg))

        if is_event:
            evt_handler = getattr(self, "evt_%s" % event, evt_ignore)
            evt_handler(buf_id, string, arg_list)

        # a function reply: process the reply
        elif is_event == False:
            # vim may send multiple replies for one function request
            if seqno == self.last_seqno:
                return

            if self.reply_fifo.is_empty():
                raise misc.Error(
                        'got a reply with no matching function request')
            n, reply = self.reply_fifo.pop()
            reply(seqno, string, arg_list)
            self.last_seqno = seqno

        else:
            # ignore invalid message
            pass

    def open_session(self, msg):
        """Process initial netbeans messages."""
        # 'AUTH changeme'
        matchobj = re_auth.match(msg)
        if matchobj:
            if matchobj.group('passwd') == self.passwd:
                return
            else:
                raise misc.Error('invalid password: "%s"' % passwd)
        # '0:version=0 "2.3"'
        # '0:startupDone=0'
        else:
            # handle variable number of elements in returned tuple
            is_event, buf_id, event, seqno, string, arg_list =          \
                    (lambda a, b=None, c=None, d=None, e=None, f=None:
                                (a, b, c, d, e, f))(*parse_msg(msg))

            if is_event:
                if event == "version":
                    if string >= NETBEANS_VERSION:
                        self.nbversion = string
                        return
                    else:
                        raise misc.Error(
                                'invalid netbeans version: "%s"' % string)
                elif event == "startupDone":
                    self.ready = True
                    return
        raise misc.Error('received unexpected message: "%s"' % msg)

    def goto_last(self):
        """Go to the last cursor position."""
        # FIXME: restore last cursor position by using an invalid offset
        if self.last_buf is not None:
            self.send_cmd(self.last_buf, 'setDot', str(sys.maxint))

    #-----------------------------------------------------------------------
    #   Events
    #-----------------------------------------------------------------------
    def evt_balloonText(self, buf_id, string, arg_list):
        if not string:
            error('empty string in balloonText')
        else:
            self.app.balloon_text(string)

    def evt_disconnect(self, buf_id, string, arg_list):
        self.close()

    def evt_fileOpened(self, buf_id, pathname, arg_list):
        """A file was opened by the user."""
        if pathname:
            clewnbuf = is_clewnbuf(pathname)
            if os.path.isabs(pathname) or clewnbuf:
                if clewnbuf:
                    buf = self.app._bset[os.path.basename(pathname)]
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

                if not buf.editport:
                    self.last_buf = buf
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

    def evt_keyAtPos(self, buf_id, string, arg_list):
        if self.console is None or not self.console.buf.registered:
            self.console = Console(self)
            self.console.register()

        if self.dbgvarbuf is None or not self.dbgvarbuf.buf.registered:
            self.dbgvarbuf = DebuggerVarBuffer(self)

        buf = self.app._bset.getbuf(buf_id)
        if buf is None:
            error('invalid bufId: "%d" in keyAtPos', buf_id)
        elif not string:
            warning('empty string in keyAtPos')
        elif len(arg_list) != 2:
            warning('invalid arg in keyAtPos')
        else:
            if not buf.editport:
                self.last_buf = buf

            matchobj = re_lnumcol.match(arg_list[1])
            if not matchobj:
                error('invalid lnum/col: %s', arg_list[1])
            else:
                lnum = int(matchobj.group('lnum'))
                # col is not used in keyAtPos events
                # col = int(matchobj.group('col'))

                cmd, args = (lambda a='', b='':
                                    (a, b))(*string.split(None, 1))

                if self.is_editport_evt(cmd):
                    return

                self.app.dispatch_keypos(cmd, args, buf, lnum)

    def evt_killed(self, buf_id, string, arg_list):
        """A file was closed by the user."""
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
        # do not show a balloon when the application is not started
        if not self.app or not self.app.started:
            return

        # restrict size to 2000 chars, about...
        size = 2000
        if len(text) > size:
            size /= 2
            text = text[:size] + '...' + text[-size:]
        self.send_cmd(None, 'showBalloon', _quote(text))

    def special_keys(self, key):
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
        self.__last_sernum += 1
        return self.__last_sernum

    last_sernum = property(get_sernum, None, None, 'last annotation serial number')

    def __repr__(self):
         return self.__str__()

    def __str__(self):
        status = ''
        if self.ready:
            status = 'ready, netbeans version "%s", remote ' % self.nbversion
        elif not self.connected and self.addr:
            status = 'listening to '
        elif self.connected:
            status = 'connected to '
        if self.addr is not None:
            status += str(self.addr)
        return status

