from threading import Semaphore


def sure_release(semaphore: Semaphore, func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    finally:
        semaphore.release()
