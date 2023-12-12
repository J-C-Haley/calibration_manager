# THIS IS FOR ROS CATKIN BUILD, DO NOT RUN MANUALLY
from distutils.core import setup
from catkin_pkg.python_setup import generate_distutils_setup
d = generate_distutils_setup(
    packages=['calibration_manager.py'],
    package_dir={'': 'src'}
)
setup(**d)