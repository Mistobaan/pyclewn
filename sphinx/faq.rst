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

Installation process on Windows could not find gvim
---------------------------------------------------

*Installation setup program couldn't find gvim. This is the error at the end
of installation process*::

    Failed to run '"C:\Program Files\Vim\vim73\gvim.exe"' as Vim.
    Please set the EDITOR environment variable or run 'pyclewn --editor=/path/to/(g)vim'.

    [Error 3] The system cannot find the path specified

*Also, I've set the EDITOR environment variable but it didn't work.*

The error message shows that the gvim pathname incorrectly includes double
quotes.  Do not enclose the EDITOR environment variable in double quotes.

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

When pyclewn is started from vim with the ``:Pyclewn`` command, there is no
terminal associated with pyclewn, the debuggee output is redirected to
``/dev/null``. So use the ``inferior_tty.py`` script to create a pseudo
terminal to be used as the controlling terminal of the process debugged by gdb.
For example, to debug vim (not gvim) and start the debugging session at vim's
main function.  From pyclewn, spawn an xterm terminal and launch
``inferior_tty.py`` in this terminal with the commands::

    :Cfile /path/to/vim
    :Cshell setsid xterm -e inferior_tty.py &

``inferior_tty.py`` prints the name of the pseudo terminal to be used by gdb
and the two gdb commands needed to configure properly gdb with this terminal.
Copy and paste these two commands in vim command line::

    :Cset inferior-tty /dev/pts/nn
    :Cset environment TERM = xterm

Then start the debugging session of vim and stop at vim main()::

    :Cstart

ImportError on install
----------------------

*I get the following error message: "ImportError: No module named subprocess".*

This error occurs when trying to install pyclewn with an old version of python.
Upgrade to python 2.4 or above.

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

