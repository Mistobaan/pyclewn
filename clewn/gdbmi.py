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

"""Contain classes that implement the gdb commands.

A Gdb command may be an:
    * instance of CliCommand
    * instance of MiCommand
    * instance of ShowBalloon
The first two types trigger execution of out of band (oob) commands.

An oob command may be an:
    * instance of OobCommand
    * instance of VarObjCmd
The difference between both types is that OobCommand instances are part of a
static list in OobList, while VarObjCmd instances are pushed into this list
dynamically.

The oob commands fetch from gdb, using gdb/mi, the information required to
maintain the state of the breakpoints table, the varobj data, ...
The instance of the Info class contains all this data.

The oob commands also perform actions such as: source the project file, update
the breakpoints and frame sign, create/delete/update the varobj objects.

The sequence of instances of OobCommand commands is sorted in alphabetical order
in class OobList.  The names of the subclasses of OobCommand are chosen so that
class instances that depend on the result of the processing of other class
instances, are last in alphabetical order.

"""

import sys
import os.path
import re
import inspect
import pprint
import cStringIO
from collections import deque

import gdb
import misc
from misc import (
        any as _any,
        quote as _quote,
        parse_keyval as _parse_keyval,
        )

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('mi')

VAROBJ_FMT = '%%(name)-%ds: (%%(type)-%ds) %%(exp)-%ds %%(chged)s %%(value)s\n'

# beakpoint commands are also triggered on a frame event
BREAKPOINT_CMDS = (
    'b', 'tbreak', 'hbreak', 'thbreak', 'rbreak',
    'clear', 'delete',
    'disable', 'enable',
    'source')

DIRECTORY_CMDS = (
    'directory',
    'source')

# frame commands are triggered on a frame event
FRAME_CMDS = ()

SOURCE_CMDS = (
    'r', 'start',
    'file', 'exec-file', 'core-file', 'symbol-file', 'add-symbol-file',
    'source')

# regexp
RE_COMPLETION = r'^break\s*(?P<sym>[\w:]*)(?P<sig>\(.*\))?(?P<rest>.*)$'    \
                r'# break symbol completion'

RE_EVALUATE = r'^done,value="(?P<value>.*)"$'                               \
              r'# result of -data-evaluate-expression'

RE_DICT_LIST = r'{[^}]+}'                                                   \
               r'# a gdb list'

RE_VARCREATE = r'(name|exp|numchild|value|type)=%s'                         \
               r'# done,name="var1",numchild="0",type="int"'

RE_VARDELETE = r'^done,ndeleted="(?P<ndeleted>\d+)"$'                       \
               r'# done,ndeleted="1"'

RE_VAREVALUATE = r'(value)=%s'                                              \
                 r'# done,value="14"'

RE_BREAKPOINTS = r'(number|type|enabled|file|line)=%s'                      \
                 r'# a breakpoint'

RE_DIRECTORIES = r'(?P<path>[^:^\n]+)'                                      \
                 r'# /path/to/foobar:$cdir:$cwd\n'

RE_FILE = r'(line|file|fullname)=%s'                                        \
          r'# line="1",file="foobar.c",fullname="/home/xdg/foobar.c"'

RE_FRAME = r'(level|func|file|line)=%s'                                     \
           r'# frame={level="0",func="main",args=[{name="argc",value="1"},' \
           r'{name="argv",value="0xbfde84a4"}],file="foobar.c",line="12"}'

RE_SOURCES = r'(file|fullname)=%s'                                          \
             r'# files=[{file="foobar.c",fullname="/home/xdg/foobar.c"},'   \
             r'{file="foo.c",fullname="/home/xdg/foo.c"}]'

RE_VARUPDATE = r'(name|in_scope)=%s'                                        \
               r'# changelist='                                             \
               r'[{name="var3.key",in_scope="true",type_changed="false"}]'

