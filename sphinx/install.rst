Pyclewn installation notes
==========================

Required
--------

+------------+---------------------------------------+
| python     | gvim                                  |
+============+=======================================+
| python 2.4 | Vim 7.0 or above with the             |
| or above   | **netbeans_intg** feature enabled,    |
|            | and with the **autocmd** feature      |
|            | enabled                               |
|            | (netbeans and autocmd are             |
|            | enabled on most                       |
|            | distributions).                       |
+------------+---------------------------------------+

Note that netbeans does not run on the console vim, you must use gvim.

Install on unix
---------------

Unpack the tarball, change directory to the distribution directory and run the
setup script to install pyclewn::

    tar xzf pyclewn-d.d.tar.gz
    cd pyclewn-d.d
    python setup.py install

You can now use the ``:help pyclewn`` command within vim, to get access to the
documentation.


Local installation on unix
--------------------------

Use a local installation when you do not have root privileges and those are
required to install python packages or to install the vim runtime files on your
system.

Pyclewn binaries
^^^^^^^^^^^^^^^^

Local installation of the pyclewn binaries is done using the distutils ``home
scheme`` as follows (pyclewn is installed in $HOME/bin)::

    python setup.py install --home=$HOME

Vim runtime files
^^^^^^^^^^^^^^^^^

Local installation of the runtime file is done by setting the ``vimdir``
environment variable set to your personal vim runtime directory during
installation::

    vimdir=$HOME/.vim python setup.py install

Both binaries and runtime
^^^^^^^^^^^^^^^^^^^^^^^^^

Local installation of the pyclewn binaries and the runtime file is done with
the command::

    vimdir=$HOME/.vim python setup.py install --home=$HOME

Install on Windows
------------------

Pyclewn is installed with a Windows installer.

The following software must have been installed on Windows:

* the win32 python package from http://starship.python.net/crew/mhammond/
* MinGW and the MinGW components MSYS and gdb from http://www.mingw.org/

Gvim must be in the PATH before starting the installation, otherwise the
installation will fail. Use the Control Panel on Windows XP to add the gvim
directory to ``%PATH%``::

    Control Panel > System > Advanced tab
    Advanced tab > Enviroment Variables > Edit "PATH"

To install pyclewn, double-click on the installer: pyclewn-d.d.win32.exe. This
will install pyclewn, configure Vim and create a shortcut on the Desktop. The
installation is complete after the following message is printed by the
installer: ``pyclewn postinstall completed``. You can now use the ``:help
pyclewn`` command within vim, to access the documentation.

You may have to edit the installed shortcut (right-click > Properties) to
update the gdb full pathname when gdb has not been installed in the standard
MinGW location.

Pyclewn may be uninstalled with the Control Panel.

.. vim:filetype=rst:tw=78:ts=8:et:

