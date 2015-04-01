# vi:set ts=8 sts=4 sw=4 et tw=80:
"""
Contain classes that implement the gdb commands.

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
"""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from io import open

import sys
import os
import re
import io
import traceback
import collections
from abc import ABCMeta, abstractmethod
from collections import OrderedDict

from . import PY3, text_type, misc

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('mi')

VAROBJ_FMT = '%%(name)-%ds: (%%(type)-%ds) %%(exp)-%ds %%(chged)s %%(value)s\n'

BREAKPOINT_CMDS = ()
FILE_CMDS = ()
FRAME_CMDS = ()
THREADS_CMDS = ()
VARUPDATE_CMDS = ()

DIRECTORY_CMDS = (
    'directory',
    'source')

SOURCE_CMDS = (
    'r', 'start',
    'file', 'exec-file', 'core-file', 'symbol-file', 'add-symbol-file',
    'source')

# Need to know the list of sources to build the breakpoint full pathname.
SOURCE_CMDS_EXTRA = ('break', 'tbreak', 'hbreak', 'thbreak', 'rbreak')

PROJECT_CMDS = ('project',) + SOURCE_CMDS

# gdb objects attributes.
BREAKPOINT_ATTRIBUTES = {'number', 'type', 'disp', 'enabled', 'func', 'file',
                         'line', 'times', 'original-location', 'what'}
REQ_BREAKPOINT_ATTRIBUTES = {'number', 'type', 'enabled'}
FILE_ATTRIBUTES = {'line', 'file', 'fullname'}
FRAMECLI_ATTRIBUTES = {'level', 'func', 'file', 'line', }
FRAME_ATTRIBUTES = {'level', 'func', 'file', 'fullname', 'line', 'from',  }
REQ_FRAME_ATTRIBUTES = {'level', }
THREADS_ATTRIBUTES = {'current', 'id', 'target-id', 'name', 'state', 'core', }
SOURCES_ATTRIBUTES = {'file', 'fullname'}
VARUPDATE_ATTRIBUTES = {'name', 'in_scope'}
VARCREATE_ATTRIBUTES = {'name', 'numchild', 'type'}
VARLISTCHILDREN_ATTRIBUTES = {'name', 'exp', 'numchild', 'value', 'type'}
VAREVALUATE_ATTRIBUTES = {'value'}

def keyval_pattern(attributes, comment=''):
    """Build and return a keyval pattern string."""
    return '(' + '|'.join(attributes) + ')=' + misc.QUOTED_STRING

# regexp
RE_EVALUATE = r'^done,value="(?P<value>.*)"$'                               \
              r'# result of -data-evaluate-expression'

RE_DICT_LIST = r'{[^}]+}'                                                   \
               r'# a gdb list'

RE_VARCREATE = keyval_pattern(VARCREATE_ATTRIBUTES,
            'done,name="var1",numchild="0",type="int"')

RE_VARDELETE = r'^done,ndeleted="(?P<ndeleted>\d+)"$'                       \
               r'# done,ndeleted="1"'

RE_SETFMTVAR = r'^done,format="\w+",value="(?P<value>.*)"$'                 \
               r'# done,format="binary",value="1111001000101110110001011110"'

RE_VARLISTCHILDREN = keyval_pattern(VARLISTCHILDREN_ATTRIBUTES)

RE_VAREVALUATE = keyval_pattern(VAREVALUATE_ATTRIBUTES, 'done,value="14"')

RE_ARGS = r'\s*"(?P<args>.+)"\.'                                            \
             r'# "toto "begquot endquot" titi".'

RE_BREAKPOINTS = keyval_pattern(BREAKPOINT_ATTRIBUTES, 'a breakpoint')

RE_DIRECTORIES = r'(?P<path>[^' + os.pathsep + r'^\n]+)'                    \
                 r'# /path/to/foobar:$cdir:$cwd\n'

RE_FILE = keyval_pattern(FILE_ATTRIBUTES,
            'line="1",file="foobar.c",fullname="/home/xdg/foobar.c"')

RE_FRAMECLI = keyval_pattern(FRAMECLI_ATTRIBUTES,
            'frame={level="0",func="main",args=[{name="argc",value="1"},'
            '{name="argv",value="0xbfde84a4"}],file="foobar.c",line="12"}')
RE_FRAME = keyval_pattern(FRAME_ATTRIBUTES)

# Output of '-thread-info':
# '{id="2",target-id="Thread 0x7ffff6bd9700 (LWP # 3820)",name="python",
#   frame={level="0",addr="0x00007ffff7bcd920",func="sem_wait",args=[],
#     from="/usr/lib/libpthread.so.0"},
#   state="stopped",core="2"},
# {id="1",target-id="Thread 0x7ffff7fce700 (LWP # 3816)",name="python",
#   frame={level="0",addr="0x0000000000432e77",func="sys_getrecursionlimit",
#     args=[{name="self",value="0x7ffff70ec7d8"}],
#     file="./Python/sysmodule.c",
#     fullname="/home/xavier/src/python/cpython-hg-default/Python/sysmodule.c",
#     line="726"}
#   ,state="stopped",core="3"}],
# current-thread-id="1"]'
RE_THREADS = '({[^{]+{[^}]*args=\[[^]]*\][^}]*}[^}]*})|current-thread-id="(\d+)"'

RE_THREADS_ATTRIBUTES = keyval_pattern(THREADS_ATTRIBUTES)

RE_PGMFILE = r'\s*"(?P<debuggee>[^"]+)"\.'                                  \
             r'# "/path/to/pyclewn/testsuite/foobar".'

RE_PWD = r'"(?P<cwd>[^"]+)"# "/home/xavier/src/pyclewn_wa/trunk/pyclewn"'

