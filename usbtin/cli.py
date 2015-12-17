import time

import click

from .ctx import open_channel
from .protocol import (SetBaudrate, GetFirmwareVersion, GetHardwareVersion,
                       GetSerialNumber, SendCANFrame, SendCANExtendedFrame)
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
@click.option('--extended', '-E', is_flag=True)
@click.pass_obj
def test(obj, delay, id, data, extended):
    click.echo('Sending CAN packets, press C-c to abort...')

    usb_tin = obj['usb_tin']

    cmd_class = SendCANExtendedFrame if extended else SendCANFrame

    with open_channel(usb_tin):
        while True:
            msg = cmd_class.with_frame(id, data)
            click.echo('Sending frame: {}'.format(msg.frame))
            usb_tin.transmit_command(msg)
            time.sleep(delay)


@cli.command()
@click.option('--format',
              '-f',
              type=click.Choice(['x', 'b', 'd'], ),
              default='x')
@click.option('--count', '-c', type=int)
@click.pass_obj
def dump(obj, format, count):
    usb_tin = obj['usb_tin']

    with open_channel(usb_tin):
        num_captured = 0
        while count is None or num_captured < count:
            msg = usb_tin.recv_can_message()

            click.echo(msg.frame.format_msg(format))
            num_captured += 1


@cli.command()
@click.argument('ident', type=int)
@click.argument('data', type=parse_8bit)
@click.option('--receive', '-r', default=0, type=float)
@click.pass_obj
def send(obj, ident, data, receive):
    usb_tin = obj['usb_tin']

    msg = CANMessage(ident, data)
    click.echo('Sending {}'.format(msg))

    try:
        usb_tin.open_can_channel()
        if receive:
            click.echo('Receiving for {:.2f} seconds'.format(receive))

            count = 0
            start = time.time()
            while time.time() - start < receive:
                usb_tin.read_can_message()
                count += 1

            click.echo('Received {} CAN messages'.format(count))

        usb_tin.send_can_message(msg)
    finally:
        usb_tin.close_can_channel()