# compile regexps
re_completion = re.compile(RE_COMPLETION, re.VERBOSE)
re_evaluate = re.compile(RE_EVALUATE, re.VERBOSE)
re_dict_list = re.compile(RE_DICT_LIST, re.VERBOSE)
re_varcreate = re.compile(RE_VARCREATE % misc.QUOTED_STRING, re.VERBOSE)
re_vardelete = re.compile(RE_VARDELETE, re.VERBOSE)
re_varevaluate = re.compile(RE_VAREVALUATE % misc.QUOTED_STRING, re.VERBOSE)
re_breakpoints = re.compile(RE_BREAKPOINTS % misc.QUOTED_STRING, re.VERBOSE)
re_directories = re.compile(RE_DIRECTORIES, re.VERBOSE)
re_file = re.compile(RE_FILE % misc.QUOTED_STRING, re.VERBOSE)
re_frame = re.compile(RE_FRAME % misc.QUOTED_STRING, re.VERBOSE)
re_sources = re.compile(RE_SOURCES % misc.QUOTED_STRING, re.VERBOSE)
re_varupdate = re.compile(RE_VARUPDATE % misc.QUOTED_STRING, re.VERBOSE)

def fullname(name, file):
    """Return 'fullname' value, matching name in the file dictionary."""
    try:
        if file and file['file'] == name:
            return file['fullname']
    except KeyError:
        pass
    return ''

class VarObjList(dict):
    """A dictionary of {name:VarObj instance}."""

    def collect(self, parents, lnum, stream, indent=0):
        if not self: return
        # follow positional parameters in VAROBJ_FMT
        tab = [(len(x['name']), len(x['type']), len(x['exp']))
                                            for x in self.values()]
        tab = (max([x[0] for x in tab]),
                        max([x[1] for x in tab]),
                        max([x[2] for x in tab]))
        for name in sorted(self.keys()):
            self[name].collect(parents, lnum, stream, indent, tab)

class RootVarObj(object):
    """The root of the tree of varobj objects.

    Instance attributes:
        root: VarObjList
            the root of all varobj objects
        parents: dict
            dictionary {lnum:varobj parent}
        dirty: boolean
            True when there is a change in the varobj objects
        str_content: str
            string reprentation of the varobj objects

    """

    def __init__(self):
        self.root = VarObjList()
        self.parents = {}
        self.dirty = False
        self.str_content = ''

    def leaf(self, childname):
        """Return childname VarObj and the VarObjList of the parent of childname.

        'childname' is a string with format: varNNN.child_1.child_2....

        """
        branch = childname.split('.')
        l = len(branch)
        assert l
        curlist = self.root
        try:
            for i in range(l):
                name = '.'.join(branch[:i+1])
                if i == l - 1:
                    return (curlist[name], curlist)
                curlist = curlist[name]['children']
        except KeyError:
            warning('bad key: "%s", cannot find "%s" varobj'
                                                % (name, childname))
        return (None, None)

    def collect(self):
        """Return the string representation of the varobj objects.

        This method has the side-effect of building the parents dictionary.

        """
        if self.dirty:
            self.dirty = False
            self.parents = {}
            self.lnum = [0]
            output = cStringIO.StringIO()
            self.root.collect(self.parents, self.lnum, output)
            self.str_content = output.getvalue()
            output.close()
        return self.str_content

class VarObj(dict):
    def __init__(self, vardict={}):
        self['name'] = ''
        self['exp'] = ''
        self['type'] = ''
        self['value'] = ''
        self['in_scope'] = 'true'
        self['numchild'] = 0
        self['children'] = VarObjList()
        self.chged = True
        self.update(vardict)

    def collect(self, parents, lnum, stream, indent, tab):
        if self.chged:
            self['chged'] = '={*}'
            self.chged = False
        elif self['in_scope'] != 'true':
            self['chged'] = '={-}'
        else:
            self['chged'] = '={=}'

        lnum[0] += 1
        if self['numchild'] != '0':
            parents[lnum[0]] = self
            if self['children']:
                fold = '[-] '
            else:
                fold = '[+] '
        else:
            fold = ' *  '
        format = VAROBJ_FMT % tab
        stream.write(' ' * indent + fold + format % self)
        if self['children']:
            assert self['numchild'] != 0
            self['children'].collect(parents, lnum, stream, indent + 2)

