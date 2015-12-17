class USBtinError(Exception):
    pass


class MessageParsingError(USBtinError):
    pass


class UnknownMessageTypeError(USBtinError):
    pass


class QueueNotEmptyError(USBtinError):
    pass


class RemoteError(USBtinError):
    pass
