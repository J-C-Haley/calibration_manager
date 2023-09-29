# calibration_manager
A simple, general purpose, ROS installable OR pure python package for keeping track of calibration data.

Calibrations are organized by machine, component, and time of the calibration in a file structure.
Thay may contain any standard python type, and will automatically load numpy arrays. 

Once created, calibrations can be loaded and accessed as a dictionary:
```
import calibration_manager as cm

cal = cm.Calibration('my_machine')
cal.load_all()
p = cal.cmp['my_parameter']
arr = cal.cmp['my_np_array']
```

If ros is installed (optional!) and the code has connection to a roscore, 
it will automatically upload parameters to the rosparam server
in /{my_machine}/{my_component}/{ros_params} (location can be overwritten).

To create an example calibration, run the following and look in ~/.ros/calibrations/:
```
cal.save_example_cal()
```

To save a new calibration, just construct a dictionary of your parameters and pass to cal:
```
my_np_array = np.random.rand(3,3)
my_calibration = {
    'A': 3.0,
    'B': True,
    'C': 'pinhole',
    subsystem = {
        '1': my_np_array
    }
}
cal.save('camera1', my_calibration)
```

Calibrations are stored in ~/.ros/calibrations/ by default, but this can overwritten with:
```
cal = cm.Calibration('my_machine', '/my/calibration/location/')
```