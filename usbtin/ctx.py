from contextlib import contextmanager

from .protocol import CloseCANChannel, OpenCANChannel


@contextmanager
def open_channel(can):
    can.transmit_command(OpenCANChannel())
    try:
        yield
    finally:
        can.transmit_command(CloseCANChannel())
