Vim patches
===========

Browsing Vim patches
--------------------

Vim patches are Mercurial Queues patches. You can browse the `Vim patches
mercurial repository
<http://pyclewn.hg.sourceforge.net/hgweb/pyclewn/vim-patches>`_ on line.

Clicking on `tags
<http://pyclewn.hg.sourceforge.net/hgweb/pyclewn/vim-patches/tags>`_ provides
the list of all available tags. Each tag corresponds to an official Vim release
or a snapshot of Vim development source tree. In this ``tags`` page, select the
tag of your choice and click on the corresponding ``files`` link. In this new
page, click on the ``series`` file to get the list of patches for this version
and the order in which the patches are applied. The first line of each patch
file contains a short description of the patch.

List of Vim patches:

* console-netbeans
    Netbeans support of Vim in a terminal. Enable pyclewn or other applications
    to implement a front end to a debugger when Vim is run in a terminal.

Patch a Vim tarball
-------------------

Example with vim-7.2.

#. Download the vim-7.2 tarball::

   $ wget ftp://ftp.vim.org/pub/vim/unix/vim-7.2.tar.bz2
   $ tar xjf vim-7.2.tar.bz2

#. Get the corresponding patch::

   $ hg clone --rev vim-7.2 http://pyclewn.hg.sourceforge.net/hgweb/pyclewn/vim-patches

#. Patch Vim. There is only one patch for vim-7.2, so only one patch command is
   issued. Otherwise, each patch must be applied in the order given by the
   ``series`` file. The ``--force`` patch option is needed in order to skip
   file ``gui_w48.c`` that does not exist in the unix tarball::

   $ cd vim72
   $ patch -p1 --force < ../vim-patches/console-netbeans

#. Build and install Vim.

Maintain a patched Vim development tree
---------------------------------------

The goal is to maintain a Vim Mercurial repository synchronized with the latest
Vim development tree, and a Mercurial Queues patch synchronized with pyclewn
vim-patches. Whenever you want to update the Vim development tree:

* the patches are first popped out
* changes are pulled into the Vim repository
* changes are pulled into pyclewn vim-patches
* the patches are pushed back

Since Vim does not use Mercurial yet, the Vim Mercurial repository is built
from a subversion work area. The entire process will be much simpler when Vim
uses Mercurial.

Initial setup
^^^^^^^^^^^^^

The following assumes that Vim subversion HEAD is at ``vim-7.2.ddd``, and that
``vim-7.2.nnn`` is the closest pyclewn vim-patches tag smaller or equal to
``vim-7.2.ddd``.

#. Get Vim source from subversion::

   $ svn co https://vim.svn.sourceforge.net/svnroot/vim/vim7

#. Build the hg repository in the subversion repository and clone it (first
   look into subversion logs to get the latest Vim patch number, ``vim-7.2.ddd``
   for the commit message)::

   $ cd vim7
   $ hg init
   $ svn log | less # for the commit message
   $ hg commit -q --addremove --exclude 're:.*\.svn\/.*' -m vim-7.2.ddd
   $ cd ..; hg clone vim7 vim-hg

#. Enable Mercurial Queues extension by editing your ``~/.hgrc`` and adding::

    [extensions]
    hgext.mq =

#. Edit ``vim-hg/.hg/hgrc`` and add the following hooks::

    [hooks]
    # Prevent "hg pull" if MQ patches are applied.
    prechangegroup.mq-no-pull = ! hg qtop > /dev/null 2>&1
    # Prevent "hg push" if MQ patches are applied.
    preoutgoing.mq-no-push = ! hg qtop > /dev/null 2>&1

#. Get pyclewn vim-patches and push all patches (see above how to browse the
   repository to get ``vim-7.2.nnn``)::

   $ cd vim-hg
   $ hg clone --rev vim-7.2.nnn http://pyclewn.hg.sourceforge.net/hgweb/pyclewn/vim-patches .hg/patches
   $ hg qpush --all

#. Build Vim.

Update Vim tree
^^^^^^^^^^^^^^^

The following assumes that Vim subversion HEAD is at ``vim-7.2.ddd``, and that
``vim-7.2.nnn`` is the closest pyclewn vim-patches tag smaller or equal to
``vim-7.2.ddd``.

#. Pop all the patches::

   $ cd vim-hg; hg qpop --all

#. Synchronize the changes from subversion and pull them into vim-hg::

   $ cd vim7
   $ hg locate -0 | xargs -0 rm
   $ cs src; make distclean; cd ..
   $ svn update -r HEAD
   $ svn log | less # for the commit message
   $ hg commit --addremove --exclude 're:.*\.svn\/.*' -m vim-7.2.ddd
   $ cd ../vim-hg; hg pull --update

#. Pull the latest vim-patches. Get the list of all available tags (the result
   of command ``mq tags``), and update with the ``vim-7.2.nnn`` tag that is the
   closest pyclewn vim-patches tag smaller or equal to ``vim-7.2.ddd``::

   $ cd vim-hg
   $ alias mq='hg -R $(hg root)/.hg/patches'
   $ mq pull
   $ mq tags
   $ mq update --rev vim-7.2.nnn

#. Push back the patches::

   $ hg qpush --all

#. Build Vim.

Documentation
-------------

Documentation on Mercurial can be found at `Mercurial: The Definitive Guide
<http://hgbook.red-bean.com/read/>`_.

Documentation on Mercurial Queues can be found at `Managing change with
Mercurial Queues
<http://hgbook.red-bean.com/read/managing-change-with-mercurial-queues.html>`_

Documentation on accessing the repository can be found at `SourceForge
documentation
<http://sourceforge.net/apps/trac/sourceforge/wiki/Mercurial>`_.
