class USBtinError(Exception):
    pass


class MessageParsingError(USBtinError):
    pass


class UnknownMessageTypeError(USBtinError):
    pass
