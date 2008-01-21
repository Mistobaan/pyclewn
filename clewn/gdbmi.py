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

"""Contain the classes used to implement the oob commands.

The oob commands are run in sequence, in the background and at the gdb prompt.
The oob commands fetch from gdb, using gdb/mi, the information required to
maintain the state of the breakpoints table, the varobj data, ...
The instance of the Info class contains all this data.

The oob commands also perform actions such as: source the project file, update
the breakpoints and frame sign, update the varobj window.

The sequence of oob commands is sorted in alphabetical order in class OobList.
The names of the subclasses of OobCommand are chosen so that class instances
that depend on the result of the processing of other class instances, are last
in alphabetical order.

"""

import sys
import re
import inspect
import pprint

import gdb
import misc

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('mi')

# gdb commands ordered as in the gdb manual
#FRAME_CMDS = (
#    'attach', 'd', 'kill',
#    'r', 'start', 'c', 'fg', 's', 'n', 'finish', 'u', 'advance',
#    'up', 'up-silently', 'down', 'down-silently', 'f', 'select-frame'
#    'j', 'signal', 'return',
#    'source')
# All commands trigger a frame oob command. For example a plain gdb print
# command may call a debuggee function and stop at a breakpoint set
# inside this function.
FRAME_CMDS = ()

SOURCE_CMDS = (
    'r', 'start',
    'file', 'exec-file', 'core-file', 'symbol-file', 'add-symbol-file',
    'source')

# regexp
RE_DICT_LIST = r'{[^}]+}'                                                   \
               r'# a gdb list'

RE_DIRECTORIES = r'(?P<path>[^:^\n]+)'                                      \
                 r'# /path/to/foobar:$cdir:$cwd\n'

RE_FILE = r'(line|file|fullname)="([^"]+)"'                                 \
          r'# line="1",file="foobar.c",fullname="/home/xdg/foobar.c"'

RE_FRAME = r'(level|func|file|line)="([^"]+)"'                              \
           r'# frame={level="0",func="main",args=[{name="argc",value="1"},' \
           r'{name="argv",value="0xbfde84a4"}],file="foobar.c",line="12"}'

RE_SOURCES = r'(file|fullname)="([^"]+)"'                                   \
             r'# files=[{file="foobar.c",fullname="/home/xdg/foobar.c"},'   \
             r'{file="foo.c",fullname="/home/xdg/foo.c"}]'

# compile regexps
re_dict_list = re.compile(RE_DICT_LIST, re.VERBOSE)
re_directories = re.compile(RE_DIRECTORIES, re.VERBOSE)
re_file = re.compile(RE_FILE, re.VERBOSE)
re_frame = re.compile(RE_FRAME, re.VERBOSE)
re_sources = re.compile(RE_SOURCES, re.VERBOSE)

class Info(object):
    """Container for the debuggee state information.

    It includes the breakpoints table, the varobj data, etc.
    This class is named after the gdb "info" command.

    Instance attributes:
        gdb: gdb.Gdb
            the Gdb application instance
        directories: list
            list of gdb directories
        file: dict
            current gdb source attributes
        frame: dict
            gdb frame attributes
        frameloc: dict
            current frame location
        sources: list
            list of gdb sources

    """
    def __init__(self, gdb):
        self.gdb = gdb
        self.directories = []
        self.file = {}
        self.frame = {}
        self.frameloc = {}
        self.sources = []

    def frame_sign(self):
        """Update the frame sign."""
        if self.frame and isinstance(self.frame, dict):
            try:
                fullname = self.file['fullname']
                line = int(self.frame['line'])
            except KeyError:
                debug('key error in Info.frame dictionary')
            except ValueError:
                error('not an integer in Info.frame["line"]')
            else:
                frameloc = {'pathname':fullname, 'lnum':line}
                # do it only when frame location has changed
                if self.frameloc != frameloc:
                    self.gdb.show_frame(**frameloc)
                    self.frameloc = frameloc
                return
        self.gdb.show_frame()
        self.frameloc = {}

    def __repr__(self):
        return pprint.pformat(self.__dict__)

class Result(dict):
    """Storage for Command objects whose command has been sent to gdb.

    A dictionary: {token:command}

    Instance attributes:
        token: str
            gdb/mi token number; range 100..199

    """

    def __init__(self):
        self.token = 100

    def add(self, command):
        """Add a command object to the dictionary."""
        assert isinstance(command, Command)
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

class OobList(list):
    """List of instances of all OobCommand subclasses."""

    def __init__(self, gdb):
        """Build the OobCommand list."""
        for clss in sys.modules[self.__module__].__dict__.values():
            if inspect.isclass(clss) and issubclass(clss, OobCommand):
                try:
                    obj = clss(gdb)
                except AssertionError:
                    # skip abstract classes
                    pass
                else:
                    self.append(obj)
        self.sort()

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

