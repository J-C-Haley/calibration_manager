# calibration_manager
A simple, general purpose, ROS installable OR pure python package for keeping track of calibration data.

Calibrations are organized by machine, component, and time of the calibration in a file structure.
Thay may contain any standard python type, and will automatically load numpy arrays. 

Once created, calibrations can be loaded and accessed as a dictionary:
```
import calibration_manager as cm

ws = cm.Workspace('my_machine')
ws.save_example_cal()
components = ws.load()
pA = ws.cfg['example_component']['test_param_A']
cA = ws.cal['example_component']['test_cal_A']
arr = ws.cal['example_component']['test_array_B']
```
Don't forget that you can unpack all the dict keys into a function variable directly:
```
def func(test_param_A, test_array_B, **kwargs):
    return test_param_A + test_array_B

arr_B = func(**ws.cal['example_component'])
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
ws.save_component_cal('camera1', my_calibration)
```

If ros is installed (optional!) and the code has connection to a roscore, 
it can automatically upload parameters to the rosparam server.
If a ros_param_ns is provided in load(), all values in the cal.yaml will be loaded, or
if ros_param_ns is set to 'default', it will default to /{machine}/{component}/{params}.

Workspaces are stored in ~/.ros/workspaces/ by default, but this can overwritten with:
```
ws = cm.Workspace('my_machine', '/my/workspace/root/dir/')
```

Suggestions and commits are welcome.