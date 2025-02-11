from core_tools.data.SQL.SQL_common_commands import execute_statement, execute_query
from core_tools.data.SQL.SQL_common_commands import select_elements_in_table, insert_row_in_table, update_table
from core_tools.data.SQL.queries.dataset_creation_queries import data_table_queries
from core_tools.data.SQL.SQL_utility import text, generate_uuid, N_to_n
from core_tools.data.SQL.connect import SQL_conn_info_local, sample_info

import psycopg2, json
import numpy as np

class sync_mgr_queries:
	@staticmethod
	def get_sync_items_meas_table(sync_agent):
		'''
		returns:
			meaurments <list<long>> : list of uuid's who's table entries need a sync
		'''
		res = select_elements_in_table(sync_agent.conn_local, "global_measurement_overview",
			('uuid', ), where=("table_synchronized",False), dict_cursor=False)
		
		uuid_entries = list(sum(res, ()))
		uuid_entries.sort()
		return uuid_entries

	@staticmethod 
	def sync_table(sync_agent, uuid):
		'''
		syncs row in the table to the remote for the given uuid
		'''
		# check if uuid exists
		entry_exists = select_elements_in_table(sync_agent.conn_remote, "global_measurement_overview",
			('uuid', ), where=("uuid",uuid), dict_cursor=False)

		local_content = select_elements_in_table(sync_agent.conn_local, "global_measurement_overview",
			('*', ), where=("uuid",uuid), dict_cursor=True)[0]
		sync_mgr_queries.convert_SQL_raw_table_entry_to_python(local_content)

		del local_content['id']
		local_content['table_synchronized'] = True
		

		if len(entry_exists) == False:
			insert_row_in_table(sync_agent.conn_remote, 'global_measurement_overview',
				tuple(local_content.keys()), tuple(local_content.values()))
		else:
			remote_content = select_elements_in_table(sync_agent.conn_remote, "global_measurement_overview",
				('*', ), where=("uuid",uuid), dict_cursor=True)[0]
			sync_mgr_queries.convert_SQL_raw_table_entry_to_python(remote_content)
			
			del remote_content['id']

			content_to_update = dict()

			for key in remote_content.keys():
				if local_content[key] != remote_content[key]:
					content_to_update[key] = local_content[key]

			update_table(sync_agent.conn_remote, 'global_measurement_overview',
				content_to_update.keys(), content_to_update.values(),
				condition=("uuid",uuid))

		update_table(sync_agent.conn_local, 'global_measurement_overview',
				('table_synchronized', ), (True, ),
				condition=("uuid",uuid))

		sync_agent.conn_local.commit()
		sync_agent.conn_remote.commit()

	@staticmethod
	def get_sync_items_raw_data(sync_agent):
		'''
		returns:
			meaurments <list<long>> : list of uuid's where the data needs to be updated of.
		'''
		res = select_elements_in_table(sync_agent.conn_local, "global_measurement_overview",
			('uuid', ), where=('data_synchronized',False), dict_cursor=False)

		uuid_entries = list(sum(res, ()))
		uuid_entries.sort()
		return uuid_entries

	@staticmethod
	def sync_raw_data(sync_agent, uuid):
		raw_data_table_name = select_elements_in_table(sync_agent.conn_local, 
			'global_measurement_overview', ('exp_data_location', ), 
			where=("uuid",uuid), dict_cursor=False)[0][0]

		data_table_queries.generate_table(sync_agent.conn_local, raw_data_table_name)
		sync_mgr_queries._sync_raw_data_table(sync_agent, raw_data_table_name)
		
		update_table(sync_agent.conn_local, 'global_measurement_overview',
				('data_synchronized', ), (True, ),
				condition=("uuid",uuid))
		sync_agent.conn_local.commit()
		
		sync_mgr_queries._sync_raw_data_lobj(sync_agent, raw_data_table_name)

	@staticmethod
	def _sync_raw_data_table(sync_agent, raw_data_table_name):
		n_row_loc = select_elements_in_table(sync_agent.conn_local, raw_data_table_name,
			(psycopg2.sql.SQL('COUNT(*)'), ), dict_cursor=False)[0][0]

		table_name = execute_query(sync_agent.conn_remote, 
			"SELECT to_regclass('{}.{}');".format('public', raw_data_table_name))[0][0]

		n_row_rem = 0
		if table_name is not None:
			n_row_rem = select_elements_in_table(sync_agent.conn_remote, raw_data_table_name,
				(psycopg2.sql.SQL('COUNT(*)'), ), dict_cursor=False)[0][0]

		if n_row_loc != n_row_rem or table_name == None:
			get_rid_of_table = "DROP TABLE IF EXISTS {} ; ".format(raw_data_table_name)
			execute_statement(sync_agent.conn_remote, get_rid_of_table)
						
			data_table_queries.generate_table(sync_agent.conn_remote, raw_data_table_name)

			res_loc = select_elements_in_table(sync_agent.conn_local, raw_data_table_name, ('*', ), order_by=('id', ''))

			for result in res_loc:
				lobject = sync_agent.conn_remote.lobject(0,'w')
				del result['id']
				result['oid'] = lobject.oid
				result['write_cursor'] = 0
				result['depencies'] = json.dumps(result['depencies'])
				result['shape'] = json.dumps(result['shape'])
				insert_row_in_table(sync_agent.conn_remote, raw_data_table_name, 
					result.keys(), result.values())

		sync_agent.conn_remote.commit()

	@staticmethod
	def _sync_raw_data_lobj(sync_agent, raw_data_table_name):
		res_loc = select_elements_in_table(sync_agent.conn_local, raw_data_table_name,
			('write_cursor', 'total_size', 'oid'), order_by=('id', ''))
		res_rem = select_elements_in_table(sync_agent.conn_remote, raw_data_table_name,
			('write_cursor', 'total_size', 'oid'), order_by=('id', ''))
		
		for i in range(len(res_loc)):
			r_cursor = res_rem[i]['write_cursor']
			l_cursor = res_loc[i]['write_cursor']
			r_oid = res_rem[i]['oid']
			l_oid = res_loc[i]['oid']
			l_lobject = sync_agent.conn_local.lobject(l_oid,'rb')
			r_lobject = sync_agent.conn_remote.lobject(r_oid,'wb')

			while (r_cursor != l_cursor):
				l_lobject.seek(r_cursor*8)
				r_lobject.seek(r_cursor*8)
				if l_cursor*8 - r_cursor*8 < 2_000_000:
					mybuffer = np.frombuffer(l_lobject.read(l_cursor*8-r_cursor*8))
					r_cursor = l_cursor
				else:
					print(f'large dataset, {(l_cursor*8-r_cursor*8)*1e-9}GB')
					mybuffer = np.frombuffer(l_lobject.read(2_000_000))
					r_cursor += int(2_000_000/8)
				r_lobject.write(mybuffer.tobytes())

			r_lobject.close()
			l_lobject.close()

			update_table(sync_agent.conn_remote, raw_data_table_name, 
				('write_cursor',), (l_cursor,), condition=('oid',r_oid))

		sync_agent.conn_remote.commit()

	@staticmethod
	def convert_SQL_raw_table_entry_to_python(content):
		content['keywords'] = psycopg2.extras.Json(content['keywords'])
		content['start_time'] = psycopg2.sql.SQL("TO_TIMESTAMP({})").format(psycopg2.sql.Literal(content['start_time'].timestamp()))

		if content['snapshot'] is not None:
			content['snapshot'] = str(content['snapshot'].tobytes()).replace('\\\'', '').replace('\\\\\"', '')
			if content['snapshot'].startswith('b'):
				content['snapshot'] = content['snapshot'][1:]
			if content['snapshot'].startswith('\''):
				content['snapshot'] = content['snapshot'][1:-1]
			content['snapshot'] = psycopg2.extras.Json(json.loads(content['snapshot']))
		if content['metadata'] is not None:
			content['metadata'] = str(content['metadata'].tobytes()).replace('\\\'', '')
			if content['metadata'].startswith('b'):
				content['metadata'] = content['metadata'][1:]
			if content['metadata'].startswith('\''):
				content['metadata'] = content['metadata'][1:-1]
			content['metadata'] = psycopg2.extras.Json(json.loads(content['metadata']))

		if content['stop_time'] is not None:
			content['stop_time'] = psycopg2.sql.SQL("TO_TIMESTAMP({})").format(psycopg2.sql.Literal(content['stop_time'].timestamp()))

