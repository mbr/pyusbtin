#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os

from setuptools import setup, find_packages


def read(fname):
    buf = open(os.path.join(os.path.dirname(__file__), fname), 'rb').read()
    return buf.decode('utf8')


setup(name='usbtin',
      version='0.2.dev1',
      description='Python driver for Thomas Fischl\'s USBtin',
      long_description=read('README.rst'),
      author='Marc Brinkmann',
      author_email='git@marcbrinkmann.de',
      url='https://github.com/mbr/pyusbtin',
      license='MIT',
      packages=find_packages(exclude=['tests']),
      install_requires=['click', 'pyserial'],
      entry_points={
          'console_scripts': [
              'pyusbtin = usbtin.cli:cli',
          ],
      },
      classifiers=[
          'Programming Language :: Python :: 3',
      ])
