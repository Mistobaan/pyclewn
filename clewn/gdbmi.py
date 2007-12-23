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
# $Id: gdbmi.py 204 2007-12-21 20:55:44Z xavier $

"""Contain the classes used to implement the oob commands.

The oob commands are run in sequence, in the background and at the gdb prompt.
The oob commands fetch from gdb, using gdb/mi, the infomation required to
maintain the state of the breakpoints table, the varobj data, ...
The instance of the Info class contains all this data.

The sequence of oob commands is sorted in alphabetical order in class Mi. The
names of the subclasses of MiCommand are chosen so that class instances that
depend on the result of the processing of other class instances, are last in
alphabetical order.

"""

import sys
import inspect

import gdb
import misc

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('mi')

class Info(object):
    """Container for the debuggee state information.

    This includes the breakpoints table, the varobj data, ...

    """

    pass

class Result(dict):
    """Storage for Command objects whose command has been sent to gdb.

    A dictionary: {token:command}

    """

    def __init__(self):
        self.token = 100

    def add(self, command):
        """Add a command object to the dictionary."""
        t = str(self.token)
        if self.has_key(t):
            error('token "%s" already exists as an expected pending result', t)
        self[t] = command
        self.token = (self.token + 1) % 100 + 100
        return t

    def remove(self, token):
        """Remove a command object from the dictionary and return the object."""
        if not self.has_key(token):
            error('no token "%s" as an expected pending result', token)
            return None
        command = self[token]
        del self[token]
        return command

class Mi(object):
    """The list of instances of all MiCommand subclasses.

    An instance of Mi is a callable that returns an iterator over this list.

    """

    def __init__(self, gdb):
        """Instantiate and build the MiCommand list."""
        self.l = []
        for clss in sys.modules[self.__module__].__dict__.values():
            if inspect.isclass(clss)                \
                    and issubclass(clss, MiCommand) \
                    and clss is not MiCommand:
                self.l.append(clss(gdb))
        self.l.sort()

    def __call__(self):
        for e in self.l:
            yield e

class Command(object):
    """Abstract class to send gdb command and process the result.

    Instance attributes:
        gdb: Gdb
            the Gdb instance

    """

    def __init__(self, gdb):
        self.gdb = gdb

    def sendcmd(self):
        """Send a gdb command."""
        raise NotImplementedError('must be implemented in subclass')

    def handle_result(self, result):
        """Process the result of the gdb command."""
        raise NotImplementedError('must be implemented in subclass')

    def handle_strrecord(self, stream_record):
        """Process the stream records output by the command."""
        raise NotImplementedError('must be implemented in subclass')

    def send(self, fmt, *args):
        """Send the command and add oneself to the expected pending results."""
        token = self.gdb.results.add(self)
        if args:
            fmt = fmt % args
        self.gdb.write(token + fmt)

class CliCommand(Command):
    """All cli commands."""

    def sendcmd(self, cmd):
        """Send a cli command."""
        if not self.gdb.gotprmpt or self.gdb.oob is not None:
            self.gdb.console_print(
                    "gdb busy: command discarded, please retry\n")
            return False

        self.gdb.gotprmpt = False
        self.send('-interpreter-exec console %s\n', misc.quote(cmd))
        return True

    def handle_result(self, line):
        """Ignore the result."""
        pass

    def handle_strrecord(self, stream_record):
        """Process the stream records output by the command."""
        self.gdb.console_print(stream_record)

class CompleteBreakCommand(CliCommand):
    """CliCommand sent to get the symbols completion list."""

    def sendcmd(self):
        if not CliCommand.sendcmd(self, 'complete break '):
            self.handle_strrecord('')

    def handle_strrecord(self, stream_record):
        f_clist = f_ack = None
        try:
            if not stream_record:
                f_ack = open(self.gdb.globaal.f_ack.name, 'w')
                f_ack.write('Nok\n')
                self.gdb.console_print(
                        'Break and clear completion not changed.\n')
            else:
                invalid = 0
                f_clist = open(self.gdb.globaal.f_clist.name, 'w')
                completion_list = stream_record.splitlines()
                for result in completion_list:
                    matchobj = gdb.re_completion.match(result)
                    if matchobj:
                        arg = matchobj.group('arg')
                        rest = matchobj.group('rest')
                        if not rest:
                            f_clist.write('%s\n' % arg)
                        else:
                            invalid += 1
                            warning('invalid symbol completion: %s', result)
                    else:
                        error('invalid symbol completion: %s', result)
                        break
                else:
                    f_ack = open(self.gdb.globaal.f_ack.name, 'w')
                    f_ack.write('Ok\n')
                    info('%d symbols fetched for break and clear completion',
                            len(completion_list) - invalid)
        finally:
            if f_clist:
                f_clist.close()
            if f_ack:
                f_ack.close()
            else:
                self.gdb.console_print('Failed to fetch symbols completion.\n')

class MiCommand(Command):
    """Abstract class for mi commands."""
    pass

class SourceFiles(MiCommand):
    """List the source files for the current executable."""

    def sendcmd(self):
        self.send('-file-list-exec-source-files\n')

    def handle_result(self, result):
        pass # XXX

    def handle_strrecord(self, stream_record):
        pass

