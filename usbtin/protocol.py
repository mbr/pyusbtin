from binascii import hexlify

from .exc import MessageParsingError, UnknownMessageTypeError
from .util import decode_hex, encode_hex


class USBtinMessage(object):
    is_ok = True
    is_can = False

    @classmethod
    def parse(cls, buf):
        try:
            if buf[0] == ord('t'):
                # handle most common message type, CAN messages, first
                return CANMessage.parse(buf)
            elif buf[0] == ord('T'):
                return CANExtendedMessage.parse(buf)
            elif buf[0] == ord('r'):
                return CANRequest.parse(buf)
            elif buf[0] == ord('R'):
                return CANExtendedRequest.parse(buf)
            elif buf == b'z\r' or buf == b'Z\r':
                return SendOk()
            elif buf == b'\r':
                return Ok()
            elif buf == b'\a':
                return Error()
            elif buf[0] == ord('v'):
                return FirmwareVersion.parse(buf)
            elif buf[0] == ord('V'):
                return HardwareVersion.parse(buf)
            elif buf[0] == ord('N'):
                return SerialNumber.parse(buf)
            elif buf[0] == ord('F'):
                return ErrorFlags.parse(buf)
            elif len(buf) == 3:
                return SingleByte.parse(buf)
            else:
                raise UnknownMessageTypeError(buf)
        except Exception as e:
            raise MessageParsingError(str(e))

    def __str__(self):
        return self.__class__.__name__


class _CANFrameBase(object):
    MAX_DATA = 8
    timestamp = None

    def __init__(self, ident, data):
        if not 0 <= ident <= self.MAX_IDENT:
            raise ValueError(
                'Identifier too large (max: {:X}, actual: {:X}'.format(
                    ident, self.MAX_IDENT))

        if not 0 <= len(data) <= self.MAX_DATA:
            raise ValueError('Too much data ({}), max is {} bytes'.format(
                len(data),
                self.MAX_DATA, ))

        self.ident = ident
        self.data = data

    def __bytes__(self):
        header = self.HEADER_TPL.format(self.ident,
                                        len(self.data)).encode('ascii')

        return header + hexlify(self.data)

    def __str__(self):
        return self.format_msg()

    def format_msg(self, fmt='x'):
        return self.FMT[fmt].format(self)

    @classmethod
    def parse_from_msg(cls, msg):
        msg_offset = 2 + cls.IDENT_LEN
        ident = decode_hex(msg[1:msg_offset - 1])

        msg_len = decode_hex(msg[msg_offset - 1:msg_offset])

        if not len(msg) == msg_offset + msg_len * 2 + 1:
            raise MessageParsingError(
                'Broken message (message length): {!r}'.format(msg))

        data = bytes(decode_hex(msg[i:i + 2])
                     for i in range(msg_offset, msg_offset + msg_len * 2, 2))

        return cls(ident, data)


class CANFrame(_CANFrameBase):
    IDENT_LEN = 3
    MAX_IDENT = 0x7FF
    HEADER_TPL = '{:03x}{:1x}'

    FMT = {
        'x': '<CAN id 0x{0.ident:03x} data {0.data!r}>',
        'b': '<CAN id {0.ident:011b} data {0.data!r}>',
        'd': '<CAN id {0.ident:04d} data {0.data!r}>',
    }


class CANExtendedFrame(_CANFrameBase):
    IDENT_LEN = 8
    MAX_IDENT = 0x1FFFFFFF
    HEADER_TPL = '{:08x}{:1x}'

    FMT = {
        'x': '<xCAN id 0x{0.ident:08x} data {0.data!r}>',
        'b': '<xCAN id {0.ident:029b} data {0.data!r}>',
        'd': '<xCAN id {0.ident:09d} data {0.data!r}>',
    }


class _CANBaseMessage(USBtinMessage):
    is_can = True

    @classmethod
    def parse(cls, msg):
        m = cls()
        m.frame = cls.FRAME_CLASS.parse_from_msg(msg)

        return m


class CANMessage(_CANBaseMessage):
    FRAME_CLASS = CANFrame


class CANExtendedMessage(_CANBaseMessage):
    FRAME_CLASS = CANExtendedFrame


class _CANBaseRequest(USBtinMessage):
    is_can = True

    @classmethod
    def parse(cls, msg):
        r = cls()
        r.ident = int(r[1:1 + cls.IDENT_LEN].decode('ascii'), 16)
        r.data_length = int(r[1 + cls.IDENT_LEN].decode('ascii'), 16)
        return r


class CANRequest(_CANBaseRequest):
    IDENT_LEN = 3


class CANExtendedRequest(_CANBaseRequest):
    IDENT_LEN = 8


class Ok(USBtinMessage):
    pass


class SendOk(USBtinMessage):
    pass


class Error(USBtinMessage):
    is_ok = False


class VersionString(USBtinMessage):
    @classmethod
    def parse(cls, buf):
        v = cls()
        v.major = decode_hex(buf[1:3])
        v.minor = decode_hex(buf[3:5])

        return v


class HardwareVersion(VersionString):
    pass


class FirmwareVersion(VersionString):
    pass


class SerialNumber(USBtinMessage):
    @classmethod
    def parse(cls, buf):
        v = cls()
        v.serial_number = buf[1:].decode('ascii')
        return v


