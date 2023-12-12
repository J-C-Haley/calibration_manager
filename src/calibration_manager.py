
import numpy as np
from ruamel.yaml import YAML; yaml=YAML()
import time
import logging
import pandas as pd
import pathlib
import shutil
import json

try:
    import rospy
    import rosgraph
    imports_ros = True
except:
    imports_ros = False

class Workspace:
    """
    A tool to flexibly store, load, and use configuration and calibration data for a machine workspace
    
    Each machine workspace has any number of named components, which store a current configuration, and a
    timeline history of calibrations (with the config at time of calibration)

    workspaces_root_dir: str path to either the current machine calibration storage location 
    (~/.ros/calibrations/, /networkdrive/calibrations, etc), 
    or a stored backup of the calibration ({build_name}/SCOPS/cal/)
    """
    def __init__(self,machine: str, workspaces_root_dir: str = '~/.ros/workspaces/'):
        self.machine = machine
        self.ws_root_dir = pathlib.Path(workspaces_root_dir)
        self.ws_root_dir = self.ws_root_dir.expanduser()
        self.machine_dir = self.ws_root_dir / self.machine
        
        self.cfg = {}
        self.cal = {}
        self.paths = {}

    def load(self, run_time_epoch: int = None, ros_param_ns: str = None):
        '''Loads all component configurations & calibrations of a machine workspace
        
        If a run_time_epoch is specified, the latest config/calibration preceeding the time will be loaded,
        otherwise the most recent config/calibration will be loaded.

        If a ros_param_ns is provided, all values in the cal.yaml will be loaded to the parameter server.
        If ros_param_ns is set to 'default', it will default to /{machine}/{component}/{params}
        If ros_param_ns is set to None, no parameters will be uploaded
        '''
        self.component_names = []
        for component_dir in self.machine_dir.iterdir():
            if not component_dir.is_dir():
                continue
            component_name = str(component_dir.name)
            self.load_component(component_name,run_time_epoch, ros_param_ns)
            self.component_names.append(component_name)
        return self.component_names
    
    def load_component(self, component_name: str, run_time_epoch: int = None, ros_param_ns: str = None):
        '''Load a single component to the machine workspace'''
        self.load_component_cfg(component_name,run_time_epoch, ros_param_ns)
        self.load_component_cal(component_name,run_time_epoch, ros_param_ns)

    def load_component_cfg(self, component_name: str, run_time_epoch: int = None, ros_param_ns: str = None, default_cfg: str = None):
        '''Load a single component's configuration to the machine workspace'''
        component_dir = self.machine_dir / (component_name+'/')
        component_dir.mkdir(parents=True,exist_ok=True)
        
        cal_dirs = [f for f in component_dir.iterdir() if (f.is_dir() and str(f.name).isdigit())]
        if run_time_epoch != None and len(cal_dirs) > 0:
            # Use cal_dir
            times = [int(str(f.name)) for f in cal_dirs]
            times.sort(reverse=True)
            for cal_time in times:
                if cal_time <= int(run_time_epoch):
                    break
            cal_dir = component_dir / str(cal_time)
            cfg_dir = cal_dir
        elif (component_dir / 'cfg' / 'cfg.yaml').exists():
            # try cfg dir
            cfg_dir = component_dir / 'cfg/'
        elif default_cfg != None and pathlib.Path(default_cfg).exists():
            logging.warning('WARNING: no prior configuration found, loading from defaults')
            cfg_dir = component_dir / 'cfg/'
            shutil.copytree(default_cfg,cfg_dir)
        else:
            logging.error('No configuration could be found')
            return
        
        self.cfg[component_name] = yaml.load(cfg_dir / 'cfg.yaml')

        if not component_name in self.paths:
            self.paths[component_name] = {}
        self.paths[component_name]['cfg'] = cfg_dir

        # load ros parameters to the the ros core if available
        if imports_ros and rosgraph.is_master_online() and ros_param_ns is not None:
            try: 
                if ros_param_ns == 'default':
                    ros_param_ns = f'/{self.machine}/{component_name}'
                rospy.set_param(ros_param_ns,json.loads(json.dumps(self.cfg[component_name]))) 
                # json recursively converts ordereddict to dict
            except Exception as ex: 
                logging.warning(f'failed to set ros params: {ex}')

        self.cfg[component_name] = load_to_dict(self.cfg[component_name],cfg_dir)

    def load_component_cal(self, component_name: str, run_time_epoch: int = None, ros_param_ns: str = None, default_cfg: str = None):
        '''Load a single component's calibration to the machine workspace'''
        component_dir = self.machine_dir / component_name
        component_dir.mkdir(parents=True,exist_ok=True)
        cal_dirs = [f for f in component_dir.iterdir() if (f.is_dir() and str(f.name).isdigit())]
        if run_time_epoch != None and len(cal_dirs) > 0:
            # Use cal_dir
            times = [int(str(f.name)) for f in cal_dirs]
            times.sort(reverse=True)
            for cal_time in times:
                if cal_time <= int(run_time_epoch):
                    break
            cal_dir = component_dir / str(cal_time)
        elif run_time_epoch == None and len(cal_dirs) > 0:
            times = [int(str(f.name)) for f in cal_dirs]
            times.sort(reverse=True)
            cal_time = times[0]
            cal_dir = component_dir / str(cal_time)
        else: 
            logging.warning('no calibration found')
            return
        
        self.cal[component_name] = yaml.load(cal_dir / 'cal.yaml')

        if not component_name in self.paths:
            self.paths[component_name] = {}
        self.paths[component_name]['cal'] = cal_dir

        # load ros parameters to the the ros core if available
        if imports_ros and rosgraph.is_master_online() and ros_param_ns is not None:
            try: 
                if ros_param_ns == 'default':
                    ros_param_ns = f'/{self.machine}/{component_name}'
                rospy.set_param(ros_param_ns,json.loads(json.dumps(self.cal[component_name])))
            except Exception as ex: 
                logging.warning(f'failed to set ros params: {ex}')

        self.cal[component_name] = load_to_dict(self.cal[component_name],cal_dir)

    def save_component_cfg(self, component_name: str, configuration: dict):
        '''Save a configuration for a single component - overwrites prior'''
        cfg_dir = self.machine_dir / component_name / 'cfg/'
        cfg_dir.mkdir(parents=True,exist_ok=True)

        configuration = save_from_dict(configuration,cfg_dir)

        yaml.dump(configuration, cfg_dir / 'cfg.yaml')
        logging.debug(f'configuration saved in {cfg_dir}')

    def save_component_cal(self, component_name: str, calibration: dict, overwrite: bool = False):
        '''Write calibration for a single component'''
        print(self.paths)
        if component_name not in self.paths:
            self.paths[component_name] = {}
        if overwrite and 'cal' in self.paths[component_name]:
            # overwrite cal
            cal_dir = pathlib.Path(self.paths[component_name]['cal'])
            logging.debug(f'overwriting cal {cal_dir}')
        else: # new cal
            cal_time = str(int(time.time()))
            cal_dir = self.machine_dir / component_name / cal_time
            cal_dir.mkdir(parents=True,exist_ok=True)
            self.paths[component_name]['cal'] = cal_dir
            logging.debug(f'creating new cal {cal_dir}')

        # save and replace objects with paths
        calibration = save_from_dict(calibration,cal_dir)

        yaml.dump(calibration, cal_dir / 'cal.yaml')
        if 'cfg' in self.paths[component_name]:
            shutil.copytree(self.paths[component_name]['cfg'],cal_dir,dirs_exist_ok=True)
        logging.debug(f'calibration written to {cal_dir}')

    def save_example_cal(self):
        '''Write out an example calibration for layout and testing'''
        logging.info('writing example calibration')
        cfg = {
            'test_param_A':1.6,
            'test_param_B':False,
        }
        cal = {
            'test_cal_A':1,
            'test_array_B': np.random.rand(3,3),
            'subcomponent':{
                'ros_param_C':5.0,
                'ros_param_D':True,
                'sub-subcomponent':{
                    'sub_param_A':33
                }
            }
        }
        self.save_component_cfg('example_component',cfg)
        self.save_component_cal('example_component',cal,overwrite=True)