if __name__ == '__main__':
	from core_tools.data.SQL.connect import set_up_local_storage, set_up_remote_storage, set_up_local_and_remote_storage
	set_up_local_storage('stephan', 'magicc', 'test', 'test_project', 'test_set_up', 'test_sample')
	set_up_local_and_remote_storage('131.180.205.81', 5432, 'stephan', 'magicc', 'test',
		'stephan_test', 'magicc', 'spin_data_test', 'test_project', 'test_set_up', 'test_sample')

	set_up_local_and_remote_storage('131.180.205.81', 5432,
	"xld_user", "XLDspin001", "vandersypen_data",
	'xld_measurement_pc', 'XLDspin001', 'sixdots',
	 "6dot", "XLD", "6D3S - SQ20-20-5-18-4")
	from core_tools.data.SQL.SQL_connection_mgr import SQL_sync_manager
	s = SQL_sync_manager()

	e = sync_mgr_queries.get_sync_items_meas_table(s)
	# sync_mgr_queries.sync_raw_data(s,e[11049])

	i = 0
	for uuid in e:
		print(i)
		# sync_mgr_queries.sync_raw_data(s,uuid)
		sync_mgr_queries.sync_table(s, uuid)
		i+= 1
	# # e = sync_mgr_queries.get_sync_items_raw_data(s)
	# # print(e)
	# sync_mgr_queries.sync_raw_data(s, e[-1])