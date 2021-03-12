import time
import logging
from PyQt5 import QtCore

import qcodes
import qcodes.logger as logger
from qcodes.logger import start_all_logging

from keysight_fpga.sd1.fpga_utils import \
    print_fpga_info, config_fpga_debug_log, print_fpga_log
from keysight_fpga.sd1.dig_iq import load_iq_image

from keysight_fpga.qcodes.M3202A_fpga import M3202A_fpga
from core_tools.drivers.M3102A import SD_DIG, MODES

from core_tools.HVI2.hvi2_schedule_loader import Hvi2ScheduleLoader
from core_tools.GUI.keysight_videomaps.liveplotting import liveplotting


from pulse_lib.base_pulse import pulselib

from PyQt5.QtCore import QTimer

#start_all_logging()
#logger.get_file_handler().setLevel(logging.DEBUG)

try:
    oldLoader.close_all()
except: pass
oldLoader = Hvi2ScheduleLoader

try:
    qcodes.Instrument.close_all()
except: pass


def init_pulselib(awgs):
    """
    return pulse library object

    Args:
        awgs : AWG instances you want to add (qcodes AWG object)
    """
    pulse = pulselib()

    # add to pulse_lib
    for i,awg in enumerate(awgs):
        pulse.add_awgs(awg.name, awg)

        # define channels
        if i == 0: # AWG-3
            pulse.define_channel(f'P1', awg.name, 1) # digitizer
            pulse.define_channel(f'P2', awg.name, 2) # digitizer
            pulse.define_marker(f'M3', awg.name, 3, setup_ns=50, hold_ns=50) # Scope
            pulse.define_channel(f'P4', awg.name, 4)
        elif i == 1: # AWG-7
            pulse.define_channel(f'B1', awg.name, 1)
            pulse.define_channel(f'B2', awg.name, 2) # Scope
            pulse.define_channel(f'B3', awg.name, 3) # digitizer
            pulse.define_marker(f'M4', awg.name, 4, setup_ns=50, hold_ns=50) # digitizer
        else:
            for ch in range(1,5):
                pulse.define_channel(f'{awg.name}.{ch}', awg.name, ch)
        pulse.define_marker(f'M{i+1}.T', awg.name, 0, setup_ns=50, hold_ns=50)

    pulse.finish_init()
    return pulse

class UpdateTimer(QtCore.QObject):

    def start(self, plotting):
        self.count = 0
        self.timer = QTimer(plotting)
        self.timer.timeout.connect(self.change_plot)
        self.timer.start(9000)
        plotting.destroyed.connect(self.stop_timer)

    def stop_timer(self):
        logging.info('Stop timer')
        self.timer.stop()

    def change_plot(self):
        self.count += 1
        logging.info(f'start #{self.count}')
        v = (plotting._2D_V1_swing.value() + 1)
        if v > 1100:
            v = 100

        plotting._2D_V1_swing.setValue(v)
        start = time.monotonic()
        plotting.update_plot_settings_2D()
        logging.info(f'restart duration {time.monotonic()- start:5.2f} s')


dig = SD_DIG("dig", 1, 6)
awg_slots = [3,7]
awgs = []
for i,slot in enumerate(awg_slots):
    awg = M3202A_fpga(f"AWG{i}", 1, slot)
    awg.set_hvi_queue_control(True)
    awgs.append(awg)


station = qcodes.Station()
station_name = 'Test'

for awg in awgs:
    station.add_component(awg)

station.add_component(dig)

dig_mode = MODES.AVERAGE
load_iq_image(dig.SD_AIN)
print_fpga_info(dig.SD_AIN)
dig.set_acquisition_mode(dig_mode)


logging.info('init pulse lib')
# load the AWG library
pulse = init_pulselib(awgs)


print('start gui')

logging.info('open plotting')
plotting = liveplotting(pulse, dig, "Keysight", cust_defaults={'gen':{'enabled_markers':['M3','M1.T']}})
plotting.move(222,0)
plotting.resize(1618,590)
plotting._2D_gate2_name.setCurrentIndex(1)
plotting._2D_t_meas.setValue(1)
plotting._2D_V1_swing.setValue(100)
plotting._2D_npt.setValue(80)

#updateTimer = UpdateTimer()
#updateTimer.start(plotting)
#plotting._2D_start_stop()

#%%

# station.close_all_registered_instruments()

#from V2_software.LivePlotting.data_getter.scan_generator_Virtual import fake_digitizer
#
#dig = fake_digitizer("fake_digitizer")
#pulse = return_pulse_lib_quad_dot(None)
#
#V2_liveplotting(pulse, dig)
