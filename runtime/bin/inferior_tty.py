#! /usr/bin/env python
#
# Copyright (C) 2011 Xavier de Gaye.
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
"""
Create a pseudo terminal to be used as the controlling terminal of a process
debugged by gdb.

When the name of this module is 'gdb_wrapper.py', spawn an xterm with a gdb
instance that is setup to use the current terminal as its inferior tty. The
command line arguments of 'gdb_wrapper' are passed unchanged to gdb.
"""

import os
import sys
import array
import errno
import pty
import signal
import fcntl
import time
import asyncore
import subprocess
import traceback
import logging
from termios import tcgetattr, tcsetattr, TCSADRAIN, TIOCGWINSZ, TIOCSWINSZ
from termios import error as termios_error

debug = False
# the command character: 'C-a'
CMD_CHAR = chr(1)
this_pgm = os.path.basename(sys.argv[0]).rsplit('.py', 1)[0]
usage = ("""'%s' two characters sequence commands:
    'C-a q' exit immediately
    'C-a c' close the slave pseudo terminal and exit after the gdb inferior has
            terminated
    'C-a a' send a \'C-a\' character
""" % this_pgm)

class FileDispatcher(asyncore.file_dispatcher):
    """The FileDispatcher does input/output on a file descriptor.

    Read data into 'buf'.
    Write the content of the FileDispatcher 'source' buffer 'buf'.
    When 'enable_cmds' is True, handle the command character 'C-a'.
    """

    def __init__(self, fd, source=None, reader=True, enable_cmds=False):
        """Constructor."""
        asyncore.file_dispatcher.__init__(self, fd)
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
            data = self.socket.recv(1024)
        except OSError, err:
            if err[0] != errno.EAGAIN and err[0] != errno.EINTR:
                if self.source.close_tty and err[0] == errno.EIO:
                    raise asyncore.ExitNow("[slave pseudo terminal closed,"
                            " '%s' is terminated]" % this_pgm)
                raise asyncore.ExitNow(err)
        else:
            if self.enable_cmds:
                if self.cmd_char_last:
                    self.cmd_char_last = False
                    if data == 'q':
                        raise asyncore.ExitNow(
                                '\n[%s is terminating]' % this_pgm)
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
        buf = self.source.buf
        try:
            count = os.write(self.socket.fd, buf)
        except OSError, err:
            if err[0] != errno.EAGAIN and err[0] != errno.EINTR:
                raise asyncore.ExitNow(err)
        else:
            self.source.buf = buf[count:]

    def close(self):
        """Close the dispatcher."""
        self.del_channel()

    def update_size(self):
        """Set the window size to match the size of its 'source'."""
        buf = array.array('h', [0, 0, 0, 0])
        ret = fcntl.ioctl(self.source.socket.fd, TIOCGWINSZ, buf, 1)
        if ret == 0:
            fcntl.ioctl(self.socket.fd, TIOCSWINSZ, buf, 1)
        else:
            logging.error('failed ioctl: %d', ret)

def setlogger(filename):
    """Set the logging file handler."""
    if debug:
        root = logging.getLogger()
        root.addHandler(logging.FileHandler(filename))
        root.setLevel(logging.DEBUG)

def abort(msg=''):
    """Abort after printing 'msg'."""
    if msg:
        print >> sys.stderr, msg
    sys.exit(1)

def prompt(msg):
    """Prompt for user input."""
    # remove non-blocking mode
    fd = sys.stdin.fileno()
    flags = fcntl.fcntl(fd, fcntl.F_GETFL, 0)
    flags = flags & ~os.O_NONBLOCK
    fcntl.fcntl(fd, fcntl.F_SETFL, flags)
    return raw_input(msg)

def spawn_terminal_emulator(pty_term, slave_fd, master_fd):
    """Run ourself in xterm to monitor gdb exit status."""
    argv = ['xterm', '-e', 'python']
    argv.extend(sys.argv)
    logging.debug('spawning: \'%s\'', argv)
    pid = os.fork()
    if pid == 0:
        os.close(slave_fd)
        os.close(master_fd)
        try:
            os.environ['PTY_TERM'] = pty_term
            os.execvp(argv[0], argv)
        except OSError, err:
            msg = 'argv: \'%s\'\n' % argv
            msg += 'Spawing \'%s\' failed: %s' % (argv[0], err)
            abort(msg)
    return pid