def load_to_dict(d:dict,dir:pathlib.Path):
    for k, v in d.items():
        if isinstance(v,str):
            f = dir / v
            if f.is_file() and f.suffix == '.npy':
                d[k] = np.load(f)

            if f.is_file() and f.suffix == '.csv':
                d[k] = pd.read_csv(f)

        if isinstance(v, dict):
            d[k] = load_to_dict(v,dir)
    return d

def save_from_dict(d:dict,dir:pathlib.Path,file_ns:str=''):
    for k,v in d.items():
        if isinstance(v,pd.DataFrame):
            d[k] = file_ns+k+'.csv' # replaces key with csv path
            v.to_csv(str(dir / d[k])+'.csv')

        elif isinstance(v,np.ndarray):
            d[k] = file_ns+k+'.npy' # replaces key with npy path
            np.save(dir / d[k], v)

        elif isinstance(v,np.float):
            d[k] = float(d[k])

        elif isinstance(v, dict): # recurses
            d[k] = save_from_dict(v,dir,file_ns+str(k)+'+')
    return d

if __name__ == "__main__":
    ws = Workspace('test_machine')
    ws.save_example_cal()

    testcal = {
            'test_param_A':1,
            'cal_array_B': np.random.rand(2,2),
            'subcomponent':{
                'ros_param_C':5.0,
                'ros_param_D':True,
                'sub-subcomponent':{
                    'sub_param_A':np.random.rand(3,3),
                }
            }
        }
    ws.save_component_cal('example_component',testcal)
    ws.load()
    time.sleep(2)
    ws.save_component_cal('example_component',ws.cal['example_component'])

'''
TODO:
- when instantiating a component for the first time (loading from default_cfg), run a prompt to get the user input?
'''