RE_SOURCES = keyval_pattern(SOURCES_ATTRIBUTES,
            'files=[{file="foobar.c",fullname="/home/xdg/foobar.c"},'
            '{file="foo.c",fullname="/home/xdg/foo.c"}]')

RE_VARUPDATE = keyval_pattern(VARUPDATE_ATTRIBUTES,
            'changelist='
            '[{name="var3.key",in_scope="true",type_changed="false"}]')

# compile regexps
re_evaluate = re.compile(RE_EVALUATE, re.VERBOSE)
re_dict_list = re.compile(RE_DICT_LIST, re.VERBOSE)
re_varcreate = re.compile(RE_VARCREATE, re.VERBOSE)
re_vardelete = re.compile(RE_VARDELETE, re.VERBOSE)
re_setfmtvar = re.compile(RE_SETFMTVAR, re.VERBOSE)
re_varlistchildren = re.compile(RE_VARLISTCHILDREN, re.VERBOSE)
re_varevaluate = re.compile(RE_VAREVALUATE, re.VERBOSE)
re_args = re.compile(RE_ARGS, re.VERBOSE)
re_breakpoints = re.compile(RE_BREAKPOINTS, re.VERBOSE)
re_directories = re.compile(RE_DIRECTORIES, re.VERBOSE)
re_file = re.compile(RE_FILE, re.VERBOSE)
re_framecli = re.compile(RE_FRAMECLI, re.VERBOSE)
re_frame = re.compile(RE_FRAME, re.VERBOSE)
re_threads = re.compile(RE_THREADS)
re_threads_attributes = re.compile(RE_THREADS_ATTRIBUTES)
re_pgmfile = re.compile(RE_PGMFILE, re.VERBOSE)
re_pwd = re.compile(RE_PWD, re.VERBOSE)
re_sources = re.compile(RE_SOURCES, re.VERBOSE)
re_varupdate = re.compile(RE_VARUPDATE, re.VERBOSE)

def get_pathname(name, source):
    """Return a valid path name, matching name in the source dictionary."""
    if source:
        pathname = source['fullname'] if source['file'] == name else ''
        if pathname and os.path.exists(pathname):
            return pathname

def fix_bp_attributes(bp):
    if 'line' not in bp or 'file' not in bp:
        # When file/line is missing (a template function), use the
        # original-location.
        if 'original-location' in bp:
            oloc = bp['original-location']
            if ':' in oloc:
                fn, lno = oloc.rsplit(':', 1)
                bp['file'] = fn.strip(misc.DOUBLEQUOTE)
                bp['line'] = lno
            elif 'func' not in bp:
                bp['func'] = oloc

