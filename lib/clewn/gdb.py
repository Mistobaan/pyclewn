# vi:set ts=8 sts=4 sw=4 et tw=80:
"""
The Gdb debugger is a frontend to GDB/MI.
"""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from io import open

import os
import subprocess
import re
import time
import pkgutil
import collections
from itertools import takewhile

from . import ClewnError, gdbmi, misc, debugger
from .process import Process

# On most other platforms the best timer is time.time()
_timer = time.time

# minimum gdb version
GDB_VERSION = [6, 2, 1]

# gdb initial settings
GDB_INIT = """
set confirm off
set height 0
set width 0
set annotate 1
"""
COMPLETION_TIMEOUT = 10 # seconds
SETFMTVAR_FORMATS = ('binary', 'decimal', 'hexadecimal', 'octal', 'natural')
COMPLETION = ('command! -bar -nargs=* -complete=customlist,s:GdbComplete' +
              debugger.COMPLETION_SUFFIX)

# list of key mappings, used to build the .pyclewn_keys.gdb file
#     key : (mapping, comment)
MAPKEYS = {
    'C-Z': ('sigint',
                'kill the inferior running program'),
    'S-B': ('info breakpoints',),
    'S-L': ('info locals',),
    'S-A': ('info args',),
    'S-S': ('step',),
    'C-N': ('next',),
    'S-F': ('finish',),
    'S-R': ('run',),
    'S-Q': ('quit',),
    'S-C': ('continue',),
    'S-X': ('foldvar ${lnum}',
                'expand/collapse a watched variable'),
    'S-W': ('where',),
    'C-U': ('up',),
    'C-D': ('down',),
    'C-B': ('break "${fname}":${lnum}',
                'set breakpoint at current line'),
    'C-K': ('clear "${fname}":${lnum}',
                'clear breakpoint at current line'),
    'C-P': ('print ${text}',
                'print value of selection at mouse position'),
    'C-X': ('print *${text}',
                'print value referenced by word at mouse position'),
}

RE_COMPLETION = r'^(?P<cmd>\S+)\s*(?P<arg>\S+)(?P<rest>.*)$'    \
                r'# RE: cmd 1st_arg_completion'
RE_MIRECORD = r'^(?P<token>\d\d\d)[\^*+=](?P<result>.*)$'       \
              r'# gdb/mi record'
RE_ANNO_1 = r'^[~@&]"\\032\\032([a-zA-Z]:|)[^:]+:[^:]+:[^:]+:[^:]+:[^:]+$'  \
            r'# annotation level 1'                                         \
            r'# ^Z^ZFILENAME:LINE:CHARACTER:MIDDLE:ADDR'                    \
            r'# ^Z^ZD:FILENAME:LINE:CHARACTER:MIDDLE:ADDR'
RE_FINISH = r'(gdb-result-var|return-value)=%s'                 \
            r'# return value after Cfinish' % misc.QUOTED_STRING
RE_VIM_COMMAND = r'^[a-zA-Z0-9]+$'                              \
                 r'# a valid Vim command name'

# compile regexps
re_completion = re.compile(RE_COMPLETION, re.VERBOSE)
re_mirecord = re.compile(RE_MIRECORD, re.VERBOSE)
re_anno_1 = re.compile(RE_ANNO_1, re.VERBOSE)
re_finish = re.compile(RE_FINISH, re.VERBOSE)
re_vim_command = re.compile(RE_VIM_COMMAND, re.VERBOSE)

# set the logging methods
(critical, error, warning, info, debug) = misc.logmethods('gdb')

def gdb_batch(pgm, job):
    """Run job in gdb batch mode and return the result as a string."""
    # create the gdb script as a temporary file
    with misc.TmpFile('gdbscript') as f:
        f.write(job)

    result = None
    try:
        result = subprocess.Popen((pgm, '--interpreter=mi',
                                        '-batch', '-nx', '-x', f.name),
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE).communicate()[0]
    except OSError:
        raise ClewnError('cannot start gdb as "%s"' % pgm)

    return result.decode()

