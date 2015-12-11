import serial
from binascii import hexlify


class USBtinError(Exception):
    pass


class USBtin(object):
    def __init__(self, ser):
        self.ser = ser

    def reset(self):
        # clear stale messages
        for i in range(2):
            self.ser.write(b'v\r')
            self._read_message(no_raise=True)

        # close CAN bus
        self.close_can_channel()
        self.set_timestamping(False)

    def _read_message(self, no_raise=False):
        buf = b''
        while True:
            c = self.ser.read(1)

            if c == b'\x07':
                if no_raise:
                    return None

                raise USBtinError('Error (Status 0x07) {!r}'.format(c))

            if c == b'\r':
                return buf

            buf += c

    def close_can_channel(self):
        self.ser.write(b'C\r')
        if self._read_message(no_raise=True) is None:
            return False
        return True

    def get_firmware_version(self):
        self.ser.write(b'v\r')
        return self._read_message()[1:].decode('ascii')

    def get_hardware_version(self):
        self.ser.write(b'V\r')
        return self._read_message()[1:].decode('ascii')

    def get_serial_number(self):
        self.ser.write(b'N\r')
        return self._read_message()[1:].decode('ascii')

    def set_can_baudrate(self, baudrate):
        if isinstance(baudrate, str):
            if not baudrate.startswith('S'):
                raise ValueError('Baudrate must be integer or one of S[0-8]')

            s_rate = int(baudrate[1:])
            if s_rate > 8:
                raise ValueError('Baudrate constant too large, must be <=8')

            msg = 'S{}\r'.format(s_rate).encode('ascii')
            self.ser.write(msg)
            return self._read_message()
        else:
            raise NotImplementedError('Exact baudrates not implemented')

    def open_can_channel(self, listen_only=False):
        if listen_only:
            self.ser.write(b'L\r')
        else:
            self.ser.write(b'O\r')
        if self._read_message(no_raise=True) is None:
            return False
        return True

    def open_loopback_mode(self):
        self.ser.write(b'I\r')
        self._read_message()

    def read_mcp2515(self, register_num):
        self.ser.write(b'G' + self._to_hexbyte(register_num) + b'\r')
        return self._from_hexbyte(self._read_message())

    def transmit_standard(self, ident, data):
        if not 0 <= len(data) <= 8:
            raise ValueError('Maximum payload for standard frame is 8 bytes')

        if ident > 0x7FF:
            raise ValueError('Identifier out of range ([0;0x7FF]')

        ident_bs = '{:03X}'.format(ident).encode('ascii')
        buf = (b't' + ident_bs + str(len(data)).encode('ascii') + hexlify(data)
               + b'\r')
        print(repr(buf))

        self.ser.write(buf)
        rv = self._read_message()
        if not b'z' == rv:
            raise USBtinError('Failed to transmit. {!r}'.format(rv))

    def set_timestamping(self, timestamping):
        if timestamping:
            self.ser.write(b'Z1\r')
        else:
            self.ser.write(b'Z0\r')

        self._read_message()

    def write_mcp2515(self, register_num, value):
        self.ser.write(b'W' + self._to_hexbyte(register_num) +
                       self._to_hexbyte(value) + b'\r')
        self._read_message()

    def _to_hexbyte(self, value):
        if not 0 <= value <= 0xFF:
            raise ValueError('Value must be between 0x00 and 0xFF')
        return '{:02x}'.format(value).encode('ascii')

    def _from_hexbyte(self, raw):
        return int(raw.decode('ascii'), 16)

    @classmethod
    def open_device(cls, dev, baudrate=115200):
        return cls(serial.Serial(port=dev,
                                 baudrate=baudrate,
                                 bytesize=8,
                                 stopbits=1,
                                 parity=serial.PARITY_NONE,
                                 xonxoff=False,
                                 rtscts=False,
                                 dsrdtr=False, ))
