#! /usr/bin/env python
# vi:set ts=8 sts=4 sw=4 et tw=80:
#
# the testsuite uses the python standard library testing framework with unittest
# see test/README and test/regrtest.py in the python distribution
# call this script with a test module name to test a single module
#                  with -v to get verbose output
#                  no argument to run the whole test suite

import os
import sys
import warnings
import sre
import cStringIO
import traceback

import test.regrtest as regrtest
import test.test_support as test_support

# override runtest from python 2.4 standard library
# this is broken when python changes the runtest function signature
# this is needed because, although the testing framework can be used
#   with a custom 'testdir', the test package name is hard coded in
#   this function
# all changes to runtest python 2.4 are tagged with FIXME
def runtest(test, generate, verbose, quiet, testdir=None, huntrleaks=False):
    """Run a single test.
    test -- the name of the test
    generate -- if true, generate output, instead of running the test
    and comparing it to a previously created output file
    verbose -- if true, print more messages
    quiet -- if true, don't print 'skipped' messages (probably redundant)
    testdir -- test directory
    """
    test_support.unload(test)
    if not testdir:
        testdir = findtestdir()
    outputdir = os.path.join(testdir, "output")
    outputfile = os.path.join(outputdir, test)
    if verbose:
        cfp = None
    else:
        cfp = cStringIO.StringIO()
    if huntrleaks:
        refrep = open(huntrleaks[2], "a")
    try:
        save_stdout = sys.stdout
        try:
            if cfp:
                sys.stdout = cfp
                print test              # Output file starts with test name
            if test.startswith(testdir + '.'):  # FIXME
                abstest = test
            else:
                # Always import it from the test package
                abstest = testdir + '.' + test  # FIXME
            the_package = __import__(abstest, globals(), locals(), [])
            the_module = getattr(the_package, test)
            # Most tests run to completion simply as a side-effect of
            # being imported.  For the benefit of tests that can't run
            # that way (like test_threaded_import), explicitly invoke
            # their test_main() function (if it exists).
            indirect_test = getattr(the_module, "test_main", None)
            if indirect_test is not None:
                indirect_test()
            if huntrleaks:
                # This code *is* hackish and inelegant, yes.
                # But it seems to do the job.
                import copy_reg
                fs = warnings.filters[:]
                ps = copy_reg.dispatch_table.copy()
                pic = sys.path_importer_cache.copy()
                import gc
                def cleanup():
                    import _strptime, urlparse, warnings, dircache
                    from distutils.dir_util import _path_created
                    _path_created.clear()
                    warnings.filters[:] = fs
                    gc.collect()
                    sre.purge()
                    _strptime._regex_cache.clear()
                    urlparse.clear_cache()
                    copy_reg.dispatch_table.clear()
                    copy_reg.dispatch_table.update(ps)
                    sys.path_importer_cache.clear()
                    sys.path_importer_cache.update(pic)
                    dircache.reset()
                if indirect_test:
                    def run_the_test():
                        indirect_test()
                else:
                    def run_the_test():
                        reload(the_module)
                deltas = []
                repcount = huntrleaks[0] + huntrleaks[1]
                print >> sys.stderr, "beginning", repcount, "repetitions"
                print >> sys.stderr, \
                      ("1234567890"*(repcount//10 + 1))[:repcount]
                for i in range(repcount):
                    rc = sys.gettotalrefcount()
                    run_the_test()
                    sys.stderr.write('.')
                    cleanup()
                    deltas.append(sys.gettotalrefcount() - rc - 2)
                print >>sys.stderr
                if max(map(abs, deltas[-huntrleaks[1]:])) > 0:
                    print >>sys.stderr, test, 'leaked', \
                          deltas[-huntrleaks[1]:], 'references'
                    print >>refrep, test, 'leaked', \
                          deltas[-huntrleaks[1]:], 'references'
                # The end of the huntrleaks hackishness.
        finally:
            sys.stdout = save_stdout
    except test_support.ResourceDenied, msg:
        if not quiet:
            print test, "skipped --", msg
            sys.stdout.flush()
        return -2
    except (ImportError, test_support.TestSkipped), msg:
        if not quiet:
            print test, "skipped --", msg
            sys.stdout.flush()
        return -1
    except KeyboardInterrupt:
        raise
    except test_support.TestFailed, msg:
        print "test", test, "failed --", msg
        sys.stdout.flush()
        return 0
    except:
        type, value = sys.exc_info()[:2]
        print "test", test, "crashed --", str(type) + ":", value
        sys.stdout.flush()
        if verbose:
            traceback.print_exc(file=sys.stdout)
            sys.stdout.flush()
        return 0
    else:
        if not cfp:
            return 1
        output = cfp.getvalue()
        if generate:
            if output == test + "\n":
                if os.path.exists(outputfile):
                    # Write it since it already exists (and the contents
                    # may have changed), but let the user know it isn't
                    # needed:
                    print "output file", outputfile, \
                          "is no longer needed; consider removing it"
                else:
                    # We don't need it, so don't create it.
                    return 1
            fp = open(outputfile, "w")
            fp.write(output)
            fp.close()
            return 1
        if os.path.exists(outputfile):
            fp = open(outputfile, "r")
            expected = fp.read()
            fp.close()
        else:
            expected = test + "\n"
        if output == expected or huntrleaks:
            return 1
        print "test", test, "produced unexpected output:"
        sys.stdout.flush()
        regrtest.reportdiff(expected, output)   # FIXME
        sys.stdout.flush()
        return 0

regrtest.STDTESTS = []
regrtest.runtest = runtest

regrtest.main(testdir='testsuite')