def spawn_gdb(ptyname, term):
    """Spawn gdb."""
    argv = ['gdb', '-tty', ptyname, '--eval-command',
                        'set environment TERM = %s' % term]
    argv.extend(sys.argv[1:])
    logging.debug('spawn_gdb: \'%s\'', argv)

    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        ret = subprocess.call(argv)
        if ret < 0:
            print >> sys.stderr,\
                '%s was terminated by signal %d' % (argv[0], -ret)
        elif ret != 0:
            print >> sys.stderr, '%s returned %d' % (argv, ret)
        else:
            # normal exit
            return
    except OSError, e:
        print >> sys.stderr, '%s execution failed: %s' % (argv[0], e)

    # show error messages before exiting
    raw_input('Type <Return> to exit.')

from termios import INLCR, ICRNL, IXON, IXOFF, IXANY,   \
        OPOST,                                          \
        ECHO, ECHONL, ICANON, ISIG, IEXTEN,             \
        VMIN, VTIME

def stty_raw(fd, attr):
    """Set 'fd' in raw mode."""
    attr[0] &= ~(INLCR | ICRNL | IXON | IXOFF | IXANY)
    attr[1] &= ~OPOST
    attr[3] &= ~(ECHO | ECHONL | ICANON | ISIG | IEXTEN)
    attr[6][VMIN] = 1
    attr[6][VTIME] = 0
    tcsetattr(fd, TCSADRAIN, attr)

got_sigchld = False
master_dsptch = None

def sigchld_handler(*args):
    """Handle SIGCHLD."""
    unused = args
    global got_sigchld
    got_sigchld = True

def sigwinch_handler(*args):
    """Handle SIGWINCH."""
    unused = args
    if master_dsptch is not None:
        master_dsptch.update_size()

def loop(orig_attr, stdin_fd, master_fd, slave_fd, stdin_dsptch):
    """Run the asyncore select loop."""
    try:
        msg = ''
        slave_closed = False
        try:
            while asyncore.socket_map and not got_sigchld:
                asyncore.poll()
                if stdin_dsptch.close_tty and not slave_closed:
                    slave_closed = True
                    os.close(slave_fd)
        except asyncore.ExitNow, err:
            msg = err
        if got_sigchld:
            msg = '\n[terminal emulator is terminating]'
            os.wait()
    finally:
        try:
            tcsetattr(stdin_fd, TCSADRAIN, orig_attr)
        except termios_error, err:
            msg += str(err)
        try:
            os.close(slave_fd)
            os.close(master_fd)
        except OSError:
            pass
        if msg:
            print >> sys.stderr, msg
        logging.info('========================================')

def main():
    """Main."""
    setlogger(this_pgm + '.logfile' )
    gdb_wrapper = (this_pgm == 'gdb_wrapper')

    if gdb_wrapper:
        pty_term = os.environ.get('PTY_TERM')
        logging.debug('pty_term: %s', pty_term)
        # run gdb in the new xterm terminal
        if pty_term is not None:
            spawn_gdb(*pty_term.split(':'))
            sys.exit(0)

    term = os.environ.get('TERM')
    if term is None:
        abort('The environment variable $TERM is not defined.')

    master_fd, slave_fd = pty.openpty()
    ptyname = os.ttyname(slave_fd)
    logging.info('create pty \'%s\'', ptyname)
    if gdb_wrapper:
        signal.signal(signal.SIGCHLD, sigchld_handler)
        spawn_terminal_emulator(ptyname + ':' + term, slave_fd, master_fd)

    # interconnect stdin to master_fd, and master_fd to stdout
    global master_dsptch
    stdin_fd = sys.stdin.fileno()
    stdin_dsptch = FileDispatcher(stdin_fd, enable_cmds=True)
    master_dsptch = FileDispatcher(master_fd, source=stdin_dsptch)
    FileDispatcher(sys.stdout.fileno(), source=master_dsptch, reader=False)

    # update pseudo terminal size
    master_dsptch.update_size()
    signal.signal(signal.SIGWINCH, sigwinch_handler)

    if gdb_wrapper:
        # allow for the child to start
        time.sleep(.100)
        if got_sigchld:
            abort()
    print >> sys.stderr, usage
    if not gdb_wrapper:
        print >> sys.stderr, (
            "'%s' pseudo terminal has been created.\n"
            "Set the tty for the program being debugged with the gdb commands:"
            "\n\n    'set inferior-tty %s'\n"
            "    'set environment TERM = %s'\n" % (ptyname, ptyname, term))

    # use termio from the new tty and tailor it
    orig_attr = tcgetattr(stdin_fd)
    stty_raw(stdin_fd, tcgetattr(slave_fd))

    loop(orig_attr, stdin_fd, master_fd, slave_fd, stdin_dsptch)

if __name__ == '__main__':
    try:
        main()
    except StandardError:
        traceback.print_exc()
        prompt('Type <Return> to exit.')