class Info(object):
    """Container for the debuggee state information.

    It includes the breakpoints table, the varobj data, etc.
    This class is named after the gdb "info" command.

    Instance attributes:
        gdb: gdb.Gdb
            the Gdb application instance
        breakpoints: list
            list of breakpoints
        bp_dictionary: dict
            breakpoints dictionary
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
        varobj: RootVarObj
            root of the tree of varobj objects
        changelist: list
            list of changed varobjs
        setnext_dirty: boolean
            when True, set varobj to dirty on next run

    """

    def __init__(self, gdb):
        self.gdb = gdb
        self.breakpoints = []
        self.bp_dictionary = {}
        self.directories = ['$cdir', '$cwd']
        self.file = {}
        self.frame = {}
        self.frameloc = {}
        self.sources = []
        self.varobj = RootVarObj()
        self.changelist = []
        self.setnext_dirty = False
        # _root_varobj is only used for pretty printing with Cdumprepr
        self._root_varobj = self.varobj.root

    def get_fullpath(self, name):
        """Get the full path name for the file named 'name' and return it.

        If name is an absolute path, just stat it. Otherwise, add name to
        each directory in gdb source directories and stat the result.
        """

        # an absolute path name
        if os.path.isabs(name):
            if os.path.exists(name):
                return name
            else:
                # strip off the directory part and continue
                name = os.path.split(name)[1]

        if not name:
            return None

        # proceed with each directory in gdb source directories
        for dir in self.directories:
            if dir == '$cdir':
                pathname = fullname(name, self.file)
                if not pathname:
                    for file in self.sources:
                        pathname = fullname(name, file)
                        if pathname:
                            break
                    else:
                        continue # main loop
            elif dir == '$cwd':
                pathname = os.path.abspath(name)
            else:
                pathname = os.path.normpath(dir, path)

            if os.path.exists(pathname):
                return pathname

        return None

    def update_breakpoints(self):
        """Update the breakpoints."""
        # build the breakpoints dictionary
        bp_dictionary = {}
        for bp in self.breakpoints:
            if 'breakpoint' in bp['type']:
                bp_dictionary[bp['number']] = bp

        nset = set(bp_dictionary.keys())
        oldset = set(self.bp_dictionary.keys())
        # update sign status of common breakpoints
        for num in (nset & oldset):
            state = bp_dictionary[num]['enabled']
            if state != self.bp_dictionary[num]['enabled']:
                enabled = (state == 'y')
                self.gdb.update_bp(int(num), not enabled)

        # delete signs for non-existent breakpoints
        for num in (oldset - nset):
            number = int(self.bp_dictionary[num]['number'])
            self.gdb.delete_bp(number)

        # create signs for new breakpoints
        for num in (nset - oldset):
            pathname = self.get_fullpath(bp_dictionary[num]['file'])
            if pathname is not None:
                lnum = int(bp_dictionary[num]['line'])
                self.gdb.add_bp(int(num), pathname, lnum)

        self.bp_dictionary = bp_dictionary

    def update_frame(self, hide=False):
        """Update the frame sign."""
        if hide:
            self.frame = {}
        if self.frame and isinstance(self.frame, dict):
            pathname = self.get_fullpath(self.file['fullname'])
            line = int(self.frame['line'])
            if pathname is not None:
                frameloc = {'pathname':pathname, 'lnum':line}
                # do it only when frame location has changed
                if self.frameloc != frameloc:
                    self.gdb.show_frame(**frameloc)
                    self.frameloc = frameloc
                return

        # hide frame sign
        self.gdb.show_frame()
        self.frameloc = {}

    def update_changelist(self):
        for vardict in self.changelist:
            (varobj, varlist) = self.varobj.leaf(vardict['name'])
            varobj['in_scope'] = vardict['in_scope']
            self.gdb.oob_list.push(VarObjCmdEvaluate(self.gdb, varobj))
        if self.changelist:
            self.varobj.dirty = True
            self.changelist = []
            self.setnext_dirty = True
        elif self.setnext_dirty:
            self.setnext_dirty = False
            self.varobj.dirty = True

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
        # do not add an OobCommand if the dictionary contains
        # an object of the same class
        if isinstance(command, OobCommand)  \
                and _any([command.__class__ is obj.__class__
                        for obj in self.values()]):
            return None
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

