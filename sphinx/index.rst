
Pyclewn allows using `vim <http://www.vim.org>`_ as a front end to a debugger.
Pyclewn currently supports `gdb <http://www.gnu.org/software/gdb/gdb.html>`_.

The debugger output is redirected to a vim window, the pyclewn console. The
debugger commands are mapped to vim user-defined commands with a common letter
prefix, and with completion available on the commands and their first argument.

On unix, the controlling terminal of the program to debug is the terminal used
to launch pyclewn, or any other terminal when the debugger allows it, for
example after using the ``attach`` or ``tty`` gdb commands. On Windows, gdb pops
up a console attached to the program to debug.

Features
--------

* A debugger command can be mapped in vim to a key sequence using vim key
  mappings. This allows, for example, to set/clear a breakpoint or print a
  variable value at the current cursor or mouse position by just hitting a
  key.

* A sequence of gdb commands can be run from a vim script when the ``async``
  option is set. This may be useful in a key mapping.

* Breakpoints and the line in the current frame, are highlighted in the source
  code. Disabled breakpoints are noted with a different highlighting color.
  Pyclewn automatically finds the source file for the breakpoint if it exists,
  and tells vim to load and display the file and highlight the line.

* The value of an expression or variable is displayed in a balloon in vim when
  the mouse pointer is hovering over the selected expression or the variable.

* An expression can be watched in a vim window. The expression value is
  updated and highlighted whenever it has changed. When the expression is a
  structure or class instance, it can be expanded (resp. folded) to show
  (resp. hide) its members and their values.

* The ``project`` command saves the current gdb settings to a project file
  that may be sourced later by the gdb ``source`` command. These settings are
  the working directory, the debuggee program file name, the program arguments
  and the breakpoints. The sourcing and saving of the project file can be
  automated to occur on each gdb startup and termination, whith the
  ``project`` command line option.

* Vim command completion on the commands and their first argument.

.. note::

   Pyclewn uses the ``netbeans`` protocol to interact with vim. Vim currently
   only supports netbeans in ``gvim``, its graphical implementation. The
   implementation of netbeans in ``plain vim`` (vim running in a terminal), is
   a work in progress.

Comparison of clewn, vimGdb and pyclewn
---------------------------------------

The following table lists the differences between
`clewn <http://clewn.sourceforge.net>`_,
`vimGdb <http://clewn.sourceforge.net>`_ and pyclewn.

    +---------------+-------------+-----------------------+------------------------+
    |               | vimGdb      | clewn                 | pyclewn                |
    +===============+=============+=======================+========================+
    | platform      | unix        | unix                  | all unix platforms     |
    |               |             |                       | supported by python,   |
    |               |             |                       | Windows                |
    +---------------+-------------+-----------------------+------------------------+
    | langage       | C           | C                     | python 2.4 and         |
    |               |             |                       | above                  |
    +---------------+-------------+-----------------------+------------------------+
    | vim mode      | vim in a    | gvim                  | gvim                   |
    |               | terminal,   |                       |                        |
    |               | gvim        |                       |                        |
    +---------------+-------------+-----------------------+------------------------+
    | vim interface | a vim patch | a standalone program  | a standalone program   |
    |               |             | connected to gvim with| connected to gvim with |
    |               |             | a netbeans socket     | a netbeans socket      |
    +---------------+-------------+-----------------------+------------------------+
    | vim version   | a different | vim 6.3 and above     | vim 7.0 and above      |
    |               | patch for   |                       |                        |
    |               | each vim    |                       |                        |
    |               | version     |                       |                        |
    +---------------+-------------+-----------------------+------------------------+
    | debuggers     | gdb         | gdb                   | gdb                    |
    |               |             |                       |                        |
    |               |             |                       | future: pdb, ...       |
    +---------------+-------------+-----------------------+------------------------+
    | gd features   |             | watched variables     | tight integration      |
    |               |             |                       | with vim               |
    |               |             | project file          |                        |
    |               |             |                       | gdb/mi interface       |
    |               |             |                       |                        |
    |               |             |                       | asynchronous gdb       |
    |               |             |                       | commands               |
    |               |             |                       |                        |
    |               |             |                       | watched variables      |
    |               |             |                       |                        |
    |               |             |                       | project file           |
    +---------------+-------------+-----------------------+------------------------+

.. toctree::
   :maxdepth: 2
   :hidden:

   index
   news
   install
   faq
   svn

.. vim:filetype=rst:tw=78:ts=8:et:

