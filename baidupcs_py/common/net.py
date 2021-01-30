import random
import socket


def avail_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) != 0


def random_avail_port(start: int, end: int) -> int:
    while True:
        port = random.randint(start, end)
        if avail_port(port):
            return port
