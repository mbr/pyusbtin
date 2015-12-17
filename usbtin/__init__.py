from queue import Queue
from threading import Lock, Thread

import serial
import time

from .exc import QueueNotEmptyError, RemoteError
from .protocol import USBtinMessage, Set2515Register, SetTimestamping


class USBtinThread(Thread):
    POLL_FOR_STOP = 0.25

    def __init__(self, ser, reset=True):
        super(USBtinThread, self).__init__()
        self._thread.setDaemon(True)

        if reset:
            self._reset()

        self.ser = ser
        self.can_queue = Queue()
        self.ctrl_queue = Queue()
        self.send_lock = Lock()
        self.stopped = None

    def _reset(self):
        # NOT threadsafe!
        # ensure bus is closed
        self.ser.write(b'C\rC\r')

        time.sleep(0.1)  # wait for device to catch up

        # set bus to non-blocking
        self.ser.timeout = 0

        # discard data on bus
        while self.ser.read(1):
            pass

        # back to blocking with timeout mode
        self.ser.timeout = self.POLL_FOR_STOP

        self.write(SetTimestamping(False).serialize())
        self.write(Set2515Register(0x2D, 0x00).serialize())

    def run(self):
        # note: run may throw, blocking others
        while not self.stopped:
            buf = b''
            while True:
                c = self.ser.read(1)

                # timeout, recheck for stop
                if not c:
                    continue

                buf += c

                if c in b'\r\x07':
                    # FIXME: add timestamp
                    msg = USBtinMessage.parse(buf)

                    if msg.is_can:
                        self.can_queue.put(msg)
                    else:
                        self.ctrl_queue.put(msg)

                    buf = b''
                    continue

    def transmit_command(self, cmd):
        with self.send_lock:
            if not self.ctrl_queue.empty():
                raise QueueNotEmptyError('Control queue is not empty')

            self.write(bytes(cmd))
            response = self.ctrl_queue.get()

            if not response.is_ok:
                raise RemoteError(response)

            return response

    def stop(self):
        self.stopped = True

    @classmethod
    def open_device(cls, dev, baudrate=115200):
        instance = cls(serial.Serial(port=dev,
                                     baudrate=baudrate,
                                     bytesize=8,
                                     stopbits=1,
                                     parity=serial.PARITY_NONE,
                                     xonxoff=False,
                                     rtscts=False,
                                     dsrdtr=False, ))
        return instance