class VarObjList(OrderedDict):
    """A dictionary of {name:VarObj instance}."""

    def collect(self, parents, lnum, stream, indent=0):
        """Collect all varobj children data.

        Return True when the Variables buffer must be set as dirty
        for the next update run (for syntax highlighting).

        """
        if not self:
            return False

        # follow positional parameters in VAROBJ_FMT
        table = [(len(x['name']), len(x['type']), len(x['exp']))
                                            for x in self.values()]
        tab = (max([x[0] for x in table]),
                        max([x[1] for x in table]),
                        max([x[2] for x in table]))

        dirty = False
        for name in self.keys():
            status = self[name].collect(parents, lnum, stream, indent, tab)
            if status:
                dirty = True
        return dirty

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
            string representation of the varobj objects

    """

    def __init__(self):
        self.root = VarObjList()
        self.parents = {}
        self.dirty = False
        self.str_content = ''

    def clear(self):
        """Clear all varobj elements.

        Return False when there were no varobj elements to remove.

        """
        if not self.root:
            self.dirty = False
        else:
            self.root.clear()
            self.parents = {}
            self.dirty = True
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
            lnum = [0]
            output = io.StringIO()
            self.dirty = self.root.collect(self.parents, lnum, output)
            self.str_content = output.getvalue()
            output.close()
        return self.str_content

class VarObj(dict):
    """A gdb/mi varobj object."""

    def __init__(self, vardict={}):
        self['name'] = ''
        self['exp'] = ''
        self['type'] = ''
        self['value'] = ''
        self['chged'] = '={=}'
        self['in_scope'] = 'true'
        self['numchild'] = 0
        self['children'] = VarObjList()
        self.chged = True
        self.update(vardict)

    def collect(self, parents, lnum, stream, indent, tab):
        """Collect varobj data."""
        dirty = False

        if self.chged:
            self['chged'] = '={*}'
            self.chged = False
            dirty = True
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
            status = self['children'].collect(parents, lnum, stream, indent + 2)
            dirty = dirty or status

        return dirty

class LooseFrame(dict):
    """Compare equal when only their 'line', 'addr' is different."""
    def __eq__(self, other):
        return set(other) == set(self) and all(other[x] == self[x]
               for x in self if x not in ('line', 'addr'))

class Info(object):
    """Container for the debuggee state information.

    It includes the breakpoints table, the varobj data, etc.
    This class is named after the gdb "info" command.

    Instance attributes:
        gdb: gdb.Gdb
            the Gdb debugger instance
        args: list
            the debuggee arguments
        breakpoints: list
            list of breakpoints, result of a previous OobGdbCommand
        bp_dictionary: dict
            breakpoints dictionary, with bp number as key
        bp_dirty: boolean
            True when the breakpoints have changed
        cwd: list
            current working directory
        debuggee: list
            program file
        directories: list
            list of gdb directories
        file: dict
            current gdb source attributes
        frame: dict
            gdb frame attributes
        prev_frame: dict
            previous frame
        frame_prefix: str
            completion prefix for the 'frame' command
        backtrace: dict
            the backtrace
        backtrace_dirty: boolean
            True when the backtrace has changed
        threads_list: list
            list of the gdb representation of a thread
        threads: dict
            the threads
        threads_dirty: boolean
            True when the threads have changed
        sources: list
            list of gdb sources
        varobj: RootVarObj
            root of the tree of varobj objects
        changelist: list
            list of changed varobjs

    """

    def __init__(self, gdb):
        self.gdb = gdb
        self.args = []
        self.breakpoints = []
        self.bp_dictionary = {}
        self.bp_dirty = False
        self.cwd = []
        self.debuggee = []
        self.directories = ['$cdir', '$cwd']
        self.file = {}
        self.frame = {}
        self.prev_frame = {}
        self.frame_prefix = ''
        self.backtrace = {}
        self.backtrace_dirty = False
        self.threads_list = []
        self.threads = {}
        self.threads_dirty = False
        self.sources = []
        self.varobj = RootVarObj()
        self.changelist = []
        # _root_varobj is only used for pretty printing with Cdumprepr
        self._root_varobj = self.varobj.root

    def get_fullpath(self, name):
        """Get the full path name for the file named 'name' and return it.

        If name is an absolute path, just stat it. Otherwise, add name to
        each directory in gdb source directories and stat the result.
        """

        # An absolute path name.
        if os.path.isabs(name):
            if os.path.exists(name):
                return name
            else:
                # Strip off the directory part and continue.
                name = os.path.split(name)[1]

        if not name:
            return None

        # Proceed with each directory in gdb source directories.
        for dirname in self.directories:
            if dirname == '$cdir':
                pathname = get_pathname(name, self.file)
                if pathname:
                    return pathname
                for source in self.sources:
                    pathname = get_pathname(name, source)
                    if pathname:
                        return pathname
            elif dirname == '$cwd':
                pathname = os.path.abspath(name)
                if os.path.exists(pathname):
                    return pathname
            else:
                pathname = os.path.join(dirname, name)
                if os.path.exists(pathname):
                    return pathname

    def collect_breakpoints(self):
        self.bp_dirty = False
        lines = []
        for num in sorted(self.bp_dictionary.keys()):
            bp = self.bp_dictionary[num]
            line = (('%-4s' % num) +
                    (' %(type)-15s %(enabled)-3s %(times)-5s '
                     '%(disp)-6s' % bp))
            if 'watchpoint' in bp['type']:
                if 'what' in bp:
                    line += bp['what']
            else:
                if 'func' in bp:
                    line += ' in %(func)s' % bp
                if 'line' in bp and 'file' in bp:
                    lnum = bp['line']
                    fname = bp['file']
                    line += ' at %s:%s' % (fname, lnum)
                    pathname = self.get_fullpath(fname)
                    if pathname is not None:
                        line += ' <%s>' % pathname
            lines.append(line)

        if lines:
            lines.insert(0, 'Num  Type            Enb Hit   Disp   What')
            return '\n'.join(lines) + '\n'
        else:
            return ''

    def update_breakpoints(self, cmd=''):
        """Update the breakpoints."""
        # Build the breakpoints dictionary.
        bp_dictionary = {}
        for bp in self.breakpoints:
            if (('breakpoint' in bp['type']
                    # Exclude 'throw' and 'catch 'catchpoints (they are typed by
                    # gdb as 'breakpoint' instead of 'catchpoint').
                    and not
                        ('what' in bp and 'exception' in bp['what'])) or
                    'watchpoint' in bp['type']):
                bp_dictionary[int(bp['number'])] = bp

        nset = set(bp_dictionary.keys())
        oldset = set(self.bp_dictionary.keys())
        # Update the state of common breakpoints.
        for num in (nset & oldset):
            bp = bp_dictionary[num]
            old_bp = self.bp_dictionary[num]
            if 'watchpoint' not in bp['type']:
                fix_bp_attributes(bp)
            state = bp['enabled']
            if state != old_bp['enabled']:
                self.bp_dirty = True
                if ('watchpoint' not in bp['type'] and 'line' in old_bp and
                        'file' in old_bp):
                    enabled = (state == 'y')
                    self.gdb.update_bp(num, not enabled)
            if bp['times'] != old_bp['times']:
                self.bp_dirty = True

        # Delete signs for non-existent breakpoints.
        for num in (oldset - nset):
            bp = self.bp_dictionary[num]
            if 'watchpoint' in bp['type']:
                continue
            if 'line' in bp and 'file' in bp:
                self.gdb.delete_bp(num)

        # Create signs for the new breakpoints.
        for num in sorted(nset - oldset):
            bp = bp_dictionary[num]
            if 'watchpoint' in bp['type']:
                continue
            fix_bp_attributes(bp)
            if 'line' in bp and 'file' in bp:
                pathname = self.get_fullpath(bp['file'])
                if pathname is not None:
                    lnum = int(bp['line'])
                    self.gdb.add_bp(num, pathname, lnum)

        self.bp_dictionary = bp_dictionary

        if (oldset - nset) or (nset - oldset):
            self.bp_dirty = True

    def collect_backtrace(self):
        self.backtrace_dirty = False
        flevel = self.frame.get('level')
        lines = []
        for f in self.backtrace:
            curlevel = f['level']
            line = '* #%-3s' if curlevel == flevel else '  #%-3s'
            line = line % curlevel
            if 'func' in f:
                line += ' in %s' % f['func']
            elif 'from' in f:
                line += ' from %s' % f['from']
            # Do not display the line number to avoid screen blinks.
            if 'file' in f:
                fname = f['file']
                line += ' at %s' % fname
                pathname = self.get_fullpath(fname)
                if pathname is not None:
                    line += ' <%s>' % pathname
            lines.append(line)

        if lines:
            return '\n'.join(lines) + '\n'
        else:
            return ''

    def update_frame(self, cmd=''):
        """Update the frame sign."""
        self.frame = LooseFrame(self.frame)
        try:
            if self.prev_frame != self.frame:
                self.backtrace_dirty = True
            if 'line' in self.frame:
                f = self.frame
                line = int(f['line'])
                # gdb 6.4 and above.
                if 'fullname' in f:
                    fname = f['fullname']
                else:
                    fullname = self.file.get('fullname')
                    fname = f.get('file')
                    if (fname and fullname and
                            os.path.basename(fullname) == fname):
                        fname = fullname
                pathname = self.get_fullpath(fname) if fname else None
                if pathname:
                    if not self.frame_prefix:
                        keys = list(self.gdb.cmds.keys())
                        keys.remove('frame')
                        self.frame_prefix = misc.smallpref_inlist('frame',
                                                                   keys)
                    if (self.prev_frame != self.frame or
                                cmd.startswith(self.frame_prefix)):
                        self.gdb.show_frame(pathname, line)
                    return

            self.hide_frame()
        finally:
            self.prev_frame = self.frame

    def hide_frame(self):
        if self.prev_frame:
            self.prev_frame = {}
            self.backtrace_dirty = True
            self.backtrace = {}
        self.gdb.show_frame()

    def collect_threads(self):
        self.threads_dirty = False
        lines = []
        for id in sorted(self.threads):
            thread = self.threads[id]
            if 'name' not in thread:
                thread['name'] = ''
            line = ('%(current)s %(id)-3s %(name)-16s %(state)-7s'
                    ' %(target-id)s' % thread)
            if 'frame' in thread:
                f = thread['frame']
                if 'func' in f:
                    line += ' in %s' % f['func']
                elif 'from' in f:
                    line += ' from %s' % f['from']
                # Do not display the line number to avoid screen blinks.
                if 'file' in f:
                    line += ' at %s' % f['file']
            lines.append(line)

        if lines:
            lines.insert(0, '  Id  Name             State   Info')
            return '\n'.join(lines) + '\n'
        else:
            return ''

    def update_threads(self, cmd=''):
        threads = {}
        current = None
        # Parse the threads_list and build a new threads dictionary.
        for sthread, current in self.threads_list:
            if not sthread:
                continue
            sframe = ''
            lthread = sthread[1:-1].split('frame={', 1)
            if len(lthread) == 2:
                remain = lthread[1].rsplit('}', 1)
                sthread = lthread[0].strip(' ,') + remain[1]
                sframe = remain[0]
            else:
                sthread = lthread[0]
            thread = misc.parse_keyval(re_threads_attributes, sthread)
            if 'current' not in thread:
                thread['current'] = ' '
            if sframe:
                if self.gdb.version >= [6, 4]:
                    frame = misc.parse_keyval(re_frame, sframe)
                else:
                    frame = misc.parse_keyval(re_framecli, sframe)
                thread['frame'] = LooseFrame(frame)

            try:
                threads[int(thread['id'])] = thread
            except (ValueError, KeyError):
                error('invalid thread id %s', thread)

        if current is not None:
            try:
                threads[int(current)]['current'] = '*'
            except (ValueError, KeyError):
                error('unknown current-thread-id %s', current)

        # Check if the threads have changed.
        if threads != self.threads:
            self.threads_dirty = True
        self.threads = threads

    def update_changelist(self, cmd):
        """Process a varobj changelist event."""
        for vardict in self.changelist:
            (varobj, varlist) = self.varobj.leaf(vardict['name'])
            if varobj is not None:
                varobj['in_scope'] = vardict['in_scope']
                self.gdb.oob_list.push(VarObjCmdEvaluate(self.gdb, varobj))
        if self.changelist:
            self.varobj.dirty = True
            self.changelist = []

    def __repr__(self):
        """Return the pretty formated self dictionary."""
        return misc.pformat(self.__dict__)

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
        # do not add an OobGdbCommand if the dictionary contains
        # an object of the same class
        if isinstance(command, OobGdbCommand)  \
                and any([command.__class__ is obj.__class__
                        for obj in self.values()]):
            return None
        t = str(self.token)
        if t in self:
            error('token "%s" already exists as an expected pending result', t)
        self[t] = command
        self.token = (self.token + 1) % 100 + 100
        return t

    def remove(self, token):
        """Remove a command object from the dictionary and return the object."""
        if token not in self:
            # do not report as an error: may occur on quitting
            info('no token "%s" as an expected pending result', token)
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
            ordered list of OobCommand objects
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

        # Build the OobCommand objects list, object ordering is important.
        cmdlist = [
            Args(gdb),
            Directories(gdb),
            File(gdb),
            FrameCli(gdb),      # After File.
            Frame(gdb),
            BackTrace(gdb),     # After Frame.
            Threads(gdb),
            PgmFile(gdb),
            VarUpdate(gdb),     # Not last after gdb 7.0.
            Pwd(gdb),
            Sources(gdb),
            Breakpoints(gdb),   # After File and Sources.
            Project(gdb),
            Quit(gdb),
        ]
        cmdlist = [cmd for cmd in cmdlist if not hasattr(cmd, 'version_min')
                                            or gdb.version >= cmd.version_min]
        self.static_list = [cmd for cmd in cmdlist if not hasattr(cmd,
                            'version_max') or gdb.version <= cmd.version_max]

    def __iter__(self):
        """Return an iterator over the list of OobCommand objects."""
        return self.static_list.__iter__()

    def __len__(self):
        """Length of the OobList."""
        if self.fifo is not None:
            return len(self.fifo)
        return 0

    def iterator(self):
        """Return an iterator over OobCommand and VarObjCmd objects."""
        self.fifo = collections.deque(self.static_list + self.running_list)
        self.running_list = []
        return self

    def __next__(self):
        """Iterator next method."""
        if self.fifo is not None and len(self.fifo):
            return self.fifo.popleft()
        else:
            self.fifo = None
            raise StopIteration
    next = __next__

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
        stream_record: str
            the stream record

    """

    __metaclass__ = ABCMeta

    def __init__(self, gdb):
        self.gdb = gdb
        self.stream_record = ''

    @abstractmethod
    def handle_result(self, result):
        """Process the result of the gdb command."""

    @abstractmethod
    def handle_strrecord(self, stream_record):
        """Process the stream records output by the command."""

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

    def sendcmd(self, cmd, verbose=True):
        """Send a cli command."""
        if not self.gdb.accepting_cmd():
            if verbose:
                self.gdb.console_print(
                        "gdb busy: command discarded, please retry\n")
            return False

        self.gdb.gdb_busy = True
        self.stream_record = ''
        return self.send('-interpreter-exec console %s\n', misc.quote(cmd))

    def handle_result(self, line):
        """Handle gdb/mi result."""
        warning('CliCommand gdb/mi result: %s', line)

    def handle_strrecord(self, stream_record):
        """Process the stream records output by the command."""
        self.gdb.console_print(stream_record)
        self.stream_record = stream_record

