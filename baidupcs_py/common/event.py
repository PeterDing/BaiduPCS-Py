from typing import List, Union, Callable, Any
from pynput import keyboard
from pynput.keyboard import Key, KeyCode

TKey = Union[str, Key, KeyCode]


class KeyHandler:
    def __init__(self, key: TKey, callback: Callable[..., Any]):
        self._key = key
        self._callback = callback

    def handle(self, key: TKey):
        if isinstance(key, KeyCode) and isinstance(self._key, str):
            key_char = getattr(key, "char", None)
            if self._key == key_char:
                self._callback(key_char)

        elif isinstance(key, Key) and isinstance(self._key, Key):

            if self._key == key:
                self._callback(key)


class KeyboardMonitor:
    KEY_HANDLERS: List[KeyHandler] = []

    @classmethod
    def register(cls, key_handler: KeyHandler):
        cls.KEY_HANDLERS.append(key_handler)

    @classmethod
    def on_press(cls, key: TKey):
        pass

    @classmethod
    def on_release(cls, key: TKey):
        for handler in cls.KEY_HANDLERS:
            handler.handle(key)


_KEYBOARD_LISTENER_STARTED = False


def keyboard_listener_start():
    global _KEYBOARD_LISTENER_STARTED
    if _KEYBOARD_LISTENER_STARTED:
        return

    listener = keyboard.Listener(
        on_press=KeyboardMonitor.on_press, on_release=KeyboardMonitor.on_release
    )
    listener.start()

    _KEYBOARD_LISTENER_STARTED = True
