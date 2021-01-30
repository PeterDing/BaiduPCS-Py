from functools import wraps
from threading import Semaphore


def sure_release(semaphore: Semaphore, func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    finally:
        semaphore.release()


def retry(times: int):
    """Retry times when func fails"""

    def wrap(func):
        @wraps(func)
        def retry_it(*args, **kwargs):
            nonlocal times
            if times < 0:  # forever
                times = 1 << 32

            for i in range(1, times + 1):
                try:
                    r = func(*args, **kwargs)
                    return r
                except Exception as err:
                    if i == times:
                        raise err

        return retry_it

    return wrap