class OobList(object):
    """List of instances of OobCommand subclasses.

    An instance of OobList return two different types of iterator:
        * implicit: iterator over the list of OobCommand objects
        * through the call to iterator: list of OobCommand objects
          and VarObjCmd objects

    Instance attributes:
        gdb: Gdb
            the Gdb instance
        static_list: list
            list of OobCommand objects
        running_list: list
            list of VarObjCmd objects
        fifo: deque
            fifo of OobCommand and VarObjCmd objects.
            VarObjCmd objects may be pushed into the fifo while
            the fifo iterator is being run.
    """

    def __init__(self, gdb):
        self.running_list = []
        self.fifo = None

        # build the OobCommand list
        self.static_list = []
        for clss in sys.modules[self.__module__].__dict__.values():
            if inspect.isclass(clss) and issubclass(clss, OobCommand):
                try:
                    obj = clss(gdb)
                except AssertionError:
                    # skip abstract classes
                    pass
                else:
                    self.static_list.append(obj)
        self.static_list.sort()

    def __iter__(self):
        """Return an iterator over the list of OobCommand objects."""
        return self.static_list.__iter__()

    def iterator(self):
        """Return an iterator over OobCommand and VarObjCmd objects."""
        self.fifo = deque(self.static_list + self.running_list)
        self.running_list = []
        return self

    def next(self):
        if self.fifo is not None and len(self.fifo):
            return self.fifo.popleft()
        else:
            self.fifo = None
            raise StopIteration

    def push(self, obj):
        """Push a VarObjCmd object.

        When the iterator is not running, push the object to the
        running_list (as a result of a dbgvar, delvar or foldvar command).
        """
        assert isinstance(obj, VarObjCmd)
        if self.fifo is not None:
            self.fifo.append(obj)
        else:
            self.running_list.append(obj)

class Command(object):
    """Abstract class to send gdb command and process the result.

    Instance attributes:
        gdb: Gdb
            the Gdb instance

    """

    def __init__(self, gdb):
        self.gdb = gdb

    def sendcmd(self):
        """Send a gdb command.

        Return True when the command was successfully sent.
        """

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
        if token is not None:
            if args:
                fmt = fmt % args
            self.gdb.write(token + fmt)
            return True
        return False

class CliCommand(Command):
    """All cli commands."""

    def sendcmd(self, cmd):
        """Send a cli command."""
        if not self.gdb.gotprmpt or self.gdb.oob is not None:
            self.gdb.console_print(
                    "gdb busy: command discarded, please retry\n")
            return False

        self.gdb.gotprmpt = False
        return self.send('-interpreter-exec console %s\n', _quote(cmd))

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
            return False
        return True

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
                    matchobj = re_completion.match(result)
                    if matchobj:
                        symbol = matchobj.group('sym')
                        signature = matchobj.group('sig')
                        rest = matchobj.group('rest')
                        if symbol and not rest:
                            if signature:
                                symbol += signature
                            f_clist.write('%s\n' % symbol)
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
    """The MiCommand abstract class.

    Instance attributes:
        gdb: Gdb
            the Gdb instance
        varobj: VarObj
            the VarObj instance
        result: str
            the result of the mi command

    """

    def __init__(self, gdb, varobj):
        self.gdb = gdb
        self.varobj = varobj
        self.result = ''

    def sendcmd(self, fmt, *args):
        if self.gdb.gotprmpt and self.gdb.oob is None:
            self.result = ''
            return self.send(fmt, *args)
        return False

    def handle_strrecord(self, stream_record):
        if not self.result and stream_record:
            self.gdb.console_print(stream_record)

