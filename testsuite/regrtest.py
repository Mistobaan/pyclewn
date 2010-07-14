# vi:set ts=8 sts=4 sw=4 et tw=80:
#
# Copyright (C) 2007 Xavier de Gaye.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program (see the file COPYING); if not, write to the
# Free Software Foundation, Inc.,
# 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA
#

"""Regression tests."""

import os
import sys
import cStringIO
import traceback
import shutil
import textwrap

from testsuite import test_support

def run(testdir, tests=None, verbose=0):
    """Execute a test suite.

    testdir -- the directory in which to look for tests
    tests -- a list of strings containing test names

    If the tests argument is omitted, all *.py files beginning with test_ will
    be used.
    """

    good = []
    bad = []
    skipped = []
    resource_denieds = []

    nottests = NOTTESTS[:]
    tests = tests or findtests(testdir, nottests)
    test_support.verbose = verbose
    test_prefix = os.path.basename(os.path.normpath(testdir)) + '.'
    for test in tests:
        if test.startswith(test_prefix):
            abstest = test
        else:
            abstest = test_prefix + test
        print abstest
        sys.stdout.flush()
        try:
            ok = runtest(test, abstest, verbose)
        except KeyboardInterrupt:
            # print a newline separate from the ^C
            print
            break
        except:
            raise
        if ok > 0:
            good.append(test)
        elif ok == 0:
            bad.append(test)
        else:
            skipped.append(test)
            if ok == -2:
                resource_denieds.append(test)

    good.sort()
    bad.sort()
    skipped.sort()

    if good:
        if not bad and not skipped and len(good) > 1:
            print "All",
        print count(len(good), "test"), "OK."
    if bad:
        print count(len(bad), "test"), "failed:"
        printlist(bad)
    if skipped:
        print count(len(skipped), "test"), "skipped:"
        printlist(skipped)

    sys.exit(len(bad) > 0)


NOTTESTS = [
    'test_support',
    ]

def findtests(testdir, nottests=NOTTESTS):
    """Return a list of all applicable test modules."""
    names = os.listdir(testdir)
    tests = []
    for name in names:
        if name[:5] == "test_" and name[-3:] == os.extsep+"py":
            modname = name[:-3]
            if modname not in nottests:
                tests.append(modname)
    tests.sort()
    return tests

def runtest(test, abstest, verbose):
    """Run a single test.

    test -- the name of the test
    abstest -- absolute test name
    verbose -- if true, print more messages

    Return:
         0  test failed
         1  test passed
    """

    try:
        return runtest_inner(test, abstest, verbose)
    finally:
        cleanup_test_droppings(test, verbose)

def runtest_inner(test, abstest, verbose):
    """Run a single test.."""
    if verbose:
        capture_stdout = None
    else:
        capture_stdout = cStringIO.StringIO()

    try:
        save_stdout = sys.stdout
        try:
            if capture_stdout:
                sys.stdout = capture_stdout
            the_package = __import__(abstest, globals(), locals(), [])
            the_module = getattr(the_package, test)
            # run the test
            the_module.test_main()
        finally:
            sys.stdout = save_stdout
    except KeyboardInterrupt:
        raise
    except test_support.TestFailed, msg:
        print "test", test, "failed --", msg
        sys.stdout.flush()
        return 0
    except:
        exception, value = sys.exc_info()[:2]
        print "test", test, "crashed --", str(exception) + ":", value
        sys.stdout.flush()
        if verbose:
            traceback.print_exc(file=sys.stdout)
            sys.stdout.flush()
        return 0
    else:
        # except in verbose mode, tests should not print anything
        if verbose:
            return 1
        output = capture_stdout.getvalue()
        if not output:
            return 1
        print "test", test, "produced unexpected output:"
        print "*" * 70
        print output
        print "*" * 70
        sys.stdout.flush()
        return 0

def cleanup_test_droppings(testname, verbose):
    """Clean up after test has been run."""

    # Try to clean up junk commonly left behind.  While tests shouldn't leave
    # any files or directories behind, when a test fails that can be tedious
    # for it to arrange.  The consequences can be especially nasty on Windows,
    # since if a test leaves a file open, it cannot be deleted by name (while
    # there's nothing we can do about that here either, we can display the
    # name of the offending test, which is a real help).
    for name in (test_support.TESTFN,
                 "db_home",
                ):
        if not os.path.exists(name):
            continue

        if os.path.isdir(name):
            kind, nuker = "directory", shutil.rmtree
        elif os.path.isfile(name):
            kind, nuker = "file", os.unlink
        else:
            raise SystemError("os.path says %r exists but is neither "
                              "directory nor file" % name)

        if verbose:
            print "%r left behind %s %r" % (testname, kind, name)
        try:
            nuker(name)
        except Exception, msg:
            print >> sys.stderr, ("%r left behind %s %r and it couldn't be "
                "removed: %s" % (testname, kind, name, msg))

def count(n, word):
    """Pretty print count word."""
    if n == 1:
        return "%d %s" % (n, word)
    else:
        return "%d %ss" % (n, word)

def printlist(x, width=70, indent=4):
    """Print the elements of iterable x to stdout.

    Optional arg width (default 70) is the maximum line length.
    Optional arg indent (default 4) is the number of blanks with which to
    begin each line.
    """

    blanks = ' ' * indent
    print textwrap.fill(' '.join(map(str, x)), width,
               initial_indent=blanks, subsequent_indent=blanks)

