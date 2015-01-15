#!/usr/bin/env python
# vi:set ts=8 sts=4 sw=4 et tw=80:
"""Script to build the Vim run time files."""

import os
import string
import tempfile
import subprocess
import shutil
import importlib

from lib.clewn import __version__

DEBUGGERS = ('simple', 'gdb', 'pdb')
RUNTIME = [
    'autoload/pyclewn.vim',
    'doc/pyclewn.txt',
    'plugin/pyclewn.vim',
    'syntax/dbgvar.vim',
    'macros/.pyclewn_keys.gdb',
    'macros/.pyclewn_keys.pdb',
    'macros/.pyclewn_keys.simple',
    ]

def keymap_files():
    """Build key map files for each debugger."""
    with open('runtime/macros/.pyclewn_keys.template') as tf:
        print('Updating:')
        template = tf.read()
        for d in DEBUGGERS:
            filename = 'runtime/macros/.pyclewn_keys.%s' % d
            with open(filename, 'w') as f:
                f.write(string.Template(template).substitute(clazz=d))
                module = importlib.import_module('.%s' % d, 'lib.clewn')
                mapkeys = getattr(module, 'MAPKEYS')
                for k in sorted(mapkeys):
                    if len(mapkeys[k]) == 2:
                        comment = ' # ' + mapkeys[k][1]
                        f.write('# %s%s\n' % (('%s : %s' %
                                (k, mapkeys[k][0])).ljust(30), comment))
                    else:
                        f.write('# %s : %s\n' % (k, mapkeys[k][0]))
            print('  %s' % filename)

def vimball():
    """Build the vimball."""
    fd, tmpname = tempfile.mkstemp(prefix='vimball', suffix='.clewn')
    args = ['vim', '-u', 'NORC', '-vN',
            '-c', 'edit %s' % tmpname,
            '-c', '%MkVimball! runtime/pyclewn runtime',
            '-c', 'quit',
           ]

    print('Removing the old versioned vimballs.')
    for dirpath, dirnames, filenames in os.walk('runtime'):
        if dirpath == 'runtime':
            for fname in filenames:
                if fname.startswith('pyclewn-'):
                    os.unlink(os.path.join(dirpath, fname))

    print('Creating the vimball.')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write('\n'.join(RUNTIME))
            f.close()
            subprocess.call(args)
    finally:
        try:
            os.unlink(tmpname)
        except OSError:
            pass

    vimball = 'runtime/pyclewn-%s.vmb' % __version__
    print('Copying vimball to %s.' % vimball)
    shutil.copy('runtime/pyclewn.vmb', vimball)

def main():
    keymap_files()
    vimball()

if __name__ == '__main__':
        main()