class VarCreateCommand(MiCommand):
    def sendcmd(self):
        return MiCommand.sendcmd(self, '-var-create - * %s\n',
                                        _quote(self.varobj['exp']))

    def handle_result(self, line):
        parsed = _parse_keyval(re_varcreate, line)
        if parsed is not None:
            rootvarobj = self.gdb.info.varobj
            varobj = self.varobj
            varobj.update(parsed)
            try:
                rootvarobj.root[varobj['name']] = varobj
                rootvarobj.dirty = True
                self.result = line
            except KeyError:
                error('in varobj creation of %s', str(parsed))

class VarDeleteCommand(MiCommand):
    def sendcmd(self):
        return MiCommand.sendcmd(self, '-var-delete %s\n',
                                            self.varobj['name'])

    def handle_result(self, line):
        matchobj = re_vardelete.match(line)
        if matchobj:
            self.result = matchobj.group('ndeleted')
            if self.result:
                name = self.varobj['name']
                rootvarobj = self.gdb.info.varobj
                (varobj, varlist) = rootvarobj.leaf(name)
                del varlist[name]
                rootvarobj.dirty = True
                self.gdb.console_print(
                            '%s watched variables have been deleted\n',
                                                            self.result)

class ListChildrenCommand(MiCommand):
    def sendcmd(self):
        return MiCommand.sendcmd(self, '-var-list-children --all-values %s\n',
                                                        self.varobj['name'])

    def handle_result(self, line):
        varlist = [VarObj(x) for x in
                        [_parse_keyval(re_varcreate, map)
                            for map in re_dict_list.findall(line)]
                                                    if x is not None]
        for varobj in varlist:
            self.varobj['children'][varobj['name']] = varobj
        self.gdb.info.varobj.dirty = True

class ShowBalloon(Command):
    """The ShowBalloon command.

    Instance attributes:
        gdb: Gdb
            the Gdb instance
        text: str
            the selected text under the mouse as an expression to evaluate
        result: str
            the result of the mi command

    """

    def __init__(self, gdb, text):
        self.gdb = gdb
        self.text = text
        self.result = ''

    def sendcmd(self):
        if self.gdb.gotprmpt and self.gdb.oob is None:
            self.result = ''
            return self.send('-data-evaluate-expression %s\n',
                                            _quote(self.text))
        return False

    def handle_result(self, line):
        matchobj = re_evaluate.match(line)
        if matchobj:
            self.result = matchobj.group('value')
            if self.result:
                self.gdb.show_balloon('%s = "%s"' % (self.text, self.result))

    def handle_strrecord(self, stream_record):
        if not self.result and stream_record:
            self.gdb.show_balloon(stream_record)

class VarObjCmd(Command):
    """The VarObjCmd abstract class.

    Instance attributes:
        gdb: Gdb
            the Gdb instance
        varobj: VarObj
            the VarObj instance
        result: str
            the result of the mi command

    """

    def __init__(self, gdb, varobj):
        self.gdb = gdb
        self.varobj = varobj
        self.result = ''

    def handle_strrecord(self, stream_record):
        if not self.result and stream_record:
            self.gdb.console_print(stream_record)

