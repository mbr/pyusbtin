import time

import click

from .ctx import open_channel
from .protocol import (SetBaudrate, GetFirmwareVersion, GetHardwareVersion,
                       GetSerialNumber, SendCANFrame, SendCANExtendedFrame,
                       SendCANRequest, SendCANExtendedRequest)
from .threaded import USBtinThread


# FIXME: copied over from portflakes
def parse_8bit(user_input):
    return user_input.encode('ascii').decode('unicode_escape').encode('latin1')


@click.group()
@click.argument('dev', type=click.Path(exists=True, dir_okay=False))
@click.option('--baudrate', '-b', default='S0')
@click.pass_context
def cli(ctx, dev, baudrate):
    ctx.obj = obj = {}
    obj['dev'] = dev

    usb_tin = USBtinThread.open_device(dev)
    usb_tin.start()

    # set initial baudrate
    usb_tin.transmit_command(SetBaudrate(baudrate))

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
@click.pass_obj
def dump(obj, count):
    usb_tin = obj['usb_tin']

    with open_channel(usb_tin):
        num_captured = 0
        while count is None or num_captured < count:
            msg = usb_tin.recv_can_message()

            click.echo(msg)
            num_captured += 1
