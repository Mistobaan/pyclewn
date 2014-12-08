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

        $ hg clone http://hg.code.sf.net/p/pyclewn/pyclewn

Check the pyclewn mailing list for patches or releases announcements, and
update your repository and work area by running the following commands in the
pyclewn directory::

        $ hg pull --update

Building from source
--------------------

Run the following command to build a distribution, the tarball is created in
the ``dist`` directory::

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