class VarObjCmdEvaluate(VarObjCmd):
    """The VarObjCmdEvaluate class."""

    def sendcmd(self):
        name = self.varobj['name']
        if not name:
            return False
        self.result = ''
        return self.send('-var-evaluate-expression %s\n', name)

    def handle_result(self, line):
        parsed = _parse_keyval(re_varevaluate, line)
        if parsed is not None:
            self.result = line
            value = parsed['value']
            if value != self.varobj['value']:
                self.varobj.chged = True
                self.varobj['value'] = value

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
        trigger: boolean
            when True, invoke sendcmd()
        trigger_list: tuple
            list of commands that trigger the invocation of sendcmd()
        trigger_prefix: set
            set of the trigger_list command prefixes built from the
            trigger_list and the list of gdb commands
        frame_trigger: boolean
            True when a frame event triggers the oob command

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
        assert hasattr(self, 'trigger_list')                \
                and isinstance(self.trigger_list, tuple)
        assert hasattr(self, 'frame_trigger')               \
                and isinstance(self.frame_trigger, bool)
        self.trigger = False

        # build prefix list that triggers the command after being notified
        keys = list(set(self.gdb.cmds.keys()).difference(set(self.trigger_list)))
        self.trigger_prefix = set([misc.smallpref_inlist(x, keys)
                                                for x in self.trigger_list])

    def notify(self, cmd='', frame=False):
        """Notify of the cmd being processed / of a frame event."""
        if frame and self.frame_trigger:
            self.trigger = True
        if cmd and _any([cmd.startswith(x) for x in self.trigger_prefix]):
            self.trigger = True

    def sendcmd(self):
        """Send the gdb command.

        Return True when the command was sent, False otherwise.

        """
        if self.trigger:
            setattr(self.gdb.info, self.info_attribute, [])
            self.trigger = False
            return self.send(self.gdb_cmd)
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
                parsed = [x for x in
                            [_parse_keyval(self.regexp, map)
                                for map in re_dict_list.findall(remain)]
                                                        if x is not None]
            else:
                parsed = _parse_keyval(self.regexp, remain)
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
                try:
                    getattr(self.gdb.info, self.action)()
                except (KeyError, ValueError):
                    info_attribute = getattr(self.gdb.info,
                                            self.info_attribute)
                    if info_attribute:
                        error('bad format: %s', info_attribute)

    def handle_strrecord(self, stream_record):
        """Process the stream records output by the cli command."""
        if not self.mi:
            self.parse(stream_record)

# instantiate the OobCommand subclasses
# listed in alphabetic order to remind they are run in alphabetic order
Breakpoints =   \
    type('Breakpoints', (OobCommand,),
            {
                'gdb_cmd': '-break-list\n',
                'info_attribute': 'breakpoints',
                'prefix': 'done,',
                'regexp': re_breakpoints,
                'gdblist': True,
                'action': 'update_breakpoints',
                'trigger_list': BREAKPOINT_CMDS,
                'frame_trigger': True,
            })

Directories =    \
    type('Directories', (OobCommand,),
            {
                'gdb_cmd': '-interpreter-exec console "show directories"\n',
                'info_attribute': 'directories',
                'prefix': 'Source directories searched: ',
                'regexp': re_directories,
                'gdblist': False,
                'trigger_list': DIRECTORY_CMDS,
                'frame_trigger': False,
            })

File =    \
    type('File', (OobCommand,),
            {
                'gdb_cmd': '-file-list-exec-source-file\n',
                'info_attribute': 'file',
                'prefix': 'done,',
                'regexp': re_file,
                'gdblist': False,
                'trigger_list': FRAME_CMDS,
                'frame_trigger': True,
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
                'action': 'update_frame',
                'trigger_list': FRAME_CMDS,
                'frame_trigger': True,
            })

Sources =   \
    type('Sources', (OobCommand,),
            {
                'gdb_cmd': '-file-list-exec-source-files\n',
                'info_attribute': 'sources',
                'prefix': 'done,',
                'regexp': re_sources,
                'gdblist': True,
                'trigger_list': SOURCE_CMDS,
                'frame_trigger': False,
            })

VarUpdate =    \
    type('VarUpdate', (OobCommand,),
            {
                'gdb_cmd': '-var-update *\n',
                'info_attribute': 'changelist',
                'prefix': 'done,',
                'regexp': re_varupdate,
                'gdblist': True,
                'action': 'update_changelist',
                'trigger_list': FRAME_CMDS,
                'frame_trigger': True,
            })

