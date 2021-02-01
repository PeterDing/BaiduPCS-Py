from typing import List, Callable, Any

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


_KEYBOARD_LISTENER_STARTED = False


def keyboard_listener_start():
    global _KEYBOARD_LISTENER_STARTED
    if _KEYBOARD_LISTENER_STARTED:
        return

    listener = KeyboardListener(on=KeyboardMonitor.on)
    listener.start()

    _KEYBOARD_LISTENER_STARTED = True