class CliCommandNoPrompt(CliCommand):
    """The prompt is printed by one of the OobCommands."""
    pass

class CompleteCommand(CliCommand):
    """Get the gdb completion."""

    def sendcmd(self, args):
        """Send the gdb command."""
        # Set the prefix to remove from gdb answer.
        arglead = args.rsplit(None, 1)
        if len(arglead) != 2:
            # A gdb command terminated with white space(s) else a completion
            # whith an empty command such as 'C brea'.
            self.prefix = args if len(args.rstrip()) != len(args) else ''
        else:
            idx = args.rfind(arglead[1])
            self.prefix = args[:idx]

        if not CliCommand.sendcmd(self, 'complete %s' % args, verbose=False):
            with open(self.gdb.globaal.f_ack.name, 'w') as f:
                f.write('Nok\n')

    def handle_result(self, result):
        if result == 'done':
            plen = len(self.prefix)
            completion = '\n'.join(l[plen:]
                                   for l in self.stream_record.splitlines()
                                   if l.find(self.prefix) == 0)

            with open(self.gdb.globaal.f_clist.name, 'w') as f:
                f.write(completion)

            with open(self.gdb.globaal.f_ack.name, 'w') as f:
                result = 'Ok\n' if completion else 'Nok\n'
                f.write(result)

    def handle_strrecord(self, stream_record):
        self.stream_record += stream_record

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

    def docmd(self, fmt, *args):
        """Send the gdb command."""
        if not self.gdb.accepting_cmd():
            self.gdb.console_print(
                    "gdb busy: command discarded, please retry\n")
            return False

        self.gdb.gdb_busy = True
        self.result = ''
        return self.send(fmt, *args)

    def handle_strrecord(self, stream_record):
        """Process the gdb/mi stream records."""
        if not self.result and stream_record:
            self.gdb.console_print(stream_record)

