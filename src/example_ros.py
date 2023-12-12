#!/usr/bin/env python3
'''
A quick demo of how to call the calibration manager from a ROS environment
'''

import rospy
import calibration_manager as cm
import numpy as np
import pandas as pd

if __name__ == '__main__':
    rospy.init_node('test_node')
    
    # Save a test calibration
    ws = cm.Workspace('my_machine')
    my_config = {
        'A': 3.0,
        'B': True,
        'C': 'pinhole',
        'subsystem': {
            '1': np.random.rand(3,3)
        },
    }
    my_calibration = {
        'flatfield': np.zeros((3,3)),
        'curve':pd.DataFrame({'x':[0,1,2],'y':[4,6,7]})
    }
    ws.save_component_cfg('my_camera', my_config)
    ws.save_component_cal('my_camera', my_calibration)

    # Load a calibration
    ws2 = cm.Workspace('my_machine')
    ws2.load()
    print('configuration loaded:')
    print(ws2.cfg['my_camera'])    
    print('calibration loaded:')
    print(ws2.cal['my_camera'])