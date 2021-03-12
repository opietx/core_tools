import logging

from keysight_fpga.qcodes.M3202A_fpga import FpgaAwgQueueingExtension

'''
Single shot HVI schedule.

The start time of this schedule is 5 to 10 ms faster for repeated starts than the original Hvi2SingleShot schedule,
because it keeps the HVI running and uses a start flag to restart the schedule.
The gain is bigger when more modules are being used.
'''

class Hvi2SingleShot():
    verbose = True

    name = "SingleShot"
    ''' Name of the script (class varriable) '''

    def __init__(self, configuration):
        '''
        Args:
            configuration (Dict[str,Any]):
                'n_waveforms' (int): number of waveforms per channel (only applies when hvi_queue_control=True)
                'n_triggers' (int): number of digitizer triggers
                'acquisition_delay_ns' (int):
                Time in ns between AWG output change and digitizer acquisition start.
                This also increases the gap between acquisitions.
                'digitizer_name':
                    'all_ch' (List[int]): all channels
                    'raw_ch' (List[int]): channels in raw mode
                    'ds_ch' (List[int]): channels in downsampler mode
                    'iq_ch' (List[int]): channels in IQ mode
                `awg_name`:
                    'active_los' (List[Tuple[int,int]]): pairs of (channel, LO).
                    'switch_los' (bool): whether to switch LOs on/off
                    'enabled_los' (List[List[Tuple[int,int]]): per switch interval list with (channel, active local oscillator).
                                  if None, then all los are switched on/off.
                    'hvi_queue_control' (bool): if True enables waveform queueing by hvi script.
                    'trigger_out' (bool): if True enables markers via Trigger Out channel.
        '''
        self._configuration = configuration.copy()

        self.started = False

        self._n_starts = 0
        self._acquisition_delay = int(configuration.get('acquisition_delay_ns', 0)/10) * 10


    def _module_config(self, seq, key):
        return self._configuration[seq.engine.alias][key]


    def _wait_state_clear(self, dig_seq, **kwargs):
        dig_seq.ds.set_state_mask(**kwargs)
        dig_seq.wait(10)
        dig_seq['channel_state'] = dig_seq.ds.state
        dig_seq.wait(20)

        with dig_seq.While(dig_seq['channel_state'] != 0):
            dig_seq['channel_state'] = dig_seq.ds.state
            dig_seq.wait(20)

    def _push_data(self, dig_seqs):
        for dig_seq in dig_seqs:
            ds_ch = self._module_config(dig_seq, 'ds_ch')
            if len(ds_ch) > 0:
                # NOTE: loop costs PXI registers. Better wait fixed time.
                dig_seq.wait(600)
    #            self._wait_state_clear(dig_seq, running=ds_ch)

                dig_seq.ds.control(push=ds_ch)
                dig_seq.wait(600)
    #            self._wait_state_clear(dig_seq, pushing=ds_ch)


    def sequence(self, sequencer, hardware):
        self.hardware = hardware
        n_triggers = self._configuration['n_triggers']

        self.r_start = sequencer.add_sync_register('start')
        self.r_stop = sequencer.add_sync_register('stop')
        self.r_nrep = sequencer.add_sync_register('n_rep')
        self.r_wave_duration = sequencer.add_module_register('wave_duration', module_type='awg')
        for awg in hardware.awgs:
            if self._configuration[awg.name]['hvi_queue_control']:
                for register in FpgaAwgQueueingExtension.get_registers():
                    sequencer.add_module_register(register, module_aliases=[awg.name])

        self.r_dig_wait = []
        self.r_awg_los_wait = []
        self.r_awg_los_duration = []
        for i in range(n_triggers):
            self.r_dig_wait.append(sequencer.add_module_register(f'dig_wait_{i+1}', module_type='digitizer'))
        self.r_awg_los_wait = {}
        self.r_awg_los_duration = {}
        for awg in hardware.awgs:
            if self._configuration[awg.name]['switch_los']:
                r_wait = []
                r_los = []
                self.r_awg_los_wait[awg.name] = r_wait
                self.r_awg_los_duration[awg.name] = r_los
                for i in range(n_triggers):
                    r_wait.append(sequencer.add_module_register(f'awg_los_wait_{i+1}', module_aliases=[awg.name]))
                    r_los.append(sequencer.add_module_register(f'awg_los_duration_{i+1}', module_aliases=[awg.name]))

        sequencer.add_module_register('channel_state', module_type='digitizer')

        sync = sequencer.main
        awg_seqs = sequencer.get_module_builders(module_type='awg')
        dig_seqs = sequencer.get_module_builders(module_type='digitizer')
        all_seqs = awg_seqs + dig_seqs

        with sync.Main():

            with sync.While(sync['stop'] == 0):

                with sync.While(sync['start'] == 1):

                    sync['start'] = 0

                    with sync.SyncedModules():
                        for awg_seq in awg_seqs:
                            if self._module_config(awg_seq, 'hvi_queue_control'):
                                awg_seq.queueing.queue_waveforms()
                            awg_seq.log.write(1)
                            awg_seq.start()
                            awg_seq.wait(1000)

                        for dig_seq in dig_seqs:
                            all_ch = self._module_config(dig_seq, 'all_ch')
                            ds_ch = self._module_config(dig_seq, 'ds_ch')

                            dig_seq.log.write(1)
                            dig_seq.start(all_ch)

                            if len(ds_ch) > 0:
                                dig_seq.wait(40)
                                dig_seq.trigger(ds_ch)

                    with sync.Repeat(sync['n_rep']):
                        with sync.SyncedModules():
                            for awg_seq in awg_seqs:
                                los = self._module_config(awg_seq, 'active_los')
                                awg_seq.log.write(2)
                                if len(los)>0:
                                    awg_seq.lo.reset_phase(los)
                                else:
                                    awg_seq.wait(10)
                                awg_seq.trigger()
                                if self._module_config(awg_seq, 'trigger_out'):
                                    awg_seq.marker.start()
                                    awg_seq.marker.trigger()
                                else:
                                    awg_seq.wait(20)
                                if self._module_config(awg_seq, 'switch_los'):
                                    enabled_los = self._module_config(awg_seq, 'enabled_los')
                                    # enable local oscillators
                                    for i in range(n_triggers):
                                        enabled_los_i = enabled_los[i] if enabled_los else los
                                        awg_seq.wait(awg_seq[f'awg_los_wait_{i+1}'])
                                        # start delay of instruction after wait_register is 0!
                                        awg_seq.lo.set_los_enabled(enabled_los_i, True)
                                        awg_seq.wait(awg_seq[f'awg_los_duration_{i+1}'])
                                        awg_seq.lo.set_los_enabled(enabled_los_i, False)

                                awg_seq.wait(awg_seq['wave_duration'])
                                if self._module_config(awg_seq, 'trigger_out'):
                                    awg_seq.marker.stop()

                            for dig_seq in dig_seqs:
                                iq_ch = self._module_config(dig_seq, 'iq_ch')
                                ds_ch = self._module_config(dig_seq, 'ds_ch')
                                raw_ch = self._module_config(dig_seq, 'raw_ch')

                                dig_seq.log.write(2)
                                if len(iq_ch) > 0:
                                    dig_seq.ds.control(phase_reset=iq_ch)
                                else:
                                    dig_seq.wait(10)

                                for i in range(n_triggers):
                                    dig_seq.wait(dig_seq[f'dig_wait_{i+1}'])
                                    if len(raw_ch) > 0:
                                        dig_seq.trigger(raw_ch)
                                    else:
                                        dig_seq.wait(10)
                                    dig_seq.wait(40)

                                    if len(ds_ch) > 0:
                                        dig_seq.ds.control(start=ds_ch)
                                    else:
                                        dig_seq.wait(10)


                    with sync.SyncedModules():
                        self._push_data(dig_seqs)
                        for seq in all_seqs:
                            seq.stop()

                # A simple statement after with sync.While(sync['start'] == 1).
                # The last statement inside with sync.While(sync['stop'] == 0) shouldn't
                # be a while loop, because this results in strange timing constraint in the compiler
                with sync.SyncedModules():
                    pass


    def _get_dig_trigger(self, hvi_params, i):
        warn = self._n_starts == 1
        try:
            return hvi_params[f'dig_trigger_{i+1}']
        except:
            if warn:
                logging.warning(f"Couldn't find HVI variable dig_trigger_{i+1}; trying dig_wait_{i+1}")
        try:
            return hvi_params[f'dig_wait_{i+1}']
        except:
            if i == 0:
                if warn:
                    logging.warning(f"Couldn't find HVI variable dig_wait_{i+1}; trying dig_wait")
                return hvi_params['dig_wait']
            else:
                if warn:
                    logging.warning(f"Couldn't find HVI variable dig_wait_{i+1}")
                raise


    def _set_wait_time(self, hvi_exec, register, value_ns):
        if value_ns < 0:
            # negative value results in wait time of 40 s.
            raise Exception(f'Invalid wait time {value_ns}')
        hvi_exec.write_register(register, int(value_ns/10))


    def start(self, hvi_exec, waveform_duration, n_repetitions, hvi_params):
        if self.started != hvi_exec.is_running():
            logging.warning(f'HVI running: {hvi_exec.is_running()}; started: {self.started}')
        if not self.started:
            logging.info('start hvi')
            hvi_exec.start()
            self.started = True

        self._n_starts += 1

        hvi_exec.write_register(self.r_nrep, n_repetitions)

        # update digitizer measurement time
        if 'averaging' in hvi_params and 't_measure'in hvi_params:
            for dig in self.hardware.digitizers:
                ds_ch = self._configuration[dig.name]['ds_ch']
                for ch in ds_ch:
                        dig.set_measurement_time_averaging(ch, hvi_params['t_measure'])

        for awg in self.hardware.awgs:
            if self._configuration[awg.name]['hvi_queue_control']:
                awg.write_queue_mem()

        # add 310 ns delay to start acquiring when awg signal arrives at digitizer.
        dig_offset = 310 + self._acquisition_delay
        tot_wait = -dig_offset
        for i in range(0, self._configuration['n_triggers']):
            t_trigger = self._get_dig_trigger(hvi_params, i)
            self._set_wait_time(hvi_exec, self.r_dig_wait[i], t_trigger - tot_wait)
            tot_wait = t_trigger + 80 # wait: +40 ns, wait_reg: +20 ns, wait: +10 ns, ds.control: +10 ns

        for awg in self.hardware.awgs:
            if self._configuration[awg.name]['switch_los']:
                tot_wait_awg = 20 # 20 ns for marker trigger, 10 ns awg trigger, -10 ns fpga_array_write
                for i in range(0, self._configuration['n_triggers']):
                    t_on = hvi_params[f'awg_los_on_{i+1}']
                    t_off = hvi_params[f'awg_los_off_{i+1}']
                    self._set_wait_time(hvi_exec, self.r_awg_los_wait[awg.name][i], t_on - tot_wait_awg)
                    tot_wait_awg = t_on + 30 # wait_reg: +30 ns, lo.set_los_enabled: +0 ns
                    self._set_wait_time(hvi_exec, self.r_awg_los_duration[awg.name][i], t_off - tot_wait_awg)
                    tot_wait_awg = t_off + 30
            else:
                tot_wait_awg = 0

        # add 250 ns for AWG and digitizer to get ready for next trigger.
            self._set_wait_time(hvi_exec, self.r_wave_duration.registers[awg.name],
                                waveform_duration + 250 - tot_wait_awg + self._acquisition_delay)

        hvi_exec.write_register(self.r_stop, 0)
        hvi_exec.write_register(self.r_start, 1)


    def stop(self, hvi_exec):
        logging.info(f'stop HVI')
        if self.started != hvi_exec.is_running():
            logging.warning(f'HVI running-1: {hvi_exec.is_running()}; started: {self.started}')
        self.started = False
        hvi_exec.write_register(self.r_stop, 1)
        hvi_exec.write_register(self.r_start, 1)
        if self.started != hvi_exec.is_running():
            logging.warning(f'HVI running-2: {hvi_exec.is_running()}; started: {self.started}')

