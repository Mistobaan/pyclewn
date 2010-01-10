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
vim-patches. Whenever you want to update from the Vim development tree:

* the patches are first popped out
* changes are pulled into your Vim repository
* changes are pulled into pyclewn vim-patches
* the patches are pushed back

Initial setup
^^^^^^^^^^^^^

The following assumes that Vim latest patch is ``vim-7.2.ddd``, and that
``vim-7.2.nnn`` is the closest pyclewn vim-patches tag smaller or equal to
``vim-7.2.ddd``.

#. Clone Vim development tree and clone a working copy::

   $ hg clone --noupdate http://vim.googlecode.com/hg/ vim-master
   $ hg clone vim-master vim-working

#. Enable Mercurial Queues extension by editing your ``~/.hgrc`` and adding::

    [extensions]
    hgext.mq =

#. Edit ``vim-working/.hg/hgrc`` and add the following hooks::

    [hooks]
    # Prevent "hg pull" if MQ patches are applied.
    prechangegroup.mq-no-pull = ! hg qtop > /dev/null 2>&1
    # Prevent "hg push" if MQ patches are applied.
    preoutgoing.mq-no-push = ! hg qtop > /dev/null 2>&1

#. Get pyclewn vim-patches::

   $ cd vim-working
   $ hg clone http://pyclewn.hg.sourceforge.net/hgweb/pyclewn/vim-patches .hg/patches

#. Browse Vim logs to get the latest Vim patch number ``vim-7.2.ddd``,
   and run the ``mq tags`` command to list the vim-patches tags and to find
   ``vim-7.2.nnn`` which is the closest pyclewn vim-patches tag smaller or
   equal to ``vim-7.2.ddd``::

   $ hg log
   $ alias mq='hg -R $(hg root)/.hg/patches'
   $ mq tags

#. Update vim-patches to ``vim-7.2.nnn``, and push all patches::

   $ mq update --rev vim-7.2.nnn
   $ hg qpush --all

#. Build Vim.

Update Vim tree
^^^^^^^^^^^^^^^

The following assumes that Vim latest patch is ``vim-7.2.ddd``, and that
``vim-7.2.nnn`` is the closest pyclewn vim-patches tag smaller or equal to
``vim-7.2.ddd``.

#. Pop all the patches::

   $ cd vim-working
   $ hg qpop --all
   $ cd ..

#. Pull Vim changes into vim-working::

   $ cd vim-master
   $ hg pull
   $ cd ../vim-working
   $ hg pull --update

#. Pull vim-patches changes::

   $ alias mq='hg -R $(hg root)/.hg/patches'
   $ mq pull

#. Browse Vim logs to get the latest Vim patch number ``vim-7.2.ddd``,
   and run the ``mq tags`` command to list the vim-patches tags and to find
   ``vim-7.2.nnn`` which is the closest pyclewn vim-patches tag smaller or
   equal to ``vim-7.2.ddd``::

   $ hg log
   $ alias mq='hg -R $(hg root)/.hg/patches'
   $ mq tags

#. Update vim-patches to ``vim-7.2.nnn``, and push all patches::

   $ mq update --rev vim-7.2.nnn
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