class VarCreateCommand(MiCommand):
    """Create a variable object."""

    varnum = 1

    def sendcmd(self):
        """Send the gdb command."""
        return MiCommand.docmd(self, '-var-create var%d * %s\n',
                               self.varnum, misc.quote(self.varobj['exp']))

    def handle_result(self, line):
        """Process gdb/mi result."""
        VarCreateCommand.varnum += 1
        parsed = misc.parse_keyval(re_varcreate, line)
        if VARCREATE_ATTRIBUTES.issubset(parsed):
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
    """Delete the variable object and its children."""

    def sendcmd(self):
        """Send the gdb command."""
        return MiCommand.docmd(self, '-var-delete %s\n',
                                            self.varobj['name'])

    def handle_result(self, line):
        """Process gdb/mi result."""
        matchobj = re_vardelete.match(line)
        if matchobj:
            self.result = matchobj.group('ndeleted')
            if self.result:
                name = self.varobj['name']
                rootvarobj = self.gdb.info.varobj
                (varobj, varlist) = rootvarobj.leaf(name)
                if varlist is not None:
                    del varlist[name]
                    rootvarobj.dirty = True
                    self.gdb.console_print(
                                '%s watched variables have been deleted\n',
                                                                self.result)

class VarSetFormatCommand(MiCommand):
    """Set the output format of the value of the watched variable."""

    def sendcmd(self, format):
        """Send the gdb command."""
        return MiCommand.docmd(self, '-var-set-format %s %s\n',
                                        self.varobj['name'], format)

    def handle_result(self, line):
        """Process gdb/mi result."""
        matchobj = re_setfmtvar.match(line)
        if matchobj:
            self.gdb.console_print('%s = %s\n',
                        self.varobj['name'], matchobj.group('value'))

class NumChildrenCommand(MiCommand):
    """Get how many children this object has."""

    def sendcmd(self):
        """Send the gdb command."""
        return MiCommand.docmd(self, '-var-info-num-children %s\n',
                                                        self.varobj['name'])

    def handle_result(self, line):
        """Process gdb/mi result."""
        # used as a nop command by the foldvar command
        pass

