"""Debugged module used by the test suite."""

# Python 2-3 compatibility.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from io import open

import sys
import os
import time

class C(object):
    """Test class."""
    def __init__(self, value):
        self.value = value

    def get_value(self):
        """Getter."""
        return self.value

def loop():
    """Infinite loop."""
    while True:
        time.sleep(.200)
    return

def bar(prefix, i):
    """Testing an exception and infinite loop."""
    if i == 0:
        sys.stderr = open(os.devnull, 'w')
        i = 1/i
    elif i == -1:
        loop()

    print(prefix, i)
    return i + 1

def foo(run, do_sleep, *args):
    """Main function."""
    c = C(1)
    while run:
        if do_sleep:
            time.sleep(.200)
        val = bar('value', c.get_value())
        c = C(val)
        if c.value == 0:
            break

    return 0

