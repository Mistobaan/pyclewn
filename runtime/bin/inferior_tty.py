#! /usr/bin/env python
# vi:set ts=8 sts=4 sw=4 et tw=80:
"""
Create a pseudo terminal to be used as the controlling terminal of a process.
"""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from io import open

import os
import sys
import asyncio

from clewn import misc, tty

def main():
    term = os.environ.get('TERM')
    if term is None:
        print('The TERM environment variable is not defined.', file=sys.stderr)
        sys.exit(1)

    loop = asyncio.get_event_loop()
    tasks, ptyname = tty.inferior_tty(cmds=True, loop=loop)

    commands = ('set inferior-tty %s\n'
                    'set environment TERM = %s\n' % (ptyname, term))
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'w') as f:
            f.write(commands)
    else:
        print('Set the inferior tty with the following gdb commands:')
        print(commands)

    misc.cancel_after_first_completed(tasks, lambda: None, loop)

if __name__ == '__main__':
    main()

