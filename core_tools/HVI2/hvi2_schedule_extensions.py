import os
import logging

from keysight_fpga.qcodes.M3202A_fpga import (
        FpgaLocalOscillatorExtension, FpgaAwgQueueingExtension,
        FpgaTriggerOutExtension
        )
from keysight_fpga.sd1.fpga_utils import (
    FpgaSysExtension, FpgaLogExtension, FpgaNoLogExtension,
    get_fpga_image_path, has_fpga_info, FpgaMissingExtension
    )
from keysight_fpga.sd1.dig_iq import get_iq_image_filename, is_iq_image_loaded, FpgaDownsamplerExtension


def get_awg_image_filename(module):
    return os.path.join(get_fpga_image_path(module), 'awg_enhanced.k7z')


def add_extensions(hvi_system):
    for awg_engine in hvi_system.get_engines(module_type='awg'):
        logging.info(f'Adding {awg_engine.name} extensions')
        awg = awg_engine.module
        if has_fpga_info(awg):
            bitstream = get_awg_image_filename(awg)
            logging.info(f'{awg_engine.name} load symbols {bitstream}')
            awg_engine.load_fpga_symbols(bitstream)
            awg_engine.add_extension('sys', FpgaSysExtension)
            awg_engine.add_extension('log', FpgaLogExtension)
            awg_engine.add_extension('lo', FpgaLocalOscillatorExtension)
            awg_engine.add_extension('queueing', FpgaAwgQueueingExtension)
            awg_engine.add_extension('marker', FpgaTriggerOutExtension)
        else:
            for ext in ['sys']:
                awg_engine.add_extension(ext, FpgaMissingExtension)
            awg_engine.add_extension('log', FpgaNoLogExtension)

    for dig_engine in hvi_system.get_engines(module_type='digitizer'):
        logging.info(f'Adding {dig_engine.name} extensions')
        digitizer = dig_engine.module
        if not is_iq_image_loaded(digitizer):
            logging.warn(f'downsampler-iq FPGA image not loaded')

        if has_fpga_info(digitizer):
            dig_bitstream = get_iq_image_filename(digitizer)
            logging.info(f'{dig_engine.name} load symbols {dig_bitstream}')
            dig_engine.load_fpga_symbols(dig_bitstream)
            dig_engine.add_extension('sys', FpgaSysExtension)
            dig_engine.add_extension('log', FpgaLogExtension)
            dig_engine.add_extension('ds', FpgaDownsamplerExtension)
        else:
            for ext in ['sys']:
                dig_engine.add_extension(ext, FpgaMissingExtension)
            dig_engine.add_extension('log', FpgaNoLogExtension)

