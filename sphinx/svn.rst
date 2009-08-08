Subversion
==========

Browsing the pyclewn sources
----------------------------

Browse the `pyclewn subversion repository
<http://pyclewn.svn.sourceforge.net/viewvc/pyclewn/trunk/pyclewn>`_ on line.
This shows the most recent version of the files in pyclewn. You can also view
the diffs and the revision logs for each file.

Maintaining a work area
-----------------------

Run the following command in the directory where you want to check out pyclewn
for the first time::

        $ svn co https://pyclewn.svn.sourceforge.net/\
        > svnroot/pyclewn/trunk/pyclewn pyclewn

Once pyclewn has been checked out, check the pyclewn mailing list for patches
or releases announcements, and update your work area from the subversion
repository by running the following command in the pyclewn directory::

        $ cd pyclewn
        $ svn update

Building from source
--------------------

Run the following command to build a distribution, the tarball is created in
the ``dist`` directory::

        $ python setup.py sdist

Documentation
-------------

Documentation on accessing the repository can be found at `SourceForge
documentation
<https://sourceforge.net/apps/trac/sourceforge/wiki/Subversion>`_.

Documentation on subversion can be found at `Version Control with Subversion
<http://svnbook.red-bean.com/nightly/en/index.html>`_.
