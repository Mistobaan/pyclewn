FAQ
===

Why isn't the async-option enabled by default ?
-----------------------------------------------

A drawback of having async-option enabled is that it might lead to unintended
command execution. For example, you might issue a ``step`` command before another
``step`` command has finished executing and unintentionally execute two step
commands, with no way to go back.

Use -x with gnome-terminal instead of -e in the --terminal option
-----------------------------------------------------------------

Konsole and rxvt both use -e in the same way that xterm does, to specify the
program (and its command  line  arguments) to be run in the terminal window,
but gnome-terminal uses -x instead.

Pyclewn never executes gdb
--------------------------

*A buffer named (clewn)_console is opened and ':echo has("netbeans_enabled")'
displays 1. However, a 'ps -fC gdb' reports nothing, and the (clewn)_console
buffer is always empty, regardless of the ':C' commands that are run.*

Netbeans is not supported by vim when vim is run in a terminal and vim version
is 7.2 or older. When you are running vim in a terminal (not gvim), make sure
the vim version is 7.3 or above.

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

