from functools import partial
from core_tools.drivers.hardware.hardware import hardware as hw_parent

import qcodes as qc
import numpy as np
import copy

class gates(qc.Instrument):
	"""
	gates class, generate qcodes parameters for the real gates and the virtual gates
	It also manages the virtual gate matrix.
	"""
	def __init__(self, name ,hardware, dac_sources):
		'''
		gates object
		args:
			name (str) : name of the instrument
			hardware (class) : class describing the instrument (standard qtt issue, see example below to generate a gate set).
			dac_sources (list<virtual_dac>) : list with the dacs
		'''
		super(gates, self).__init__(name)

		if not isinstance(hardware, type(hw_parent())):
			raise ValueError('Please use the updated hardware class (see https://core-tools.readthedocs.io/ for more info).')

		self.hardware = hardware
		self.dac_sources = dac_sources

		self._gv = dict()
		self.v_gates = dict()

		# add gates:
		for gate_name, dac_location in self.hardware.dac_gate_map.items():
			self.add_parameter(gate_name, set_cmd = partial(self._set_voltage,  gate_name), get_cmd=partial(self._get_voltage,  gate_name), unit = "mV")

		# make virtual gates:
		for virt_gate_set in self.hardware.virtual_gates:
			self.v_gates[virt_gate_set.name] = list()
			for i in range(len(virt_gate_set)):
				if virt_gate_set.gates[i] in self.hardware.dac_gate_map.keys():
					gate_name = virt_gate_set.v_gates[i]
					self.v_gates[virt_gate_set.name].append(gate_name)
					self.add_parameter(gate_name, set_cmd = partial(self._set_voltage_virt, gate_name, virt_gate_set),
						get_cmd=partial(self._get_voltage_virt, gate_name, virt_gate_set), unit = "mV")

	def _set_voltage(self, gate_name, voltage):
		'''
		set a voltage to the dac
		Args:
			voltage (double) : voltage to set
			gate_name (str) : name of the gate to set
		'''
		dac_location = self.hardware.dac_gate_map[gate_name]
		if gate_name in self.hardware.boundaries.keys():
			min_voltage, max_voltage = self.hardware.boundaries[gate_name]
			if voltage < min_voltage or voltage > max_voltage:
				raise ValueError("Voltage boundaries violated, trying to set gate {} to {}mV. \nThe limit is set to {} to {} mV.\nThe limit can be changed by updating the hardware class".format(gate_name, voltage, min_voltage, max_voltage))

		getattr(self.dac_sources[dac_location[0]], f'dac{int(dac_location[1])}')(voltage)

	def _get_voltage(self, gate_name):
		'''
		get a voltage to the dac
		Args:
			gate_name (str) : name of the gate to set
		'''
		dac_location = self.hardware.dac_gate_map[gate_name]
		return getattr(self.dac_sources[dac_location[0]], f'dac{int(dac_location[1])}').cache()

	def _set_voltage_virt(self, gate_name, virt_gate_obj, voltage):
		'''
		set a voltage to the virtual dac
		Args:
			voltage (double) : voltage to set
			name : name of the real gate (that corresponds the certain virtual gate)
		'''
		names = list(self.gv.keys())
		current_voltages = list(self.gv.values())
		
		names_in_vg_matrix = list(set(names).intersection(virt_gate_obj.gates))
		red_virt_gates_obj = virt_gate_obj.reduce(names_in_vg_matrix)
		current_voltages_formatted = np.zeros([len(red_virt_gates_obj)])

		for i in range(len(red_virt_gates_obj)):
			current_voltages_formatted[i] = current_voltages[names.index(red_virt_gates_obj.gates[i])]

		voltage_key = red_virt_gates_obj.v_gates.index(gate_name)
		virtual_voltages =  np.matmul(red_virt_gates_obj.matrix,current_voltages_formatted)
		virtual_voltages[voltage_key] = voltage
		new_voltages = np.matmul(np.linalg.inv(red_virt_gates_obj.matrix), virtual_voltages)

		i = 0
		for gate_name in red_virt_gates_obj.gates:
			if new_voltages[i] != current_voltages_formatted[i]:
				self._set_voltage(gate_name,new_voltages[i])
			i+=1

	def _get_voltage_virt(self, gate_name, virt_gate_obj):
		'''
		get a voltage to the virtual dac
		Args:
			name : name of the real gate (that corresponds the certain virtual gate)
		'''

		names = list(self.gv.keys())
		current_voltages = list(self.gv.values())

		names_in_vg_matrix = list(set(names).intersection(virt_gate_obj.gates))
		red_virt_gates_obj = virt_gate_obj.reduce(names_in_vg_matrix)
		current_voltages_formatted = np.zeros([len(red_virt_gates_obj)])

		for i in range(len(red_virt_gates_obj)):
			current_voltages_formatted[i] = current_voltages[names.index(red_virt_gates_obj.gates[i])]

		voltage_key = red_virt_gates_obj.v_gates.index(gate_name)
		virtual_voltages =  np.matmul(red_virt_gates_obj.matrix,current_voltages_formatted)

		return virtual_voltages[voltage_key]

	def set_all_zero(self):
		'''
		set all dacs in the gate set to 0. Is ramped down 1 per 1
		'''
		print("In progress ..")
		for gate_name, dac_location in self.hardware.dac_gate_map.items():
			self._set_voltage(gate_name, 0)
		print("All gates set to 0!")

	@property
	def gv(self):
		'''
		get a dict with all the gate value of dacs (real values).
		Return:
			real_voltages (dict<str, double>): dict with gate name as key and the corresponding voltage as value
		'''
		for gate_name, my_dac_location in self.hardware.dac_gate_map.items():
			self._gv[gate_name] = self._get_voltage(gate_name)

		return copy.copy(self._gv)

	@gv.setter
	def gv(self, my_gv):
		'''
		setter for voltages
		'''
		names = list(my_gv.keys())
		voltages = list(my_gv.values())

		for i in range(len(names)):
			self._set_voltage(names[i], voltages[i])


