#! /usr/bin/env python

import sys
import os
import os.path
import tempfile
import atexit

def find_pyfiles(file_list):
    """Build a list of python files in all subdirectories."""
    for root, dirs, files in os.walk('.'):
        if root == '.':
            continue
        for file in files:
            if os.name != 'posix':
                if file == 'misc_posix.py': continue
            if os.name != 'nt':
                if file == 'misc_win.py': continue
            (base, ext) = os.path.splitext(file)
            if ext == '.py':
                file_list.append(os.path.join(root, file))

def unlink(filename):
    """Unlink a file."""
    if filename and os.path.exists(filename):
        try:
            os.unlink(filename)
        except OSError:
            pass

class TmpFile(file):
    """An instance of this class is a writtable temporary file object."""

    def __init__(self, prefix):
        """Constructor."""
        self.tmpname = None
        try:
            fd, self.tmpname = tempfile.mkstemp('.clewn', prefix)
            os.close(fd)
            file.__init__(self, self.tmpname, 'w')
        except (OSError, IOError):
            unlink(self.tmpname)
            print 'cannot create temporary file'; raise
        else:
            atexit.register(unlink, self.tmpname)

    def __del__(self):
        """Unlink the file."""
        unlink(self.tmpname)

pyfiles = sys.argv[1:]
if not pyfiles:
    find_pyfiles(pyfiles)

args = ['pychecker', '--quiet', '-F']
if os.name == 'nt':
    import pychecker.checker
    f = TmpFile('checker')
    # lots of false positive with pychecker on Windows
    for line in open('./.pycheckrc', 'r').readlines():
        if line.startswith('moduleImportErrors'):
            line = 'moduleImportErrors = 0'
        elif line.startswith('importUsed'):
            line = 'importUsed = 0'
        elif line.startswith('allVariablesUsed'):
            line = 'allVariablesUsed = 0'
        f.write(line)
    f.close()
    pychecker.checker.main(args + [f.name] + pyfiles)
else:
    import subprocess
    args.append('./.pycheckrc')
    for file in pyfiles:
        print '--- %s' % file
        output = subprocess.Popen(args + [file],
                                    stdout=subprocess.PIPE).communicate()[0]
        output = output.strip('\n')
        if output:
            print output