# 'type' and 'value' are not always present in -var-list-children output
LIST_CHILDREN_KEYS = VARLISTCHILDREN_ATTRIBUTES.difference({'type', 'value'})
class ListChildrenCommand(MiCommand):
    """Return a list of the object's children."""

    def sendcmd(self):
        """Send the gdb command."""
        return MiCommand.docmd(self, '-var-list-children --all-values %s\n',
                                                        self.varobj['name'])

    def handle_result(self, line):
        """Process gdb/mi result."""
        varlist = [VarObj(x) for x in
                        [misc.parse_keyval(re_varlistchildren, list_element)
                            for list_element in re_dict_list.findall(line)]
                if LIST_CHILDREN_KEYS.issubset(x)]
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
        """Send the gdb command."""
        if self.gdb.accepting_cmd():
            self.result = ''
            self.gdb.gdb_busy = True
            return self.send('-data-evaluate-expression %s\n',
                                        misc.quote(self.text))
        return False

    def handle_result(self, line):
        """Process gdb/mi result."""
        matchobj = re_evaluate.match(line)
        if matchobj:
            self.result = misc.unquote(matchobj.group('value'))
            if self.result:
                self.gdb.show_balloon('%s = "%s"' % (self.text, self.result))

    def handle_strrecord(self, stream_record):
        """Process the gdb/mi stream records."""
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

    __metaclass__ = ABCMeta

    def __init__(self, gdb, varobj):
        self.gdb = gdb
        self.varobj = varobj
        self.result = ''

    def handle_strrecord(self, stream_record):
        """Process the gdb/mi stream records."""
        if not self.result and stream_record:
            self.gdb.console_print(stream_record)

    @abstractmethod
    def sendcmd(self):
        """Send the gdb command.

        Return True when the command has been sent to gdb, False otherwise.

        """

    def __call__(self):
        """Run the gdb command.

        Return True when the command has been sent to gdb, False otherwise.

        """
        return self.sendcmd()

class VarObjCmdEvaluate(VarObjCmd):
    """The VarObjCmdEvaluate class."""

    def sendcmd(self):
        """Send the gdb command.

        Return True when the command has been sent to gdb, False otherwise.

        """
        name = self.varobj['name']
        if not name:
            return False
        self.result = ''
        return self.send('-var-evaluate-expression %s\n', name)

    def handle_result(self, line):
        """Send the gdb command."""
        parsed = misc.parse_keyval(re_varevaluate, line)
        if VAREVALUATE_ATTRIBUTES.issubset(parsed):
            self.result = line
            value = parsed['value']
            if value != self.varobj['value']:
                self.varobj.chged = True
                self.gdb.info.varobj.dirty = True
                self.varobj['value'] = value

class VarObjCmdDelete(VarObjCmd):
    """The VarObjCmdDelete class."""

    def sendcmd(self):
        """Send the gdb command.

        Return True when the command has been sent to gdb, False otherwise.

        """
        name = self.varobj['name']
        if not name:
            return False
        self.result = ''
        return self.send('-var-delete %s\n', name)

    def handle_result(self, line):
        """Send the gdb command."""
        matchobj = re_vardelete.match(line)
        if matchobj:
            self.result = matchobj.group('ndeleted')
            if self.result:
                name = self.varobj['name']
                rootvarobj = self.gdb.info.varobj
                (varobj, varlist) = rootvarobj.leaf(name)
                if varlist is not None:
                    del varlist[name]
                    rootvarobj.dirty = True

class OobCommand(object):
    """Abstract class for all static OobCommands.

    An OobCommand can either send a gdb command, or process the result of other
    OobCommands as with the Project OobCommand.

    """

    __metaclass__ = ABCMeta

    def __init__(self, gdb):
        self.gdb = gdb

    @abstractmethod
    def notify(self, cmd):
        """Notify of the cmd being processed."""

    @abstractmethod
    def __call__(self):
        """Run the gdb command or perform the task.

        Return True when the command has been sent to gdb, False otherwise.

        """

