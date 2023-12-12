# calibration_manager
A simple, ROS installable OR pure python package for keeping track of configuration and calibration data.

Calibrations are organized by machine setup, component, and time of the calibration in a file structure.
Thay may contain any standard python type, and will automatically load numpy arrays and pandas dataframes. 

A calibration is considered valid for a specific configuration, so a snapshot of the current cfg is stored in the calibration; this allows easy recall of a specific state for later analysis.

Once created, calibrations can be loaded and accessed as a dictionary:
```
import calibration_manager as cm

setup = cm.Setup('my_machine')
setup.save_example_cal()
components = setup.load()
pA = setup.cfg['example_component']['test_param_A']
cA = setup.cal['example_component']['test_cal_A']
arr = setup.cal['example_component']['test_array_B']
```
Don't forget that you can unpack all the dict keys into a function variable directly:
```
def func(test_param_A, test_array_B, **kwargs):
    return test_param_A + test_array_B

arr_B = func(**setup.cal['example_component'])
```

To save a new calibration, just construct a dictionary of your parameters and pass to cal:
```
my_np_array = np.random.rand(3,3)
my_calibration = {
    'A': 3.0,
    'B': True,
    'C': 'pinhole',
    'subsystem': {
        '1': my_np_array
    }
}
setup.save_component_cal('camera1', my_calibration)
```

If ros is installed (optional!) and the code has connection to a roscore, 
it can automatically upload parameters to the rosparam server.
If a ros_param_ns is provided in load(), all values in the cal.yaml will be loaded, or
if ros_param_ns is set to 'default', it will default to /{machine}/{component}/{params}.

Setups are stored in ~/.ros/setups/ by default, but this can overwritten with:
```
setup = cm.Setup('my_machine', '/my/setups/root/dir/')
```

Future features planned:
- when instantiating a component for the first time when no default_cfg is available, run a prompt to get the user input
- load from a SCOPS build folder
- allow datetime loading

Suggestions and commits are welcome.