if __name__ == '__main__':
	from core_tools.drivers.virtual_dac import virtual_dac
	from core_tools.drivers.hardware.hardware import hardware
	my_dac_1 = virtual_dac("dac_a", "virtual")
	my_dac_2 = virtual_dac("dac_b", "virtual")
	my_dac_3 = virtual_dac("dac_c", "virtual")
	my_dac_4 = virtual_dac("dac_d", "virtual")

	from core_tools.data.SQL.connect import set_up_local_storage, set_up_remote_storage, set_up_local_and_remote_storage
	set_up_local_storage('stephan', 'magicc', 'test', 'test_project1', 'test_set_up', 'test_sample')

	hw =  hardware()

	hw.dac_gate_map = {
	    # dacs for creating the quantum dots -- syntax, "gate name": (dac module number, dac index)
	    'B0': (0, 1), 'P1': (0, 2), 
	    'B1': (0, 3), 'P2': (0, 4),
	    'B2': (0, 5), 'P3': (0, 6), 
	    'B3': (0, 7), 'P4': (0, 8), 
	    'B4': (0, 9), 'P5': (0, 10),
	    'B5': (0, 11),'P6': (0, 12),
	    'B6': (0, 13), 'S6' : (0,14,),
	    'SD1_P': (1, 1), 'SD2_P': (1, 2), 
	    'SD1_B1': (1, 3), 'SD2_B1': (1, 4),
	    'SD1_B2': (1, 5), 'SD2_B2': (1, 6),}

	hw.boundaries = {'B0' : (0, 2000), 'B1' : (0, 2500)}
	hw.awg2dac_ratios.add(['P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'B0', 'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'S6', 'SD1_P', 'SD2_P'])
	hw.virtual_gates.add('test', ['B0', 'P1', 'B1', 'P2', 'B2', 'P3', 'B3', 'P4', 'B4', 'P5', 'B5', 'P6', 'B6', 'S6', 'SD1_P', 'SD2_P', 'COMP1'])

	my_gates = gates("my_gates", hw, [my_dac_1, my_dac_2, my_dac_3, my_dac_4])
	my_gates.vB0(1200)
	my_gates.vB0(1800)
	print(my_gates.vB0())
	print(my_gates.B0())
	# print(my_gates.v_gates)

	gv = my_gates.gv
	# print(my_gates.vB0())
	my_gates.set_all_zero()
	my_gates.gv = gv
	# print(my_gates.vB0())

	from core_tools.GUI.parameter_viewer_qml.param_viewer import param_viewer

	# if gates are not names gates, it needs to be provided as an argument.
	ui = param_viewer(my_gates)
