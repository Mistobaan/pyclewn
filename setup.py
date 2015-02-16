# vi:set ts=8 sts=4 sw=4 et tw=80:
"A Vim front-end to the gdb and pdb debuggers."

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from io import open

import sys
import os
import subprocess
import importlib
from unittest import defaultTestLoader
try:
    from setuptools import setup, Command
    SETUPTOOLS = True
except ImportError:
    SETUPTOOLS = False
    from distutils.core import setup, Command

from lib.clewn import __version__, PY3, PY34

long_description = []
within_toc = False
with open('README') as f:
    # Exclude the toc.
    for line in f:
        if within_toc and line.startswith('..'):
            within_toc = False
        if line.startswith('.. toctree'):
            within_toc = True
        elif not within_toc:
            long_description.append(line)

if not PY34:
    import distutils
    from distutils.util import byte_compile as _byte_compile

    def byte_compile(files, *args, **kwds):
        if 'dry_run' not in kwds or not kwds['dry_run']:
            mapping = {
                'import asyncio': 'import trollius as asyncio',
                'yield from': 'yield asyncio.From',
                }
            for fname in files:
                if fname[-3:] != '.py':
                    continue
                substitute_in_file(fname, mapping)
        return _byte_compile(files, *args, **kwds)

    distutils.util.byte_compile = byte_compile

def substitute_in_file(fname, mapping):
    with open(fname, 'r+') as f:
        updated = False
        lines = []
        for line in f:
            for s in mapping:
                idx = line.find(s)
                if idx != -1:
                    updated = True
                    line = ''.join([line[:idx], mapping[s], line[idx+len(s):]])
            lines.append(line)
        if updated:
            f.seek(0)
            f.write(''.join(lines))

NOTTESTS = ('test_support',)

class Test(Command):
    """Run the test suite.
    """

    user_options = [(str(x), str(y), str(z)) for (x, y, z) in
        (('test=', 't',
            'run a comma separated list of tests, for example             '
            '"--test=simple,gdb", all the tests are run when this option'
            ' is not present'),
        ('prefix=', 'p', 'run only tests whose name starts with this prefix'),
        ('stop', 's', 'stop at the first test failure or error'),
        ('detail', 'd', 'detailed test output, each test case is printed'),
        ('pdb', 'b', 'debug a single test with pyclewn and pdb: start the'
                     ' test with \'python setup.py test --test=gdb --pdb -p'
                     ' test_021\''
                     ' then start a Vim instance and run'
                     ' \'Pyclewn pdb\''),)
    ]

    def initialize_options(self):
        self.test = None
        self.prefix = None
        self.stop = False
        self.detail = False
        self.pdb = False

    def finalize_options(self):
        self.test = self.test or 'pyclewn,simple,gdb,pdb'

    def run (self):
        """Run the test suite."""
        import testsuite.test_support as test_support

        if self.pdb and self.test != ['test_gdb']:
            print('One can only debug a gdb test case for now.')
            return

        testsuite = 'testsuite'
        tests = ['test_' + t for t in self.test.split(',')]
        if self.prefix:
            defaultTestLoader.testMethodPrefix = self.prefix
        for test in tests:
            the_module = importlib.import_module('.%s' % test, testsuite)
            suite = defaultTestLoader.loadTestsFromModule(the_module)
            if self.pdb and (len(tests) > 1 or suite.countTestCases() > 1):
                print('Only one test at a time can be debugged, use the'
                      ' \'--test=\' and \'--prefix=\' options to set'
                      ' this test.')
                return
            if test == 'test_gdb':
                subprocess.check_call(['make', '-C', testsuite])
            # run the test
            print(the_module.__name__)
            sys.stdout.flush()
            test_support.run_suite(suite, self.detail, self.stop, self.pdb)

def main():
    requirements = []
    if not PY34:
        requirements.append('trollius')
    if PY3:
        requirements.append('pdb-clone==1.9.2.py3')
    else:
        requirements.append('pdb-clone==1.9.2.py2.7')

    install_options = {
        'cmdclass': {'test': Test},
        'packages': [str('clewn')],
        'package_dir':  {str(''): str('lib')},
        'package_data': {str('clewn'):
                            ['runtime/pyclewn-%s.vmb' % __version__]},

        # meta-data
        'name': 'pyclewn',
        'version': __version__,
        'description': __doc__,
        'long_description': ''.join(long_description),
        'platforms': 'all',
        'license': 'GNU GENERAL PUBLIC LICENSE Version 2',
        'author': 'Xavier de Gaye',
        'author_email': 'xdegaye at users dot sourceforge dot net',
        'url': 'http://pyclewn.sourceforge.net/',
        'classifiers': [
            'Topic :: Software Development :: Debuggers',
            'Intended Audience :: Developers',
            'Operating System :: Unix',
            'Programming Language :: Python :: 2.7',
            'Programming Language :: Python :: 3',
            'Development Status :: 6 - Mature',
            'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
        ],
    }

    if SETUPTOOLS:
        install_options['install_requires'] = requirements

    setup(**install_options)

if __name__ == '__main__':
    main()