def parse_gdb_version(header):
    r"""Parse the gdb version from the gdb header.

    From GNU coding standards: the version starts after the last space of the
    first line.

    >>> DOCTEST_GDB_VERSIONS = [
    ... r'~"GNU gdb (GDB) 7.5.1\n"',
    ... r'~"GNU gdb (Sourcery CodeBench Lite 2011.09-69) 7.2.50.20100908-cvs\n"',
    ... r'~"GNU gdb (GDB) SUSE (7.5.1-2.5.1)\n"',
    ... r'~"GNU gdb (GDB) Fedora (7.6-32.fc19)\n"',
    ... r'~"GNU gdb (GDB) 7.6.1.dummy\n"',
    ... r'~"GNU gdb (GDB) 7.6.50.20130728-cvs (cygwin-special)\n"',
    ... ]
    >>> for header in DOCTEST_GDB_VERSIONS:
    ...     print(parse_gdb_version(header))
    [7, 5, 1]
    [7, 2, 50, 20100908]
    [7, 5, 1]
    [7, 6]
    [7, 6, 1]
    [7, 6, 50, 20130728]

    """
    def parse_version(txt):
        # Allow for Suse non conformant implementation that encloses the version
        # in brackets (issue 119).
        txt = txt.lstrip('(')
        return ''.join(takewhile(lambda x: x.isdigit() or x == '.', txt))

    lines = (x[2:-3] for x in header.splitlines() if x.startswith('~"') and
                                                        x.endswith(r'\n"'))
    try:
        vlist = next(lines).rsplit(' ', 1)
    except StopIteration:
        pass
    else:
        while len(vlist) == 2:
            version = parse_version(vlist[1])
            if version:
                return [int(x) for x in version.split('.') if x]
            vlist = vlist[0].rsplit(' ', 1)

@misc.previous_evaluation
def gdb_version(pgm):
    """Check that the gdb version is valid.

    gdb 6.1.1 and below are rejected because:
        gdb 6.1.1:error,msg='Undefined mi command:
                file-list-exec-source-files (missing implementation)'

    """
    # check first tty access rights
    # (gdb does the same on forking the debuggee)
    if hasattr(os, 'ttyname'):
        try:
            ttyname = os.ttyname(0)
        except OSError as err:
            info('No terminal associated with stdin: %s', err)
        else:
            try:
                fd = os.open(ttyname, os.O_RDWR)
                os.close(fd)
            except OSError as err:
                raise ClewnError("Gdb cannot open the terminal: %s" % err)

    header = gdb_batch(pgm, 'show version')
    version = parse_gdb_version(header)
    if version:
        if version < GDB_VERSION:
            raise ClewnError('invalid gdb version "%s"' % version)
        info('gdb version: %s', version)
        return version

    if header:
        critical('response to "show version":\n%s%s%s',
                    '***START***\n',
                    header,
                    '***END***\n')
    raise ClewnError('cannot find the gdb version')

