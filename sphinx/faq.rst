FAQ
===

Pyclewn never executes gdb
--------------------------

*A buffer named (clewn)_console is opened and ':echo has("netbeans_enabled")'
displays 1. However, a 'ps -fC gdb' reports nothing, and the (clewn)_console
buffer is always empty, regardless of the ':C' commands that are run.*

Netbeans is not supported by vim when vim is run in a terminal and vim version
is 7.2 or older. When you are running vim in a terminal (not gvim), make sure
the vim version is 7.3 or above.

Standard/error output in gdb console
------------------------------------

*I'm starting vim in a screen session inside Putty and gdb doesn't display
what's printed on the standard and error outputs*

When using vim, the debuggee output is redirected to ``/dev/null``. So
in this case you must tell gdb to redirect the debuggee output to
another terminal.

Start two putty sessions:

* on the first one run the command ``tty`` to get the name of the terminal.
  Assume for example that the command output is::

    /dev/pts/2

* on the second session, run vim, start pyclewn and gdb, and run the command::

    :Cset inferior-tty /dev/pts/2

* some gdb versions do not support the ``set inferior-tty`` command, in this
  case use the ``tty`` command instead

Now all debuggee output goes to the first putty terminal.

ImportError on install
----------------------

*I get the following error message: "ImportError: No module named subprocess".*

This error occurs when trying to install pyclewn with an old version of python.
Upgrade to python 2.4 or above.

Error on terminal open
----------------------

*I get the following error message: "Gdb cannot open the terminal: [Errno 13]
Permission denied: '/dev/pts/3'".*

This may happen after running the ``su - other_user`` unix command.

Gdb needs to open the terminal with read/write access rights. Check the
terminal ownership and access rights. Fix those with the ``chmod`` or the
``chown`` unix command.

Simultaneous sessions
---------------------

*I would like to run two or more instances of pyclewn simultaneously on the same
host.*

There is a bug in pyclewn that prevents two pyclewn sessions to use the same
listening port. This bug is fixed with pyclewn version 0.7.

With pyclewn version 0.6 and older, the second pyclewn session must use another
netbeans socket than the default netbeans socket on port 3219. This is done by
setting the appropriate parameters on the command line. For example, to use
port 3220 and password 'foobar'::

    pyclewn --netbeans=:3220:foobar --cargs=-nb:localhost:3220:foobar

Cannot set pending bp
---------------------

*I want to set a breakpoint in a shared library, and have no way to set the
breakpoint as pyclewn does not query me for "Make breakpoint pending on future
shared library load? (y or [n])".*

You must explicitly set the breakpoint pending mode to "on" with::

    :Cset breakpoint pending on

Pyclewn uses the gdb/mi API, and gdb/mi does not set pending breakpoints when
this option is "auto" (the default). Gdb help gives the following::

    (gdb) help set breakpoint pending
    Set debugger's behavior regarding pending breakpoints.
    If on, an unrecognized breakpoint location will cause
    gdb to create a pending breakpoint. If off, an
    unrecognized breakpoint location results in an error. If
    auto, an unrecognized breakpoint location results in a
    user-query to see if a pending breakpoint should be
    created.

