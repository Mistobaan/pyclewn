#! /usr/bin/env python
# vi:set ts=8 sts=4 sw=4 et tw=80:
"""
Create a pseudo terminal to be used as the controlling terminal of a process
debugged by gdb.

When the name of this module is 'gdb_wrapper.py', spawn an xterm with a gdb
instance that is setup to use the current terminal as its inferior tty. The
command line arguments of 'gdb_wrapper' are passed unchanged to gdb.
"""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from io import open

import os
import sys
import signal
import fcntl
import time
import asyncore
import subprocess
import traceback
import logging

import clewn.misc as misc
import clewn.tty as tty
import clewn.debugger as debugger

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('pty')

debug = False
this_pgm = os.path.basename(sys.argv[0]).rsplit('.py', 1)[0]
usage = ("""'%s' two characters sequence commands:
    'C-a q' exit immediately
    'C-a c' close the slave pseudo terminal and exit after the inferior has
            terminated
    'C-a a' send a \'C-a\' character
""" % this_pgm)

def setlogger(filename):
    """Set the logging file handler."""
    if debug:
        root = logging.getLogger()
        hdlr_file = logging.FileHandler(filename)
        fmt = logging.Formatter('%(name)-4s %(levelname)-7s %(message)s')
        hdlr_file.setFormatter(fmt)
        root.addHandler(hdlr_file)
        root.setLevel(logging.DEBUG)

def abort(msg=''):
    """Abort after printing 'msg'."""
    if msg:
        print(msg, file=sys.stderr)
    sys.exit(1)

def prompt(msg):
    """Prompt for user input."""
    # remove non-blocking mode
    fd = sys.stdin.fileno()
    flags = fcntl.fcntl(fd, fcntl.F_GETFL, 0)
    flags = flags & ~os.O_NONBLOCK
    fcntl.fcntl(fd, fcntl.F_SETFL, flags)
    return input(msg)

def spawn_terminal_emulator(pty_term, gdb_pty):
    """Run ourself in xterm to monitor gdb exit status."""
    argv = ['xterm', '-e', 'python']
    argv.extend(sys.argv)
    debug('spawning: \'%s\'', argv)
    pid = os.fork()
    if pid == 0:
        os.close(gdb_pty.slave_fd)
        os.close(gdb_pty.master_fd)
        try:
            os.environ['PTY_TERM'] = pty_term
            os.execvp(argv[0], argv)
        except OSError as err:
            msg = 'argv: \'%s\'\n' % argv
            msg += 'Spawing \'%s\' failed: %s' % (argv[0], err)
            abort(msg)
    return pid

def spawn_gdb(ptyname, term):
    """Spawn gdb."""
    argv = ['gdb', '-tty', ptyname, '--eval-command',
                        'set environment TERM = %s' % term]
    argv.extend(sys.argv[1:])
    debug('spawn_gdb: \'%s\'', argv)

    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        ret = subprocess.call(argv)
        if ret < 0:
            print('%s was terminated by signal %d' % (argv[0], -ret),
                                                        file=sys.stderr)
        elif ret != 0:
            print('%s returned %d' % (argv, ret), file=sys.stderr)
        else:
            # normal exit
            return
    except OSError as e:
        print('%s execution failed: %s' % (argv[0], e), file=sys.stderr)

    # show error messages before exiting
    input('Type <Return> to exit.')

got_sigchld = False

def sigchld_handler(*args):
    """Handle SIGCHLD."""
    global got_sigchld
    got_sigchld = True

def loop(gdb_pty):
    """Run the asyncore select loop."""
    try:
        msg = ''
        slave_closed = False
        gdb_pty.stty_raw()
        try:
            while asyncore.socket_map and not got_sigchld:
                asyncore.poll(timeout=debugger.LOOP_TIMEOUT)
                if gdb_pty.stdin_dsptch.close_tty and not slave_closed:
                    slave_closed = True
                    os.close(gdb_pty.slave_fd)
        except asyncore.ExitNow as err:
            msg = err
        if got_sigchld:
            msg = '\n[terminal emulator is terminating]'
            os.wait()
    finally:
        gdb_pty.close()
        if msg:
            print(msg, file=sys.stderr)
        info('========================================')

def main():
    """Main."""
    setlogger(this_pgm + '.logfile' )
    gdb_wrapper = (this_pgm == 'gdb_wrapper')

    if gdb_wrapper:
        pty_term = os.environ.get('PTY_TERM')
        debug('pty_term: %s', pty_term)
        # run gdb in the new xterm terminal
        if pty_term is not None:
            spawn_gdb(*pty_term.split(':'))
            sys.exit(0)

    term = os.environ.get('TERM')
    if term is None:
        abort('The environment variable $TERM is not defined.')

    gdb_pty = tty.GdbInferiorPty()
    gdb_pty.interconnect_pty(enable_cmds=True)
    ptyname = gdb_pty.ptyname

    if gdb_wrapper:
        signal.signal(signal.SIGCHLD, sigchld_handler)
        spawn_terminal_emulator(ptyname + ':' + term, gdb_pty)
        # allow for the child to start
        time.sleep(.100)
        if got_sigchld:
            abort()

    print(usage, file=sys.stderr)
    if not gdb_wrapper:
        print('{} pseudo terminal has been created.'.format(ptyname),
                file=sys.stderr)

        gdb_commands = ('set inferior-tty {}\n'
                        'set environment TERM = {}\n'.format(ptyname, term))
        if len(sys.argv) > 1:
            with open(sys.argv[1], 'w') as f:
                f.write(gdb_commands)
        else:
            print('Set the tty for the program being debugged with the gdb'
            ' commands:\n{}'.format(gdb_commands), file=sys.stderr)

    loop(gdb_pty)

if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        prompt('Type <Return> to exit.')