class OobGdbCommand(OobCommand, Command):
    """Base abstract class for oob commands.

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
        cmd: str
            the command being currently processed
        trigger: boolean
            when True, invoke __call__()
        trigger_list: tuple
            list of commands that trigger the invocation of __call__()
        trigger_prefix: set
            set of the trigger_list command prefixes built from the
            trigger_list and the list of gdb commands

    """

    def __init__(self, gdb):
        OobCommand.__init__(self, gdb)
        assert self.__class__ is not OobGdbCommand
        assert hasattr(self, 'gdb_cmd') and isinstance(self.gdb_cmd, text_type)
        self.mi = not self.gdb_cmd.startswith('-interpreter-exec console')
        assert hasattr(self, 'info_attribute')              \
                and isinstance(self.info_attribute, text_type)\
                and hasattr(self.gdb.info, self.info_attribute)
        assert hasattr(self, 'prefix')                      \
                and isinstance(self.prefix, text_type)
        assert hasattr(self, 'regexp')                      \
                and hasattr(self.regexp, 'findall')
        assert hasattr(self, 'gdblist')                     \
                and isinstance(self.gdblist, bool)
        if hasattr(self, 'action'):
            assert hasattr(self.gdb.info, self.action)
        assert hasattr(self, 'trigger_list')                \
                and isinstance(self.trigger_list, tuple)
        assert hasattr(self, 'reqkeys')                     \
                and isinstance(self.reqkeys, set)
        self.cmd = ''
        self.trigger = False

        # build prefix list that triggers the command after being notified
        keys = list(set(self.gdb.cmds.keys()).difference(set(self.trigger_list)))
        self.trigger_prefix = {misc.smallpref_inlist(x, keys)
                                                for x in self.trigger_list}

    def notify(self, cmd):
        """Notify of the cmd being processed.

        The OobGdbCommand is run when the trigger_list is empty, or when a
        prefix of the notified command matches in the trigger_prefix list.

        """
        self.cmd = cmd
        if not self.trigger_list or     \
                    any([cmd.startswith(x) for x in self.trigger_prefix]):
            self.trigger = True

    def __call__(self):
        """Send the gdb command.

        Return True when the command was sent, False otherwise.

        """
        if self.trigger:
            if not self.gdblist and self.reqkeys:
                setattr(self.gdb.info, self.info_attribute, {})
            else:
                setattr(self.gdb.info, self.info_attribute, [])

            self.trigger = False
            return self.send(self.gdb_cmd)
        return False

    def parse(self, data):
        """Parse 'data' with the regexp after removing prefix.

        When successful, set the info_attribute.

        """
        if self.prefix in data:
            remain = data[data.index(self.prefix) + len(self.prefix):]
        elif hasattr(self, 'ignore') and self.ignore in data:
            return
        else:
            debug('bad prefix in oob parsing of "%s",'
                    ' requested prefix: "%s"', data.strip(), self.prefix)
            return

        # Parse as a Python:
        #   * list of dict: self.gdblist is True
        #   * a dict: self.gdblist is False and self.reqkeys not empty
        #   * a list: self.gdblist is False and self.reqkeys empty
        if self.gdblist:
            # A list of dictionaries.
            parsed = [x for x in
                       [misc.parse_keyval(self.regexp, list_element)
                        for list_element in re_dict_list.findall(remain)]
                             if self.reqkeys.issubset(x)]
        else:
            if self.reqkeys:
                parsed = misc.parse_keyval(self.regexp, remain)
                if not self.reqkeys.issubset(parsed):
                    parsed = {}
            else:
                parsed = self.regexp.findall(remain)
        if parsed:
            setattr(self.gdb.info, self.info_attribute, parsed)
        else:
            if not hasattr(self, 'remain') or remain != self.remain:
                debug('no match for "%s"', remain)

    def handle_result(self, result):
        """Process the result of the mi command."""
        if self.mi:
            self.parse(result)
            # call the gdb.info method
            if hasattr(self, 'action'):
                try:
                    getattr(self.gdb.info, self.action)(self.cmd)
                except (KeyError, ValueError):
                    error(traceback.format_tb(sys.exc_info()[2])[-1])
                    info_attribute = getattr(self.gdb.info,
                                            self.info_attribute)
                    if info_attribute:
                        error('bad format: %s', info_attribute)

    def handle_strrecord(self, stream_record):
        """Process the stream records output by the cli command."""
        if not self.mi:
            self.parse(stream_record)

# instantiate the OobGdbCommand subclasses
Args =          \
    type(str('Args'), (OobGdbCommand,),
            {
                '__doc__': """Get the program arguments.""",
                'gdb_cmd': '-interpreter-exec console "show args"\n',
                'info_attribute': 'args',
                'prefix': 'Argument list to give program being'     \
                          ' debugged when it is started is',
                'remain': ' "".\n',
                'regexp': re_args,
                'reqkeys': set(),
                'gdblist': False,
                'trigger_list': PROJECT_CMDS,
            })

Breakpoints =   \
    type(str('Breakpoints'), (OobGdbCommand,),
            {
                '__doc__': """Get the breakpoints list.""",
                'gdb_cmd': '-break-list\n',
                'info_attribute': 'breakpoints',
                'prefix': 'body=[',
                'remain': ']}',
                'regexp': re_breakpoints,
                'reqkeys': REQ_BREAKPOINT_ATTRIBUTES,
                'gdblist': True,
                'action': 'update_breakpoints',
                'trigger_list': BREAKPOINT_CMDS,
            })

Directories =   \
    type(str('Directories'), (OobGdbCommand,),
            {
                '__doc__': """Get the directory list.""",
                'gdb_cmd': '-interpreter-exec console "show directories"\n',
                'info_attribute': 'directories',
                'prefix': 'Source directories searched: ',
                'regexp': re_directories,
                'reqkeys': set(),
                'gdblist': False,
                'trigger_list': DIRECTORY_CMDS,
            })

File =          \
    type(str('File'), (OobGdbCommand,),
            {
                '__doc__': """Get the source file.""",
                'gdb_cmd': '-file-list-exec-source-file\n',
                'info_attribute': 'file',
                'prefix': 'done,',
                'regexp': re_file,
                'reqkeys': FILE_ATTRIBUTES,
                'gdblist': False,
                'trigger_list': FILE_CMDS,
            })

FrameCli =      \
    type(str('FrameCli'), (OobGdbCommand,),
            {
                '__doc__': """Get the frame information.""",
                'version_max': [6, 3],
                'gdb_cmd': 'frame\n',
                'info_attribute': 'frame',
                'prefix': 'done,',
                'regexp': re_framecli,
                'reqkeys': REQ_FRAME_ATTRIBUTES,
                'gdblist': False,
                'action': 'update_frame',
                'trigger_list': FRAME_CMDS,
            })

Frame=          \
    type(str('Frame'), (OobGdbCommand,),
            {
                '__doc__': """Get the frame information.""",
                'version_min': [6, 4],
                'gdb_cmd': '-stack-info-frame\n',
                'info_attribute': 'frame',
                'prefix': 'done,',
                'ignore': 'error,msg="No registers."',
                'regexp': re_frame,
                'reqkeys': REQ_FRAME_ATTRIBUTES,
                'gdblist': False,
                'action': 'update_frame',
                'trigger_list': FRAME_CMDS,
            })

