
import numpy as np
from ruamel.yaml import YAML; yaml=YAML()
import time
import pathlib
from types import SimpleNamespace
import json

try:
    import rospy
    import rosgraph
    imports_ros = True
except:
    imports_ros = False

class Calibration:
    """
    A tool to flexibly store, load, and use calibration data for a machine
    
    Each machine has any number of named components, which store 

    calibration_dir: str path to either the current machine calibration storage location 
    (~/.ros/calibrations/, /networkdrive/calibrations, etc), 
    or a stored backup of the calibration ({build_name}/SCOPS/cal/)
    """
    def __init__(self,machine: str, calibration_dir: str = '~/.ros/calibrations/'):
        self.machine = machine
        self.cal_root_dir = pathlib.Path(calibration_dir) # TODO: test if need postpended /
        self.cal_root_dir = self.cal_root_dir.expanduser()
        self.machine_dir = self.cal_root_dir / self.machine

        if imports_ros and rosgraph.is_master_online():
            rospy.init_node('calibration_manager',anonymous=True)
            self.has_ros = True
        else:
            self.has_ros = False

    def load_all(self, run_time_epoch: int = None, upload_params=True, ros_param_ns: str = None):
        '''Loads all component calibrations of a machine
        
        If a run_time_epoch is specified, the latest calibration preceeding the time will be loaded per component,
        otherwise the most recent calibration will be loaded.

        If upload_params is True, all values in the cal.yaml will be loaded to the ros_param_ns.
        If ros_param_ns is not specified, it will default to /{machine}/{component}/{params}
        '''
        self.cmp = {}
        for component_dir in self.machine_dir.iterdir():
            if not component_dir.is_dir():
                continue
            component_name = str(component_dir.name)
            self.load(component_name,run_time_epoch,upload_params,ros_param_ns)           
            
    def load(self, component_name: str, run_time_epoch: int = None, upload_params=True, ros_param_ns: str = None):
        '''Load a single component to the machine calibration'''
        component_dir = self.machine_dir / component_name
            
        times = [int(str(f.name)) for f in component_dir.iterdir() if f.is_dir()]
        times.sort(reverse=True)
        if run_time_epoch == None:
            cal_time = times[0]
        else:
            for cal_time in times:
                if cal_time <= int(run_time_epoch):
                    break
        cal_dir = component_dir / str(cal_time)
        self.cmp[component_name] = yaml.load(cal_dir / 'cal.yaml')

        # load ros parameters to the the ros core if available
        if self.has_ros and upload_params:
            try: 
                if ros_param_ns == None:
                    ros_param_ns = f'/{self.machine}/{component_name}'
                rospy.set_param(ros_param_ns,json.loads(json.dumps(self.cmp[component_name]))) 
                # json recursively converts ordereddict to dict
            except Exception as ex: 
                print('failed to set ros params:')
                print(ex)

        # load numpy arrays by replacing file paths in dict with loaded arrays
        def load_np(d:dict,cal_dir:pathlib.Path):
            for k, v in d.items():
                if isinstance(v,str):
                    f = cal_dir / v
                    if f.is_file() and f.suffix == '.npy':
                        d[k] = np.load(f)
                if isinstance(v, dict):
                    d[k] = load_np(v,cal_dir)
            return d
        self.cmp[component_name] = load_np(self.cmp[component_name],cal_dir)

    def save_component(self, component_name: str, calibration: dict):
        '''Write a new calibration for a single component'''
        cal_time = str(int(time.time()))
        cal_dir = self.machine_dir / component_name / cal_time
        cal_dir.mkdir(parents=True,exist_ok=True)

        # save and replace np arrays with paths
        def replace_np(d:dict,cal_dir:pathlib.Path):
            for k,v in d.items():
                if isinstance(v,np.ndarray):
                    np.save(cal_dir / k, v)
                    d[k] = k+'.npy' # replace key with path
                if isinstance(v, dict):
                    d[k] = replace_np(v,cal_dir)
            return d
        calibration = replace_np(calibration,cal_dir)

        yaml.dump(calibration, cal_dir / 'cal.yaml')
        print(f'calibration written to {cal_dir}')

    def save_example_cal(self):
        '''Write out an example calibration for layout and testing'''
        print('writing example calibration')
        component = 'example_component'
        cal_time = str(int(time.time()))
        cal = {
            'test_param_A':1,
            'cal_array_B': np.random.rand(3,3),
            'subcomponent':{
                'ros_param_C':5.0,
                'ros_param_D':True,
                'sub-subcomponent':{
                    'sub_param_A':33
                }
            }
        }
        cal_dir = self.machine_dir / component / cal_time
        cal_dir.mkdir(parents=True,exist_ok=True)
        self.save_component(component,cal)

if __name__ == "__main__":
    cal = Calibration('test_machine')
    cal.save_example_cal()

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
    cal.save_component('example_component_2',testcal)
    cal.load_all()
    time.sleep(2)
    cal.save_component('example_component_2',cal.cmp['example_component_2'])