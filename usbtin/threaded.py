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
        self.setDaemon(True)
        self.ser = ser
        self.can_queue = Queue()
        self.ctrl_queue = Queue()
        self.send_lock = Lock()
        self.stopped = None

        if reset:
            self._reset()

    def _reset(self):
        # NOT threadsafe!
        # ensure bus is closed
        self.ser.write(b'C\rC\r')

        # set bus to low timeout to clear
        self.ser.timeout = 0.2

        # write commands
        self.ser.write(bytes(SetTimestamping(False)))
        self.ser.write(bytes(Set2515Register(0x2D, 0x00)))

        # discard data on bus
        while self.ser.read(1):
            # buf = self.ser.read(1)
            # if not buf:
            #     break
            # print('READ', buf)
            pass

        # back to blocking with timeout mode
        self.ser.timeout = self.POLL_FOR_STOP

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

            self.ser.write(bytes(cmd))
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