class GlobalSetup(misc.Singleton):
    """Container for gdb data constant across all Gdb instances.

    Class attributes:
        filename_complt: list
            list of gdb commands with file name completion
        illegal_cmds: list
            list of gdb illegal commands
        run_cmds: tuple
            list of gdb commands that cause the frame sign to be turned off
        illegal_setargs: tuple
            list of illegal arguments to the gdb set command

    Instance attributes:
        gdbname: str
            gdb program name to execute
        cmds: dict
            See the description of the Debugger 'cmds' attribute dictionary.
        gdb_cmds: list
            List all gdb commands, excluding illegal and dash commands
        f_ack: closed file object
            temporary file used to acknowledge the end of writing to f_clist
        f_clist: closed file object
            temporary file containing the symbols completion list
        illegal_cmds_prefix: list
            List of the illegal command prefix built from illegal_cmds and the
            list of commands
        run_cmds_prefix: list
            List of the run command prefix built from run_cmds and the
            list of commands
        illegal_setargs_prefix: list
            List of the illegal arguments to the set command, built from
            illegal_setargs and the list of the 'set' arguments

    """

    filename_complt = [
        'cd',
        'directory',
        'file',
        'load',
        'make',
        'path',
        'restore',
        'run',
        'source',
        'start',
        'tty',
        'shell',
        ]
    illegal_cmds = [
        '-', '+', '<', '>', '!',
        # 'complete' is an illegal user command, but it is used by
        # s:GdbComplete() to implement the completion.
        'complete',
        'edit',
        'end',
        # tui commands
        'layout',
        'focus',
        'fs',
        'refresh',
        'tui',
        'update',
        'winheight',
        ]
    run_cmds = (
        'attach', 'detach', 'kill',
        'run', 'start', 'continue', 'fg', 'step', 'next', 'finish', 'until', 'advance',
        'jump', 'signal', 'return',
        'file', 'exec-file', 'core-file',
        )
    illegal_setargs = (
        'annotate',
        'confirm',
        'height',
        'width',
        )

    def init(self, gdbname, pyclewn_cmds, vim_implementation):
        """Singleton initialisation."""
        self.gdbname = gdbname
        self.pyclewn_cmds = pyclewn_cmds
        self.vim_implementation = vim_implementation

        self.cmds = {}
        self.gdb_cmds = ['']
        self.illegal_cmds_prefix = []
        self.run_cmds_prefix = []
        self.illegal_setargs_prefix = []
        self.build_cmds()

        self.f_ack = misc.tmpfile('gdb')
        self.f_clist = misc.tmpfile('gdb')

    def __init__(self, gdbname, pyclewn_cmds, vim_implementation):
        self.gdbname = gdbname
        self.pyclewn_cmds = pyclewn_cmds
        self.vim_implementation = vim_implementation

    def build_cmds(self):
        """Build the completion lists from gdb and build the GlobalSetup lists.

        Build the following lists and the 'cmds' dict:
            cmds: dict
                all the commands and the Vim (static) completion of their
                argument
            gdb_cmds: list
                the gdb commands whose argument completion is (dynamically)
                obtained from gdb, once gdb has been started

            illegal_cmds_prefix
            run_cmds_prefix
            illegal_setargs_prefix
        """
        # List of gdb commands that cannot be made into a Vim command name.
        invalid_vim_commands = []
        firstarg_complt = ''

        nocomplt_cmds = self.illegal_cmds + self.filename_complt

        # Get the list of gdb commands.
        for cmd in (x[2:-3] for x in gdb_batch(
                                self.gdbname, 'complete').splitlines()
                                if x.startswith('~"') and x.endswith(r'\n"')):
            if not cmd:
                continue

            cmd = cmd.split()[0]
            valid_vim_command = re.match(re_vim_command, cmd)

            if cmd not in self.illegal_cmds and valid_vim_command:
                self.gdb_cmds.append(cmd)

            if cmd in nocomplt_cmds:
                continue
            elif not valid_vim_command:
                invalid_vim_commands.append(cmd)
            else:
                self.cmds[cmd] = []
                firstarg_complt += 'complete %s \n' % cmd

        # Get first arg completion commands.
        for result in (x[2:-3] for x in gdb_batch(
                                self.gdbname, firstarg_complt).splitlines()
                                if x.startswith('~"') and x.endswith(r'\n"')):
            matchobj = re_completion.match(result)
            if matchobj:
                cmd = matchobj.group('cmd')
                arg = matchobj.group('arg')
                rest = matchobj.group('rest')
                if not rest:
                    self.cmds[cmd].append(arg)
                else:
                    warning('invalid completion returned by gdb: %s', result)
            else:
                error('invalid completion returned by gdb: %s', result)

        # Add file name completion commands.
        for cmd in self.filename_complt:
            self.cmds[cmd] = None

        # Add the gdb commands that can't be made into a vim command.
        self.cmds[''] = invalid_vim_commands

        # Add pyclewn commands.
        for cmd, completion in self.pyclewn_cmds.items():
            if cmd and cmd != 'help':
                self.cmds[cmd] = completion

        keys = list(set(self.cmds.keys()).difference(self.vim_implementation))
        self.illegal_cmds_prefix = {misc.smallpref_inlist(x, keys)
                            for x in
                                (self.illegal_cmds + self.vim_implementation)}

        keys = list(set(keys).difference(set(self.run_cmds)))
        self.run_cmds_prefix = {misc.smallpref_inlist(x, keys)
                                            for x in self.run_cmds}

        # Note that once the first debug session is started and full gdb
        # completion is available, then completion on the illegal arguments to
        # the set command becomes available.
        if 'set' in self.cmds and self.cmds['set']:
            # Remove the illegal arguments.
            self.cmds['set'] = list(
                                    set(self.cmds['set'])
                                    .difference(set(self.illegal_setargs)))
            setargs = self.cmds['set']
            self.illegal_setargs_prefix = {misc.smallpref_inlist(x, setargs)
                                            for x in self.illegal_setargs}

