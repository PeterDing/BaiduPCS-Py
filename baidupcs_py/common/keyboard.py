# https://stackoverflow.com/a/22085679/2478637
# http://simondlevy.academic.wlu.edu/files/software/kbhit.py

from typing import Callable, Any

import os
import threading
import time

# Windows
if os.name == "nt":
    import msvcrt

# Posix (Linux, OS X)
else:
    import sys
    import termios
    import atexit
    from select import select


class KeyboardListener(threading.Thread):
    def __init__(self, on: Callable[[str], Any]):
        """Creates a KeyboardListener object that you can call to do various keyboard things."""
        super().__init__()

        self._on = on
        self._mt = threading.main_thread()

        if os.name == "nt":
            pass
        else:
            # Save the terminal settings
            self.fd = sys.stdin.fileno()
            self.new_term = termios.tcgetattr(self.fd)
            self.old_term = termios.tcgetattr(self.fd)

            # New terminal setting unbuffered
            self.new_term[3] = self.new_term[3] & ~termios.ICANON & ~termios.ECHO
            termios.tcsetattr(self.fd, termios.TCSAFLUSH, self.new_term)

            # Support normal-terminal reset at exit
            atexit.register(self.set_normal_term)

    def set_normal_term(self):
        """Resets to normal terminal.  On Windows this is a no-op."""

        if os.name == "nt":
            pass
        else:
            termios.tcsetattr(self.fd, termios.TCSAFLUSH, self.old_term)

    def getch(self):
        """Returns a keyboard character after kbhit() has been called.
        Should not be called in the same program as getarrow().
        """

        if os.name == "nt":
            return msvcrt.getch().decode("utf-8")
        else:
            return sys.stdin.read(1)

    def getarrow(self):
        """Returns an arrow-key code after kbhit() has been called. Codes are
        0 : up
        1 : right
        2 : down
        3 : left
        Should not be called in the same program as getch().
        """

        if os.name == "nt":
            msvcrt.getch()  # skip 0xE0
            c = msvcrt.getch()
            vals = [72, 77, 80, 75]
        else:
            c = sys.stdin.read(3)[2]
            vals = [65, 67, 66, 68]

        return vals.index(ord(c.decode("utf-8")))

    def kbhit(self):
        """Returns True if keyboard character was hit, False otherwise."""
        if os.name == "nt":
            return msvcrt.kbhit()

        else:
            dr, dw, de = select([sys.stdin], [], [], 0)
            return dr != []

    def run(self):
        while True:
            if self.kbhit():
                c = self.getch()
                self._on(c)
            else:
                time.sleep(0.1)

            # Exit when main_thread exited
            if not self._mt.is_alive():
                break

        self.set_normal_term()
