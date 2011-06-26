Mercurial
=========

Browsing pyclewn code
---------------------

Browse the `pyclewn mercurial repository`_ on line.
This shows the most recent version of the files in pyclewn. You can also view
the diffs and the revision logs for each file.

Clone pyclewn repository
------------------------

The following command will clone pyclewn repository in a local directory named
``pyclewn``::

        $ hg clone http://pyclewn.hg.sourceforge.net/hgweb/pyclewn/pyclewn

A version hook must be setup to update the ``clewn/__version__.py`` file after
each commit or update. To setup the hook, add the following lines to the
repository ``.hg/hgrc`` file, and run the ``hg update`` command::

    [hooks]
    commit.version = /bin/sh -c "`hg root`/version-hook.py commit clewn/__version__.py"
    update.version = /bin/sh -c "`hg root`/version-hook.py update clewn/__version__.py"

Check the pyclewn mailing list for patches or releases announcements, and
update your repository and work area by running the following commands in the
pyclewn directory::

        $ hg pull --update

The development of the Python 3 version of pyclewn is on the default branch.
To get the source of the Python 2 version of pyclewn, switch to the
``python2`` branch with the command::

        $ hg update python2

Building from source
--------------------

Run the following command to build a distribution, the tarball is created in
the ``dist`` directory::

        $ hg update default
        $ python3 setup.py sdist

Run the following commands to build a Python 2 distribution::

        $ hg update python2
        $ python setup.py sdist

Documentation
-------------

Documentation on Mercurial can be found at `Mercurial: The Definitive Guide`_.

Documentation on accessing the repository can be found at `SourceForge
documentation`_.


.. _`pyclewn mercurial repository`: http://pyclewn.hg.sourceforge.net/hgweb/pyclewn/pyclewn
.. _`Mercurial: The Definitive Guide`: http://hgbook.red-bean.com/read/
.. _`SourceForge documentation`: http://sourceforge.net/apps/trac/sourceforge/wiki/Mercurial
.. vim:filetype=rst:tw=78:ts=8:et:
