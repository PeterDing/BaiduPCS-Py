import os

from setuptools import setup
from Cython.Build import cythonize
from distutils.command.build_ext import build_ext


def build(setup_kwargs):
    extensions = ["baidupcs_py/common/simple_cipher.pyx"]

    # gcc arguments hack: enable optimizations
    os.environ["CFLAGS"] = "-O3"

    ext_modules = cythonize(
        extensions,
        language_level=3,
        compiler_directives={"linetrace": True},
    )

    ext_modules[0].name = "baidupcs_py.common.simple_cipher"

    # Build
    setup_kwargs.update(
        {
            "ext_modules": ext_modules,
            "cmdclass": {"build_ext": build_ext},
        }
    )


if __name__ == "__main__":
    setup_kwargs = {}
    build(setup_kwargs)
    setup(**setup_kwargs)
