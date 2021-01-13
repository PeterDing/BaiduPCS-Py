from types import SimpleNamespace
from baidupcs_py.app.app import app as _app


def main():
    _app(obj=SimpleNamespace())
