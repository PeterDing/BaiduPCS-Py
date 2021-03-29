from typing import List, Callable, Any
import sys

from baidupcs_py.common.keyboard import KeyboardListener


class KeyHandler:
    def __init__(self, key: str, callback: Callable[..., Any]):
        self._key = key
        self._callback = callback

    def handle(self, key: str):
        if self._key == key:
            self._callback(key)


class KeyboardMonitor:
    KEY_HANDLERS: List[KeyHandler] = []

    @classmethod
    def register(cls, key_handler: KeyHandler):
        cls.KEY_HANDLERS.append(key_handler)

    @classmethod
    def on(cls, key: str):
        for handler in cls.KEY_HANDLERS:
            handler.handle(key)


global _KEYBOARD_LISTENER_STARTED
_KEYBOARD_LISTENER_STARTED = False

global _KEYBOARD_LISTENER
_KEYBOARD_LISTENER = None


def keyboard_listener_start():
    global _KEYBOARD_LISTENER_STARTED
    if _KEYBOARD_LISTENER_STARTED:
        return

    # KeyboardListener is only available in a terminal
    if sys.stdin.isatty():
        listener = KeyboardListener(on=KeyboardMonitor.on)
        listener.start()

        global _KEYBOARD_LISTENER
        _KEYBOARD_LISTENER = listener

    _KEYBOARD_LISTENER_STARTED = True