class OobCommand(Command):
    """Base abstract class for oob commands.

    All subclasses of OobCommand that are abstract classes, must raise an
    AssertionError in their constructor.

    Instance attributes:
        mi: bool
            True when the gdb command is a mi command
        gdb_cmd: str
            new line terminated command to send to gdb
        info_attribute: str
            gdb.info attribute name, this is where the result of the
            command is stored, after parsing the result
        prefix: str
            prefix in the result or stream_record string
        regexp: a compiled regular expression
            gdb.info.info_attribute is set with list of regexp groups tuples
        gdblist: bool
            True when the result is a gdb list
        action: str
            optional: not present in all subclasses
            name of the gdb.info method that is called after parsing the result
        trigger: tuple
            list of commands that trigger the reset of the info_attribute and
            subsequently, the invocation of sendcmd(); an empty tuple triggers
            a notification on the processing of any command
        trigger_prefix: set
            set of the trigger command prefixes built from the trigger list
            and the list of gdb commands

    """

    def __init__(self, gdb):
        Command.__init__(self, gdb)
        assert self.__class__ is not OobCommand
        assert hasattr(self, 'gdb_cmd') and isinstance(self.gdb_cmd, str)
        self.mi = not self.gdb_cmd.startswith('-interpreter-exec console')
        assert hasattr(self, 'info_attribute')              \
                and isinstance(self.info_attribute, str)    \
                and hasattr(self.gdb.info, self.info_attribute)
        assert hasattr(self, 'prefix')                      \
                and isinstance(self.prefix, str)
        assert hasattr(self, 'regexp')                      \
                and hasattr(self.regexp, 'findall')
        assert hasattr(self, 'gdblist')                     \
                and isinstance(self.gdblist, bool)
        if hasattr(self, 'action'):
            assert hasattr(self.gdb.info, self.action)
        assert hasattr(self, 'trigger')                     \
                and isinstance(self.trigger, tuple)

        # build prefix list that triggers the command after being notified
        keys = list(set(self.gdb.cmds.keys()).difference(set(self.trigger)))
        self.trigger_prefix = set([misc.smallpref_inlist(x, keys)
                                                for x in self.trigger])

    def notify(self, cmd):
        """Notify of the current command being processed by pyclewn.

        Set the info attribute to an empty list when the command matches one
        of the commands in the trigger list. When the trigger list is empty,
        do it for all commands.

        """
        if not self.trigger or          \
                misc.any([cmd.startswith(x) for x in self.trigger_prefix]):
            setattr(self.gdb.info, self.info_attribute, [])

    def sendcmd(self):
        """Send the gdb command if the info attribute is empty.

        Return True when the command was sent, False otherwise.

        """
        if not getattr(self.gdb.info, self.info_attribute):
            self.send(self.gdb_cmd)
            return True
        return False

    def parse(self, string):
        """Parse a string with the regexp after removing prefix.

        When successful, set the info_attribute.

        """
        try:
            remain = string[string.index(self.prefix) + len(self.prefix):]
        except ValueError:
            debug('bad prefix in oob parsing of "%s",'
                    ' requested prefix: "%s"', string.strip(), self.prefix)
        else:
            if self.gdblist:
                # a list of dictionaries
                parsed = [dict(self.regexp.findall(item))
                                for item in re_dict_list.findall(remain)]
            else:
                parsed = self.regexp.findall(remain)
                if parsed                                   \
                        and isinstance(parsed[0], tuple)    \
                        and len(parsed[0]) == 2:
                    # a dictionary
                    parsed = dict(parsed)
            if parsed:
                setattr(self.gdb.info, self.info_attribute, parsed)
            else:
                debug('no regexp match for "%s"', remain)

    def handle_result(self, result):
        """Process the result of the mi command."""
        if self.mi:
            self.parse(result)
            # call the gdb.info method
            if hasattr(self, 'action'):
                getattr(self.gdb.info, self.action)()

    def handle_strrecord(self, stream_record):
        """Process the stream records output by the cli command."""
        if not self.mi:
            self.parse(stream_record)

# instantiate the OobCommand subclasses
# listed in alphabetic order to remind they are run in alphabetic order
Directories =    \
    type('Directories', (OobCommand,),
            {
                'gdb_cmd': '-interpreter-exec console "show directories"\n',
                'info_attribute': 'directories',
                'prefix': 'Source directories searched: ',
                'regexp': re_directories,
                'gdblist': False,
                'trigger': ('directory', 'source'),
            })

File =    \
    type('File', (OobCommand,),
            {
                'gdb_cmd': '-file-list-exec-source-file\n',
                'info_attribute': 'file',
                'prefix': 'done,',
                'regexp': re_file,
                'gdblist': False,
                'trigger': FRAME_CMDS,
            })

# Frame depends on, and is after File
Frame =    \
    type('Frame', (OobCommand,),
            {
                'gdb_cmd': 'frame\n',
                'info_attribute': 'frame',
                'prefix': 'done,',
                'regexp': re_frame,
                'gdblist': False,
                'action': 'frame_sign',
                'trigger': FRAME_CMDS,
            })

Sources =   \
    type('Sources', (OobCommand,),
            {
                'gdb_cmd': '-file-list-exec-source-files\n',
                'info_attribute': 'sources',
                'prefix': 'done,',
                'regexp': re_sources,
                'gdblist': True,
                'trigger': SOURCE_CMDS,
            })