class Gdb(debugger.Debugger, Process):
    """The Gdb debugger is a frontend to GDB/MI.

    Instance attributes:
        version: list
            current gdb version
        state: enum
            gdb state
        pgm: str
            gdb command or pathname
        arglist: list
            gdb command line arguments
        globaal: GlobalSetup
            gdb global data
        results: gdbmi.Result
            storage for expected pending command results
        oob_list: gdbmi.OobList
            list of OobCommand instances
        cli: gdbmi.CliCommand
            the CliCommand instance
        info: gdbmi.Info
            container for the debuggee state information
        gdb_busy: boolean
            False when gdb is ready to accept commands
        oob: iterator
            iterator over the list of OobCommand and VarObjCmd instances
        stream_record: list
            list of gdb/mi stream records output by a command
        lastcmd: gdbmi.MiCommand or gdbmi.CliCommand or gdbmi.ShowBalloon
                 instance
            + the last Command instance whose result is being processed
            + the empty string '' on startup or after a SIGINT
        token: string
            the token of the last gdb/mi result or out of band record
        curcmdline: str
            the current gdb command line
        firstcmdline: None, str or ''
            the first cli command line that starts gdb
        f_init: closed file object
            temporary file containing the gdb initialisation script
        time: float
            time of the startup of the sequence of oob commands
        multiple_choice: float
            time value, keeping track of a breakpoint multiple choice setting
            on an overloaded class method
        cmd_fifo: deque
            fifo of (method, cmd, args) tuples.
        async: boolean
            when True, store the commands in the cmd_fifo
        project: string
            project file pathname
        foldlnum: int
            line number of the current fold operation
        doprompt: boolean
            True when the prompt must be printed to the console

    """

    # gdb states
    STATE_INIT, STATE_RUNNING, STATE_QUITTING, STATE_CLOSING = list(range(4))

    def __init__(self, *args):
        debugger.Debugger.__init__(self, *args)
        self.pyclewn_cmds.update(
            {
                'dbgvar': (),
                'delvar': (),
                'foldvar': (),
                'setfmtvar': (),
                'project': True,
                'sigint': (),
                'define': (),
                'document': (),
                'commands': (),
            })
        self.pyclewn_cmds['inferiortty'] = ()
        self.vim_implementation.extend(
            [
                'define',
                'document',
                'commands'
            ])
        self.mapkeys.update(MAPKEYS)

        self.state = self.STATE_INIT
        self.pgm = self.vim.options.pgm or 'gdb'
        self.arglist = self.vim.options.args
        self.version = gdb_version(self.pgm)
        self.f_init = None
        Process.__init__(self, self.vim.loop)

        self.info = gdbmi.Info(self)
        self.globaal = GlobalSetup(self.pgm, self.pyclewn_cmds,
                                                self.vim_implementation)
        self.cmds = self.globaal.cmds
        self.gdb_cmds = self.globaal.gdb_cmds
        self.results = gdbmi.Result()
        self.oob_list = gdbmi.OobList(self)
        self.cli = gdbmi.CliCommand(self)
        self.gdb_busy = True
        self.oob = None
        self.stream_record = []
        self.lastcmd = ''
        self.doprompt = False
        self.token = ''
        self.curcmdline = ''
        self.firstcmdline = None
        self.time = None
        self.multiple_choice = 0
        self.cmd_fifo = collections.deque()
        self.async = False
        self.project = ''
        self.foldlnum = None
        self.parse_paramlist(self.vim.options.gdb)
        self.bg_jobs.append([self.gdb_background_jobs])

    def parse_paramlist(self, parameters):
        """Process the class parameter list."""
        for param in [x.strip() for x in parameters.split(',') if x]:
            if param.lower() == 'async':
                self.async = True
                continue

            pathname = os.path.expanduser(param)
            if os.path.isabs(pathname)          \
                        or pathname.startswith(os.path.curdir):
                if not os.path.isdir(pathname)  \
                        and os.path.isdir(os.path.dirname(pathname)):
                    if not self.project:
                        if os.path.isfile(pathname):
                            try:
                                f = open(pathname, 'r')
                                f.close()
                            except IOError as err:
                                raise ClewnError(
                                        'project file %s: %s' % (param, err))
                        self.project = pathname
                        continue
                    raise ClewnError(
                                'cannot have two project file names:'
                                        ' %s and %s' % (self.project, param))
                raise ClewnError(
                        'not a valid project file pathname: %s' % param)
            raise ClewnError(
                    'invalid parameter for the \'--gdb\' option: %s' % param)

    def getargv(self):
        """Return the gdb argv list."""
        argv = [self.pgm]
        argv += ['-tty=%s' % self.vim.options.tty]

        # build the gdb init temporary file
        with misc.TmpFile('gdbscript') as self.f_init:
            self.f_init.write(GDB_INIT)

        argv += ['-x'] + [self.f_init.name] + ['--interpreter=mi']
        if self.arglist:
            argv += self.arglist
        return argv

    def vim_script_custom(self, prefix):
        """Return gdb specific vim statements to add to the vim script."""
        commands = []
        substitute = {'pre': prefix}
        for cmd in self.gdb_cmds:
            substitute['cmd'] = cmd
            commands.append(COMPLETION % substitute)

        substitute = {
                'pre': prefix,
                'ack_tmpfile': misc.quote(self.globaal.f_ack.name),
                'complete_tmpfile': misc.quote(self.globaal.f_clist.name),
                'completion_timeout': COMPLETION_TIMEOUT,
                'commands': '\n'.join(commands),
                     }
        return pkgutil.get_data(__name__, 'gdb.vim').decode() % substitute

    def start(self):
        """Start gdb."""
        self.console_print('\n')
        Process.start(self, self.getargv())

    def print_prompt(self):
        """Print the prompt."""
        if not self.gdb_busy:   # print prompt only after gdb has started
            debugger.Debugger.print_prompt(self)

    def gdb_background_jobs(self):
        if self.multiple_choice:
            if _timer() - self.multiple_choice > 0.500:
                self.multiple_choice = 0
                self.write('1\n')
            # do not pop a command from fifo while multiple_choice pending
            return

        if self.cmd_fifo and self.accepting_cmd():
            (method, cmd, args) = self.cmd_fifo.popleft()
            debugger.Debugger._do_cmd(self, method, cmd, args)

    def accepting_cmd(self):
        """Return True when gdb is ready to process a new command."""
        return not self.gdb_busy and self.oob is None

    def terminate_cmd(self):
        """Do the command end processing."""
        self.gdb_busy = False
        self.multiple_choice = 0
        if self.doprompt:
            self.doprompt = False
            self.print_prompt()

        # source the project file
        if self.state == self.STATE_INIT:
            self.state = self.STATE_RUNNING
            if self.project:
                self.clicmd_notify('source %s' % self.project)
                return

        # send the first cli command line
        if self.firstcmdline:
            self.clicmd_notify(self.firstcmdline)
        self.firstcmdline = ''

        # Update the list buffers.
        self.update_tabpage_buffers()
        varobj = self.info.varobj
        self.update_listbuffer('variables', varobj.collect, varobj.dirty,
                               self.foldlnum)
        self.foldlnum = None

        if self.time is not None:
            info('oob commands execution: %f second' % (_timer() - self.time))
            self.time = None

    def handle_strrecord(self, cmd):
        """Process the stream records."""
        stream_record = ''.join(self.stream_record)
        if stream_record:
            cmd.handle_strrecord(stream_record)
        self.stream_record = []

    def handle_line(self, line):
        """Process the line received from gdb."""
        debug(line)
        if not line:
            error('handle_line: processing an empty line')
            return

        # gdb/mi stream record
        if line.startswith('> ~"'):
            # remove the '> ' prompt after a multiple choice
            line = line[2:]
        if line[0] in '~@':
            self.process_stream_record(line)
        elif line[0] in '&':
            # write the 'log' stream record to the console
            matchobj = misc.re_quoted.match(line[1:])
            if matchobj:
                line = misc.unquote(matchobj.group(1))
                self.stream_record.append(line)
            else:
                warning('bad format in gdb/mi log: "%s"', line)
        elif line.startswith('*stopped,reason="function-finished"'):
            # Print the return value after the 'Cfinish' command.
            rv = misc.parse_keyval(re_finish, line)
            if rv:
                self.console_print('Value returned is %(gdb-result-var)s ='
                                   ' %(return-value)s\n' % rv)
        elif line[0] in '*+=':
            # Ignore 'async' records.
            info(line[1:])
        else:
            matchobj = re_mirecord.match(line)
            # a gdb/mi result or out of band record
            if matchobj:
                self.process_mi_record(matchobj)
            # gdb/mi prompt
            elif line == '(gdb) ':
                self.process_prompt()
            else:
                # on Windows, the inferior output is redirected by gdb
                # to the pipe when 'new-console' is not set
                warning('handle_line: bad format: "%s"', line)

    def process_stream_record(self, line):
        """Process a received gdb/mi stream record."""
        matchobj = misc.re_quoted.match(line[1:])
        annotation_lvl1 = re_anno_1.match(line)
        if annotation_lvl1 is not None:
            return
        if matchobj:
            line = misc.unquote(matchobj.group(1))
            if (not self.stream_record and line == '[0] cancel\n[1] all\n') \
                    or (not self.multiple_choice                            \
                            and len(self.stream_record) == 1                \
                            and self.stream_record[0] == '[0] cancel\n'     \
                            and line.startswith('[1] all\n')):
                self.multiple_choice = _timer()
            self.stream_record.append(line)
        else:
            warning('process_stream_record: bad format: "%s"', line)

    def process_mi_record(self, matchobj):
        """Process a received gdb/mi record."""
        token = matchobj.group('token')
        result = matchobj.group('result')
        cmd = self.results.remove(token)
        if cmd is None:
            if token == self.token:
                # ignore received duplicate token
                pass
            elif self.state != self.STATE_QUITTING:
                # may occur on quitting with the debuggee still running
                raise ClewnError('invalid token "%s"' % token)
        else:
            self.token = token
            if isinstance(cmd, (gdbmi.CliCommand, gdbmi.MiCommand,
                                                        gdbmi.ShowBalloon)):
                self.lastcmd = cmd

            self.handle_strrecord(cmd)

            # Process an error message.
            errmsg = 'error,msg='
            if (result.startswith(errmsg) and
                    isinstance(cmd, (gdbmi.CliCommand, gdbmi.MiCommand))):
                result = result[len(errmsg):]
                matchobj = misc.re_quoted.match(result)
                if matchobj:
                    result = misc.unquote(matchobj.group(1))
                # Do not repeat the log stream record for CliCommands.
                if (not isinstance(cmd, gdbmi.CliCommand) or
                        result + '\n' != cmd.stream_record):
                    self.console_print('%s\n' % result)
            else:
                cmd.handle_result(result)

            self.process_oob()

    def process_prompt(self):
        """Process the gdb/mi prompt."""
        # process all the stream records
        cmd = self.lastcmd or self.cli
        self.handle_strrecord(cmd)

        # starting or after a SIGINT
        if self.lastcmd == '':
            self.process_oob()

    def process_oob(self):
        """Process OobCommands."""
        # got the prompt for a user command
        if self.lastcmd is not None:
            # prepare the next sequence of oob commands
            self.time = _timer()
            self.oob = self.oob_list.iterator()
            if len(self.results):
                if self.state != self.STATE_QUITTING:
                    # may occur on quitting with the debuggee still running
                    error('all cmds have not been processed in results')
                self.results.clear()

            if not isinstance(self.lastcmd, (gdbmi.CliCommandNoPrompt,
                                             gdbmi.ShowBalloon,
                                             gdbmi.CompleteCommand)):
                self.doprompt = True

            self.lastcmd = None

        # send the next oob command
        if self.oob is not None:
            try:
                # loop over oob commands that don't send anything
                while True:
                    if next(self.oob)():
                        break
            except StopIteration:
                self.oob = None
                self.terminate_cmd()

    def clicmd_notify(self, cmd, console=True, gdb=True):
        """Send a cli command after having notified the OobCommands.

        When 'console' is True, print 'cmd' on the console.
        When 'gdb' is True, send the command to gdb, otherwise send
        an empty command.

        """
        if console:
            self.console_print("%s\n", cmd)
        # notify each OobCommand instance
        for oob in self.oob_list:
            oob.notify(cmd)
        if gdb:
            self.cli.sendcmd(cmd)
        else:
            gdbmi.CliCommandNoPrompt(self).sendcmd('')

    def write(self, data):
        """Write data to gdb."""
        Process.write(self, data)
        debug(data.rstrip('\n'))

    def update_tabpage_buffers(self):
        debugger.Debugger.update_tabpage_buffers(self)
        self.update_listbuffer('breakpoints', self.info.collect_breakpoints,
                               self.info.bp_dirty)
        self.update_listbuffer('backtrace', self.info.collect_backtrace,
                               self.info.backtrace_dirty)
        self.update_listbuffer('threads', self.info.collect_threads,
                               self.info.threads_dirty)

    def close(self):
        """Close gdb."""
        if self.state == self.STATE_RUNNING:
            self.cmd_quit()
            return

        if not self.closed:
            # Update the 'breakpoints' buffer.
            self.info.breakpoints = {}
            self.info.update_breakpoints()

            # Update the 'backtrace' buffer.
            self.info.frame = {}
            self.info.update_frame()

            # Update the 'threads' buffer.
            self.info.threads_list = []
            self.info.update_threads()

            # Update the 'variables' buffer.
            varobj = self.info.varobj
            varobj.clear()

            debugger.Debugger.close(self)
            Process.close(self)

            # Remove temporary files.
            try:
                del self.f_init
            except AttributeError:
                pass

    #-----------------------------------------------------------------------
    #   commands
    #-----------------------------------------------------------------------

    def _do_cmd(self, method, cmd, args):
        """Process 'cmd' and its 'args' with 'method'.

        Execute directly the command when running in non-async mode.
        Otherwise, flush the cmd_fifo on receiving a sigint and send it,
        or queue the command to the fifo.
        """
        if method == self.cmd_sigint:
            self.lastcmd = ''

        if not self.async:
            debugger.Debugger._do_cmd(self, method, cmd, args)
            return

        if method == self.cmd_sigint:
            self.cmd_fifo.clear()
            debugger.Debugger._do_cmd(self, method, cmd, args)
            return

        # queue the command as a tuple
        self.cmd_fifo.append((method, cmd, args))

    def pre_cmd(self, cmd, args):
        """The method called before each invocation of a 'cmd_xxx' method."""
        self.curcmdline = cmd
        if args:
            self.curcmdline = '%s %s' % (self.curcmdline, args)

        # Echo the cmd, but not the first one and when not busy.
        if (self.firstcmdline is not None and cmd != 'sigint' and
                cmd != 'complete' and self.accepting_cmd()):
            self.console_print('%s\n', self.curcmdline)

    def post_cmd(self, cmd, args):
        """The method called after each invocation of a 'cmd_xxx' method."""
        pass

    def default_cmd_processing(self, cmd, args):
        """Process any command whose cmd_xxx method does not exist."""
        assert cmd == self.curcmdline.split()[0]
        if any([cmd.startswith(x)
                for x in self.globaal.illegal_cmds_prefix]):
            self.console_print('Illegal command in pyclewn.\n')
            self.print_prompt()
            return

        if cmd == 'set' and args:
            firstarg = args.split()[0]
            if any([firstarg.startswith(x)
                    for x in self.globaal.illegal_setargs_prefix]):
                self.console_print('Illegal argument in pyclewn.\n')
                self.print_prompt()
                return

        # Turn off the frame sign after a run command.
        if any([cmd.startswith(x)
                    for x in self.globaal.run_cmds_prefix])     \
                or any([cmd == x
                    for x in ('d', 'r', 'c', 's', 'n', 'u', 'j')]):
            self.info.hide_frame()

        if self.firstcmdline is None:
            self.firstcmdline = self.curcmdline
        else:
            self.clicmd_notify(self.curcmdline, console=False)

    def cmd_help(self, *args):
        """Print help on gdb and on pyclewn specific commands."""
        cmd, line = args
        if not line:
            self.console_print('Pyclewn specific commands:\n')
            debugger.Debugger.cmd_help(self, cmd)
            self.console_print('\nGdb help:\n')
        self.default_cmd_processing(cmd, line)

    def cmd_inferiortty(self, *args):
        """Spawn gdb inferior terminal and setup gdb with this terminal."""

        def set_inferior_tty_cb(line):
            cmd, args = line.split(' ', 1)
            self.cmd_fifo.append(
                    (self.default_cmd_processing,
                     cmd, args.strip()))

        if self.info.frame:
            self.console_print(
            'Cannot create the terminal, the inferior is already started.\n'
            'The gdb variable inferior-tty must be set *before*'
            ' starting the inferior.\n'
            )
        else:
            self.inferiortty(set_inferior_tty_cb)
        self.print_prompt()

    def cmd_complete(self, cmd, args):
        """Perform completion as requested by s:GdbComplete()."""
        gdbmi.CompleteCommand(self).sendcmd(args)

    def cmd_define(self, cmd, *args):
        """Define a new command name.  Command name is argument."""
        self.not_a_pyclewn_method(cmd)

    def cmd_commands(self, cmd, *args):
        """Set commands to be executed when a breakpoint is hit."""
        self.not_a_pyclewn_method(cmd)

    def cmd_document(self, cmd, *args):
        """Document a user-defined command."""
        self.not_a_pyclewn_method(cmd)

    def cmd_dbgvar(self, cmd, args):
        """Add a variable to the debugger variable buffer."""
        varobj = gdbmi.VarObj({'exp': args})
        if gdbmi.VarCreateCommand(self, varobj).sendcmd():
            self.oob_list.push(gdbmi.VarObjCmdEvaluate(self, varobj))

    def cmd_delvar(self, cmd, args):
        """Delete a variable from the debugger variable buffer."""
        args = args.split()
        # one argument is required
        if len(args) != 1:
            self.console_print('Invalid arguments.\n')
        else:
            name = args[0]
            (varobj, varlist) = self.info.varobj.leaf(name)
            if varobj is not None:
                gdbmi.VarDeleteCommand(self, varobj).sendcmd()
                return
            self.console_print('"%s" not found.\n' % name)
        self.print_prompt()

    def cmd_foldvar(self, cmd, args):
        """Collapse/expand a variable from the debugger variable buffer."""
        args = args.split()
        errmsg = ''
        # one argument is required
        if len(args) != 1:
            errmsg = 'Invalid arguments.'
        else:
            try:
                lnum = int(args[0])
            except ValueError:
                errmsg = 'Not a line number.'
        if not errmsg:
            rootvarobj = self.info.varobj
            if lnum in rootvarobj.parents:
                varobj = rootvarobj.parents[lnum]
                # collapse
                if varobj['children']:
                    for child in varobj['children'].values():
                        self.oob_list.push(gdbmi.VarObjCmdDelete(self, child))
                    # nop command used to trigger execution of the oob_list
                    if not gdbmi.NumChildrenCommand(self, varobj).sendcmd():
                        return
                # expand
                else:
                    if not gdbmi.ListChildrenCommand(self, varobj).sendcmd():
                        return
                self.foldlnum = lnum
                return
            else:
                errmsg = 'Not a valid line number.'
        if errmsg:
            self.console_print('%s\n' % errmsg)
        self.print_prompt()

    def cmd_setfmtvar(self, cmd, args):
        """Set the output format of the value of the watched variable."""
        args = args.split()
        # two arguments are required
        if len(args) != 2:
            self.console_print('Invalid arguments.\n')
        else:
            name = args[0]
            format = args[1]
            if format not in SETFMTVAR_FORMATS:
                self.console_print(
                    '\'%s\' is an invalid format, must be one of %s.\n'
                                            % (format, SETFMTVAR_FORMATS))
            else:
                (varobj, varlist) = self.info.varobj.leaf(name)
                if varobj is not None:
                    if gdbmi.VarSetFormatCommand(self, varobj).sendcmd(format):
                        self.oob_list.push(gdbmi.VarObjCmdEvaluate(self, varobj))
                    return
                self.console_print('"%s" not found.\n' % name)
        self.print_prompt()

    def cmd_project(self, cmd, args):
        """Save information to a project file."""
        if not args:
            self.console_print('Invalid argument.\n')
            self.print_prompt()
            return
        self.clicmd_notify('%s %s\n' % (cmd, args), console=False, gdb=False)
        self.gdb_busy = False

    def cmd_quit(self, *args):
        """Quit gdb."""
        if self.state == self.STATE_INIT:
            self.console_print("Ignoring 'quit' command on startup.\n")
            return


        # handle abnormal termination of gdb
        if hasattr(self, 'pid_status') and self.pid_status:
            self.state = self.STATE_CLOSING
            self.console_print('\n%s\n', self.pid_status)
            # save the project file
            if self.project:
                pobj = gdbmi.Project(self)
                pobj.notify('project %s' % self.project)
                pobj()
            self.console_print("Closing this gdb session.\n")
            self.console_print('\n===========\n')
            self.console_flush()
            self.close()
            return

        # Attempt to save the project file.
        # When oob commands are being processed, or gdb is busy in a
        # 'continue' statement, the project file is not saved.
        # The clicmd_notify nop command must not be run in this case, to
        # avoid breaking pyclewn state (assert on self.gdb_busy).
        self.state = self.STATE_QUITTING
        self.sendintr()
        if not self.gdb_busy and self.oob is None:
            if self.project:
                self.clicmd_notify('project %s' % self.project,
                                        console=False, gdb=False)
            else:
                self.clicmd_notify('dummy', console=False, gdb=False)
        else:
            self.state = self.STATE_CLOSING
            self.close()

    def cmd_sigint(self, *args):
        """Send a <C-C> character to the debugger."""
        if self.state == self.STATE_INIT:
            self.console_print("Ignoring 'sigint' command on startup.\n")
            return

        self.sendintr()
        self.console_print("Quit\n")

    #-----------------------------------------------------------------------
    #   netbeans events
    #-----------------------------------------------------------------------

    def balloon_text(self, text):
        """Process a netbeans balloonText event."""
        debugger.Debugger.balloon_text(self, text)
        if self.info.frame:
            gdbmi.ShowBalloon(self, text).sendcmd()

def _test():
    """Run the doctests."""
    import doctest
    doctest.testmod()

if __name__ == "__main__":
    _test()

