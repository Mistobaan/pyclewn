"""Used by the gdb test suite to test the 'threads' list buffer."""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals


import sys
import threading

def foo(lock):
    with lock:
        sys.getdefaultencoding()    # C function: sys_getdefaultencoding()

def main():
    lock = threading.Lock()
    with lock:
        t = threading.Thread(target=foo, args=(lock,))
        t.start()
        sys.getrecursionlimit()     # C function: sys_getrecursionlimit()
    t.join()

if __name__ == '__main__':
    main()

