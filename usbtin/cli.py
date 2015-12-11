from binascii import hexlify
import time

import click

from . import USBtin


@click.group()
@click.argument('dev', type=click.Path(exists=True, dir_okay=False))
@click.option('--baudrate', '-b', default='S0')
@click.pass_context
def cli(ctx, dev, baudrate):
    ctx.obj = obj = {}
    obj['dev'] = dev
    usb_tin = USBtin.open_device(dev)
    usb_tin.reset()
    usb_tin.set_can_baudrate(baudrate)

    obj['usb_tin'] = usb_tin


@cli.command()
@click.pass_obj
def info(obj):
    usb_tin = obj['usb_tin']

    click.echo('Hardware Version: {}'.format(usb_tin.get_hardware_version()))
    click.echo('Firmware Version: {}'.format(usb_tin.get_firmware_version()))
    click.echo('Serial Number: {}'.format(usb_tin.get_serial_number()))


@cli.command()
@click.option('--delay', '-d', type=float, default=0.5)
@click.option('--id', '-i', type=int, default=0x123)
@click.option('--data', '-D', default=b'\x44\x55\x66', type=bytes)
@click.pass_obj
def test(obj, delay, id, data):
    click.echo('Sending CAN packets, press C-c to abort...')

    usb_tin = obj['usb_tin']

    try:
        usb_tin.open_can_channel()

        while True:
            click.echo('ID {}, data [hex] {}'.format(id, hexlify(data).decode(
                'ascii')))
            usb_tin.transmit_standard(id, data)
            time.sleep(delay)
    finally:
        usb_tin.close_can_channel()


@cli.command()
@click.option('--format',
              '-f',
              type=click.Choice(['x', 'b', 'd'], ),
              default='x')
@click.option('--count', '-c', type=int)
@click.pass_obj
def dump(obj, format, count):
    usb_tin = obj['usb_tin']

    try:
        usb_tin.open_can_channel(listen_only=True)

        num_captured = 0
        while count is None or num_captured < count:
            click.echo(usb_tin.receive_message().format_msg(format))
            num_captured += 1

    finally:
        usb_tin.close_can_channel()
