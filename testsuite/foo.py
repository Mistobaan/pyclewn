"""Debugged module used by the test suite."""
import sys
import os
import time

class C:
    """Test class."""
    def __init__(self, value):
        """Constructor."""
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

    print prefix, i
    return i + 1

def foo(run, do_sleep, *args):
    """Main function."""
    c = C(1)
    unused = args
    while run:
        if do_sleep:
            time.sleep(.200)
        val = bar('value', c.get_value())
        c = C(val)
        if c.value == 0:
            break

    return 0

