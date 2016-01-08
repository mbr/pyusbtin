from contextlib import contextmanager, ExitStack
from binascii import hexlify

import time
from queue import Empty
import json
import sys

import click

from .ctx import open_channel
from .protocol import (SetBaudrate, GetFirmwareVersion, GetHardwareVersion,
                       GetSerialNumber, SendCANFrame, SendCANExtendedFrame,
                       SendCANRequest, SendCANExtendedRequest,
                       BAUDRATE_PRESETS)
from .threaded import USBtinThread

BAUD_INFO = {
    'S0': '10 kBaud',
    'S1': '20 kBaud',
    'S2': '50 kBaud',
    'S3': '100 kBaud',
    'S4': '125 kBaud',
    'S5': '250 kBaud',
    'S6': '500 kBaud',
    'S7': '800 kBaud',
    'S8': '1 MBaud',
}


@contextmanager
def json_writer(fn, mode='w'):
    with open(fn, mode) as out:
        need_sep = []

        out.write('[\n')

        def append_func(obj):
            if need_sep:
                out.write(',\n')
            else:
                need_sep.append(True)
            out.write('  ' + json.dumps(obj))

        try:
            yield append_func
        finally:
            out.write('\n]\n')


def detect_baudrate(usb_tin, timeout):
    print('Auto-detecting baudrate; {:.0f} ms timeout: '.format(timeout *
                                                                1000),
          end='',
          file=sys.stderr)

    for baudrate in BAUDRATE_PRESETS:
        print(baudrate, end=' ', file=sys.stderr)
        sys.stderr.flush()

        try:
            usb_tin.transmit_command(SetBaudrate(baudrate))
            with open_channel(usb_tin):
                usb_tin.recv_can_message(timeout=timeout)
            print('*', file=sys.stderr)
            break
        except Empty:
            continue
    else:
        baudrate = None
        print('all failed', file=sys.stderr)

    if baudrate is None:
        print('No packets detected, aborting', file=sys.stderr)
        sys.exit(1)

        time.sleep(timeout)

    return baudrate


# FIXME: copied over from portflakes
def parse_8bit(user_input):
    return user_input.encode('ascii').decode('unicode_escape').encode('latin1')


@click.group()
@click.argument('dev', type=click.Path(exists=True, dir_okay=False))
@click.option('--baudrate', '-b', default='S0')
@click.option('--detect-timeout', '-t', default=0.25)
@click.pass_context
def cli(ctx, dev, baudrate, detect_timeout):
    ctx.obj = obj = {}
    obj['dev'] = dev

    usb_tin = USBtinThread.open_device(dev)
    usb_tin.start()

    if baudrate == 'auto':
        baudrate = detect_baudrate(usb_tin, detect_timeout)

    # set initial baudrate
    usb_tin.transmit_command(SetBaudrate(baudrate))

    print("CAN Device: {}  Baudrate: {}".format(dev, BAUD_INFO.get(baudrate,
                                                                   baudrate)))
    obj['usb_tin'] = usb_tin


@cli.command()
@click.pass_obj
def info(obj):
    usb_tin = obj['usb_tin']

    v_hw = usb_tin.transmit_command(GetHardwareVersion())
    v_fw = usb_tin.transmit_command(GetFirmwareVersion())
    sn = usb_tin.transmit_command(GetSerialNumber())

    click.echo('Hardware Version: {0.major}.{0.minor}'.format(v_hw))
    click.echo('Firmware Version: {0.major}.{0.minor}'.format(v_fw))
    click.echo('Serial Number: {}'.format(sn.serial_number))


@cli.command()
@click.option('--delay', '-d', type=float, default=0.5)
@click.option('--id', '-i', type=int, default=0x123)
@click.option('--data', '-D', default=b'\x44\x55\x66', type=bytes)
@click.option('--data-len', '-n', default=0)
@click.option('--extended', '-E', is_flag=True)
@click.option('--rtr', '-r', is_flag=True)
@click.pass_obj
def send(obj, delay, id, data, extended, rtr, data_len):
    click.echo('Sending CAN packets, press C-c to abort...')

    usb_tin = obj['usb_tin']

    # build message
    if rtr:
        cls = (SendCANExtendedRequest if extended else SendCANRequest)
        msg = cls(id, data_len)
    else:
        cls = SendCANExtendedFrame if extended else SendCANFrame
        msg = cls.with_frame(id, data)

    with open_channel(usb_tin):
        while True:
            click.echo('Sending: {}'.format(msg))
            usb_tin.transmit_command(msg)
            time.sleep(delay)


@cli.command()
@click.option('--count', '-c', type=int)
@click.option('-j', '--json-file', type=click.Path())
@click.pass_obj
def dump(obj, count, json_file):
    usb_tin = obj['usb_tin']

    cleanup = ExitStack()

    if json_file:
        json_file = cleanup.enter_context(json_writer(json_file))

    with open_channel(usb_tin), cleanup:
        num_captured = 0
        while count is None or num_captured < count:

            msg = usb_tin.recv_can_message()

            if json_file:
                data = {'t': time.time(),
                        'msg': (msg.frame.ident,
                                hexlify(msg.frame.data).decode('ascii')), }
                json_file(data)

            click.echo(repr(msg))

            num_captured += 1
