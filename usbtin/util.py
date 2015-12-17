def decode_hex(raw):
    return int(raw.decode('ascii'), 16)


def encode_hex(n):
    return '{:02X}'.format(n).encode('ascii')