class ErrorFlags(USBtinMessage):
    @classmethod
    def parse(cls, buf):
        fl = buf[1]

        e = cls()
        e.ERR_EWARN = bool(fl & 1 << 5)
        e.ERR_RXOVR = bool(fl & 1 << 4)
        e.ERR_PASSIVE = bool(fl & 1 << 2)
        e.ERR_BUS = bool(fl & 1 << 0)

        return e


class SingleByte(USBtinMessage):
    @classmethod
    def parse(cls, buf):
        val = cls()
        val.value = decode_hex(buf[1:2])
        return val


class USBtinCommand(object):
    def __str__(self):
        return bytes(self).decode('ascii')


class SetBaudrate(USBtinCommand):
    def __init__(self, baudrate):
        self.baudrate = baudrate

    def __bytes__(self):
        baudrate = self.baudrate

        if isinstance(baudrate, str):
            if not baudrate.startswith('S'):
                raise ValueError('Baudrate must be integer or one of S[0-8]')

            s_rate = int(baudrate[1:])
            if s_rate > 8:
                raise ValueError('Baudrate constant too large, must be <=8')

            cmd = 'S{}\r'.format(s_rate)
            return cmd.encode('ascii')
        else:
            raise NotImplementedError('Exact baudrates not implemented')


class Get2515Register(USBtinCommand):
    def __init__(self, register, value):
        if not 0 <= register <= 255:
            raise ValueError('Register must be inside [0-225]')

        self.register = register
        self.value = value

    def __bytes__(self):
        return b'G' + encode_hex(self.register) + b'\r'


class Set2515Register(USBtinCommand):
    def __init__(self, register, value):
        if not 0 <= register <= 255:
            raise ValueError('Register must be inside [0-225]')

        if not 0 <= value <= 255:
            raise ValueError('Register must be inside [0-225]')

        self.register = register
        self.value = value

    def __bytes__(self):
        return (
            b'W' + encode_hex(self.register) + encode_hex(self.value) + b'\r')


class ParameterLessCommand(USBtinCommand):
    def __bytes__(self):
        return self.CMD_SEQ


class GetHardwareVersion(ParameterLessCommand):
    CMD_SEQ = b'V\r'


class GetFirmwareVersion(ParameterLessCommand):
    CMD_SEQ = b'v\r'


class GetSerialNumber(ParameterLessCommand):
    CMD_SEQ = b'N\r'


class OpenCANChannel(ParameterLessCommand):
    CMD_SEQ = b'O\r'


class OpenListenChannel(ParameterLessCommand):
    CMD_SEQ = b'L\r'


class OpenLoopbackChannel(ParameterLessCommand):
    CMD_SEQ = b'l\r'


class CloseCANChannel(ParameterLessCommand):
    CMD_SEQ = b'C\r'


class ReadErrorFlags(ParameterLessCommand):
    CMD_SEQ = b'F\r'


class SetTimestamping(USBtinMessage):
    def __init__(self, state):
        self.state = state

    def __bytes__(self):
        if self.state:
            return b'Z1\r'
        return b'Z0\r'


class SetFilterMask(USBtinCommand):
    def __init__(self, mask):
        if not 0 <= mask <= 0x7FF:
            raise ValueError('Mask may at most have 11 bits')

        self.mask = mask

    def __bytes__(self):
        return 'm{:08X}\r'.format(self.mask).encode('ascii')


class SetFilterCode(USBtinCommand):
    def __init__(self, code):
        if not 0 <= code <= 0x7FF:
            raise ValueError('Code may at most have 11 bits')

        self.code = code

    def __bytes__(self):
        return 'M{:08X}\r'.format(self.code).encode('ascii')


class _SendCANFrameBase(USBtinCommand):
    def __init__(self, frame):
        self.frame = frame

    def __bytes__(self):
        return self.CMD + bytes(self.frame) + b'\r'

    @classmethod
    def with_frame(cls, ident, data):
        return cls(cls.FRAME_CLASS(ident, data))


class SendCANFrame(_SendCANFrameBase):
    FRAME_CLASS = CANFrame
    CMD = b't'


class SendCANExtendedFrame(_SendCANFrameBase):
    FRAME_CLASS = CANExtendedFrame
    CMD = b'T'


class _SendCANRequestBase(USBtinCommand):
    MAX_DATA_LEN = 8

    def __init__(self, ident, data_len):
        if not 0 <= ident <= self.MAX_IDENT:
            raise ValueError(
                'Identifier too large (max: {:X}, actual: {:X}'.format(
                    ident, self.MAX_IDENT))

        if not 0 <= data_len <= self.MAX_DATA_LEN:
            raise ValueError('data_len too large ({}), max is {} bytes'.format(
                data_len,
                self.MAX_DATA_LEN, ))

        self.ident = ident
        self.data_len = data_len

    def __bytes__(self):
        return self.MSG_TPL.format(self.ident, self.data_len).encode('ascii')


class SendCANRequest(_SendCANRequestBase):
    IDENT_LEN = 3
    MAX_IDENT = 0x1FFF
    MSG_TPL = 'r{:03x}{:1x}\r'


class SendCANExtendedRequest(_SendCANRequestBase):
    IDENT_LEN = 8
    MAX_IDENT = 0x1FFFFFFF
    MSG_TPL = 'R{:08x}{:1x}\r'
