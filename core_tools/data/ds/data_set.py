from core_tools.data.ds.data_set_core import data_set_raw, data_set
from core_tools.data.SQL.SQL_database_mgr import SQL_database_manager

def load_by_id(exp_id):
    '''
    load a dataset by specifying its id (search in local db)

    args:
        exp_id (int) : id of the experiment you want to load
    '''
    SQL_mgr = SQL_database_manager()
    return data_set(SQL_mgr.fetch_raw_dataset_by_Id(exp_id))

def load_by_uuid(exp_uuid):
    '''
    load a dataset by specifying its uuid (searches in local and remote db)

    args:
        exp_uuid (int) : uuid of the experiment you want to load
    '''
    SQL_mgr = SQL_database_manager()
    return data_set(SQL_mgr.fetch_raw_dataset_by_UUID(exp_uuid))

def create_new_data_set(experiment_name, *m_params):
    '''
    generates a dataclass for a given set of measurement parameters

    Args:
        *m_params (m_param_dataset) : datasets of the measurement parameters
    '''
    ds = data_set_raw(exp_name=experiment_name)

    # intialize the buffers for the measurement
    for m_param in m_params:
        m_param.init_data_dataclass()
        ds.measurement_parameters += [m_param]
        ds.measurement_parameters_raw += m_param.to_SQL_data_structure()

    SQL_mgr = SQL_database_manager()
    SQL_mgr.register_measurement(ds)

    return data_set(ds)