BackTrace=          \
    type(str('BackTrace'), (OobGdbCommand,),
            {
                '__doc__': """Get the backtrace information.""",
                'gdb_cmd': '-stack-list-frames\n',
                'info_attribute': 'backtrace',
                'prefix': 'stack=[',
                'remain': ']}',
                'ignore': 'error,msg="No registers."',
                'regexp': re_frame,
                'reqkeys': REQ_FRAME_ATTRIBUTES,
                'gdblist': True,
                'trigger_list': FRAME_CMDS,
            })

Threads=          \
    type(str('Threads'), (OobGdbCommand,),
            {
                '__doc__': """Get the threads information.""",
                'gdb_cmd': '-thread-info\n',
                'info_attribute': 'threads_list',
                'prefix': 'threads=[',
                'remain': ']',
                'regexp': re_threads,
                'reqkeys': set(),
                'gdblist': False,
                'action': 'update_threads',
                'trigger_list': THREADS_CMDS,
            })

PgmFile =       \
    type(str('PgmFile'), (OobGdbCommand,),
            {
                '__doc__': """Get the program file.""",
                'gdb_cmd': '-interpreter-exec console "info files"\n',
                'info_attribute': 'debuggee',
                'prefix': 'Symbols from',
                'regexp': re_pgmfile,
                'reqkeys': set(),
                'gdblist': False,
                'trigger_list': PROJECT_CMDS,
            })

Pwd =           \
    type(str('Pwd'), (OobGdbCommand,),
            {
                '__doc__': """Get the current working directory.""",
                'gdb_cmd': '-environment-pwd\n',
                'info_attribute': 'cwd',
                'prefix': 'done,cwd=',
                'regexp': re_pwd,
                'reqkeys': set(),
                'gdblist': False,
                'trigger_list': PROJECT_CMDS,
            })

Sources =       \
    type(str('Sources'), (OobGdbCommand,),
            {
                '__doc__': """Get the list of source files.""",
                'gdb_cmd': '-file-list-exec-source-files\n',
                'info_attribute': 'sources',
                'prefix': 'done,',
                'remain': 'files=[]',
                'regexp': re_sources,
                'reqkeys': SOURCES_ATTRIBUTES,
                'gdblist': True,
                'trigger_list': SOURCE_CMDS + SOURCE_CMDS_EXTRA,
            })

VarUpdate =     \
    type(str('VarUpdate'), (OobGdbCommand,),
            {
                '__doc__': """Update the variable and its children.""",
                'gdb_cmd': '-var-update *\n',
                'info_attribute': 'changelist',
                'prefix': 'done,',
                'remain': 'changelist=[]',
                'regexp': re_varupdate,
                'reqkeys': VARUPDATE_ATTRIBUTES,
                'gdblist': True,
                'action': 'update_changelist',
                'trigger_list': VARUPDATE_CMDS,
            })

class Project(OobCommand):
    """Save project information.

    Instance attributes:
        project_name: str
            project file pathname

    """

    def __init__(self, gdb):
        OobCommand.__init__(self, gdb)
        self.project_name = ''

    def notify(self, line):
        """Set the project filename on notification."""
        self.project_name = ''
        cmd = 'project '
        if line.startswith(cmd):
            self.project_name = line[len(cmd):].strip()

    def save_breakpoints(self, project):
        """Save the breakpoints in a project file.

        Save at most one breakpoint per line.

        """
        gdb_info = self.gdb.info
        bp_list = []
        for num in sorted(list(gdb_info.bp_dictionary.keys()), key=int):
            bp_element = gdb_info.bp_dictionary[num]
            pathname = gdb_info.get_fullpath(bp_element['file'])
            breakpoint = '%s:%s' % (pathname, bp_element['line'])
            if pathname is not None and breakpoint not in bp_list:
                project.write('break %s\n' % breakpoint)
                bp_list.append(breakpoint)

    def __call__(self):
        """Write the project file."""
        if self.project_name:
            # write the project file
            errmsg = ''
            gdb_info = self.gdb.info
            quitting = (self.gdb.state == self.gdb.STATE_QUITTING)
            if gdb_info.debuggee:
                try:
                    project = open(self.project_name, 'w')

                    if gdb_info.cwd:
                        cwd = gdb_info.cwd[0]
                        if not cwd.endswith(os.sep):
                            cwd += os.sep
                        project.write('cd %s\n' % misc.unquote(cwd))

                    project.write('file %s\n' % gdb_info.debuggee[0])

                    if gdb_info.args:
                        project.write('set args %s\n' % gdb_info.args[0])

                    self.save_breakpoints(project)

                    project.close()

                    msg = 'Project \'%s\' has been saved.' % self.project_name
                    info(msg)
                    self.gdb.console_print('%s\n', msg)
                    if not quitting:
                        self.gdb.print_prompt()
                except IOError as errmsg:
                    pass
            else:
                errmsg = 'Project \'%s\' not saved:'    \
                         ' no executable file specified.' % self.project_name
            if errmsg:
                error(errmsg)
                self.gdb.console_print('%s\n', errmsg)
                if not quitting:
                    self.gdb.print_prompt()
        return False

class Quit(OobCommand):
    """Quit gdb.

    """

    def notify(self, cmd):
        """Ignore the notification."""

    def __call__(self):
        """Quit gdb."""
        if self.gdb.state == self.gdb.STATE_QUITTING:
            self.gdb.write('quit\n')

            # the Debugger instance is closing, its dispatch loop timer is
            # closing as well and we cannot rely on this timer anymore to handle
            # buffering on the console, so switch to no buffering
            self.gdb.console_print('\n=== End of gdb session ===\n')
            self.gdb.console_flush()

            self.gdb.state = self.gdb.STATE_CLOSING
            self.gdb.close()

        return False

