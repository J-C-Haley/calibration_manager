from setuptools import setup
import os
from glob import glob

package_name = 'calibration_manager'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ("share/" + package_name, ["plugin.xml"]),
        ("share/" + package_name + "/resource", ["resource/SetupManager.ui"]),
        (os.path.join('share', package_name, 'launch'), glob(os.path.join('launch', '*launch.[pxy][yma]*'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='J-C-Haley',
    maintainer_email='jchaley42@gmail.com',
    description='A simple, ROS installable OR pure python package for keeping track of configuration and calibration data',
    license='BSD',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
        ],
    },
)