FAQ
===

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

