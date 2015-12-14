import serial
from binascii import hexlify
import time


def decode_hex(raw):
    return int(raw.decode('ascii'), 16)


def encode_hex(n):
    return '{:02X}'.format(n).encode('ascii')


# FIXME: bit order swapped on error codes?
def ERR_EWARN(fl):
    return bool(fl & 1 << 5)


def ERR_RXOVR(fl):
    return bool(fl & 1 << 4)


def ERR_PASSIVE(fl):
    return bool(fl & 1 << 2)


def ERR_BUS(fl):
    return bool(fl & 1 << 0)


def error_names(fl):
    errs = []

    if ERR_EWARN(fl):
        errs.append('Error Warning')

    if ERR_RXOVR(fl):
        errs.append('Data overrun')

    if ERR_PASSIVE(fl):
        errs.append('Error-Passive')

    if ERR_BUS(fl):
        errs.append('Bus error')

    return errs


class CANMessage(object):
    FMT = {
        'x': '<CAN id 0x{0.ident:03x} data {0.data!r}>',
        'b': '<CAN id {0.ident:011b} data {0.data!r}>',
        'd': '<CAN id {0.ident:04d} data {0.data!r}>',
    }

    FMT_EX = {
        'x': '<xCAN id 0x{0.ident:08x} data {0.data!r}>',
        'b': '<xCAN id {0.ident:029b} data {0.data!r}>',
        'd': '<xCAN id {0.ident:09d} data {0.data!r}>',
    }

    MSG_TYPES = (ord('t'), ord('T'), ord('r'), ord('R'))

    def __init__(self, ident, data, extended=None):
        self.ident = ident
        self.data = data

        if extended is None:
            if self.ident > 0x7FF:
                self.extended = True
            else:
                self.extended = False
        else:
            self.extended = extended

    def __eq__(self, other):
        return self.ident == other.ident and self.data == other.data

    @classmethod
    def parse(cls, msg):
        if msg[0] == ord('T'):
            extended = True
            ident_len = 8
        elif msg[0] == ord('t'):
            extended = False
            ident_len = 3
        else:
            raise ValueError('Invalid Message: {!r}'.format(msg))

        msg_offset = 2 + ident_len
        ident = decode_hex(msg[1:msg_offset - 1])

        msg_len = decode_hex(msg[msg_offset - 1:msg_offset])

        if not len(msg) == msg_offset + msg_len * 2:
            raise ValueError('Broken message (message length): {!r}'.format(
                msg))

        data = decode_hex(msg[msg_offset:])

        return cls(ident, data, extended)

    def serialize(self):
        if self.extended:
            header_tpl = 'T{:08x}{:1x}'
        else:
            header_tpl = 't{:03x}{:1x}'

        header = header_tpl.format(self.ident, len(self.data)).encode('ascii')

        return header + hexlify(self.data)

    def format_msg(self, fmt='x'):
        tpl = self.FMT if not self.extended else self.FMT_EX
        return tpl[fmt].format(self)

    def __str__(self):
        return self.format_msg()


class USBtinError(Exception):
    pass


class USBTinCommandMixin(object):
    CHANNEL_MODES = {'open': b'O', 'listen': b'L', 'loopback': b'l', }

    def close_can_channel(self):
        self.transmit(b'C')

    def get_errors(self):
        err = self.transmit(b'F')
        assert err[0] == ord('F')

        return err[1]

    def get_firmware_version(self):
        return self.transmit(b'v')[1:].decode('ascii')

    def get_hardware_version(self):
        return self.transmit(b'V')[1:].decode('ascii')

    def get_serial_number(self):
        return self.transmit(b'N')[1:].decode('ascii')

    def set_can_baudrate(self, baudrate):
        if isinstance(baudrate, str):
            if not baudrate.startswith('S'):
                raise ValueError('Baudrate must be integer or one of S[0-8]')

            s_rate = int(baudrate[1:])
            if s_rate > 8:
                raise ValueError('Baudrate constant too large, must be <=8')

            msg = 'S{}'.format(s_rate)
            return self.transmit(msg.encode('ascii'))
        else:
            raise NotImplementedError('Exact baudrates not implemented')

    def open_can_channel(self, mode='open'):
        if mode not in self.CHANNEL_MODES:
            raise ValueError('Mode must be one of {}'.format(', '.join((
                self.CHANNEL_MODES.keys()))))

        self.transmit(self.CHANNEL_MODES[mode])

    def read_mcp2515(self, register_num):
        assert 0 <= register_num <= 255
        rv = self.transmit(b'G' + encode_hex(register_num))
        assert len(rv) == 1
        return decode_hex(rv)

    def set_timestamping(self, timestamping):
        self.transmit('Z1' if timestamping else 'Z0')

    def write_mcp2515(self, register_num, value):
        assert 0 <= register_num <= 255
        assert 0 <= value <= 255

        self.transmit(b'W' + encode_hex(register_num) + encode_hex(value))


class USBtinChannelMixin(object):
    def read_can_message(self):
        return CANMessage.parse(self.recv_can_message())

    def send_can_message(self, msg):
        self.transmit(msg.serialize())


class USBtin(USBTinCommandMixin, USBtinChannelMixin):
    def __init__(self, ser):
        self.ser = ser
        self.can_buf = []
        self.ctrl_buf = []

    def reset(self):
        # ensure bus is closed
        self.ser.write(b'C\r')
        self.ser.write(b'C\r')

        time.sleep(0.1)  # wait for device to catch up

        # set bus to non-blocking
        self.ser.timeout = 0

        # discard data on bus
        while self.ser.read(1):
            pass

        # back to blocking mode
        self.ser.timeout = None

        # FIXME: re-add later
        # # close CAN bus
        # self.set_timestamping(False)
        self.clear_flags()

    def clear_flags(self):
        # clear overflow register (see source of USBtin Java)
        self.write_mcp2515(0x2D, 0x00)

    def transmit(self, cmd):
        # transmit command
        self.ser.write(cmd + b'\r')
        return self.recv_ctrl_message()

    def recv_ctrl_message(self):
        if self.ctrl_buf:
            return self.ctrl_buf.pop(0)

        while True:
            msg = self._recv_message()

            if msg and msg[0] in CANMessage.MSG_TYPES:
                # buffer CAN messages
                self.can_buf.append(msg)
            else:
                return msg

    def recv_can_message(self):
        if self.can_buf:
            return self.can_buf.pop(0)

        while True:
            msg = self._recv_message()

            if not msg or msg[0] not in CANMessage.MSG_TYPES:
                self.ctrl_buf.append(msg)
            else:
                return msg

    def _recv_message(self, no_raise=False):
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
