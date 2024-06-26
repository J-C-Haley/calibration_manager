#!/usr/bin/env python3
from lxml import etree
import os
import pathlib
import re
import shutil
import subprocess
from ruamel.yaml import YAML
yaml = YAML()

import rospy
import rospkg
rospack = rospkg.RosPack()
from std_msgs.msg import *
from sensor_msgs.msg import *
from cv_bridge import CvBridge
bridge = CvBridge()

from qt_gui.plugin import Plugin
from python_qt_binding import loadUi
from python_qt_binding.QtCore import QSettings, Qt, QEvent
from python_qt_binding.QtWidgets import QWidget, QTreeWidgetItem, QCompleter, QComboBox, QMenu

import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
root = tk.Tk()
root.withdraw()

class SetupManager(Plugin):
    def __init__(self, context):
        super(SetupManager, self).__init__(context)
        self.setObjectName('SetupManager')

        self.cmp_types = []

        ### Create QWidget
        self._widget = QWidget()
        ui_file = os.path.join(rospack.get_path('calibration_manager'), 'config', 'SetupManager.ui')
        loadUi(ui_file, self._widget)
        self._widget.setObjectName('SetupManagerUi')
        if context.serial_number() > 1:
            self._widget.setWindowTitle(self._widget.windowTitle() + (' (%d)' % context.serial_number()))
        context.add_widget(self._widget)

        ### Set up state vars
        self.restore_settings(None,None)
        
        ### Set up gui connections
        self._widget.setupStorageLineEdit.returnPressed.connect(self.set_setup_storage)
        self._widget.selectSetupStoragePushButton.clicked.connect(self.find_setup_storage)
        self._widget.setupNsComboBox.installEventFilter(self)
        self._widget.setupNsComboBox.activated.connect(self.set_setup_from_box)
        self._widget.newSetupPushButton.clicked.connect(self.new_setup)
        self._widget.localDataStorageLineEdit.textChanged.connect(self.set_data_storage_local)
        self._widget.deepDataStorageLineEdit.textChanged.connect(self.set_data_storage_deep)
        self._widget.runDriversPushButton.clicked.connect(self.run_drivers)

        ### Set up component param tree
        self._widget.componentTreeWidget.setHeaderLabels(['Component','Value','Type'])
        self.setup = {'components':[]}
        self.list_components()
        self.component_completer = QCompleter([f['launch_path'] for f in self.launch_files_info])
        self.component_completer.setFilterMode(Qt.MatchContains)
        self._widget.addComponentLineEdit.setCompleter(self.component_completer)
        self._widget.addComponentLineEdit.returnPressed.connect(self.new_component_from_launch)
        self._widget.componentTreeWidget.setContextMenuPolicy(Qt.CustomContextMenu)  
        self._widget.componentTreeWidget.customContextMenuRequested.connect(self.component_context_menu)

        ### Set up topic recording selection
        self._widget.topicTreeWidget.setHeaderLabels(['group / topic','recording end delay (s)'])       
        self.refresh_topics()
        self._widget.addTopicToolButton.clicked.connect(self.new_topic)
        self._widget.addGroupToolButton.clicked.connect(self.new_topic_group)
        self._widget.refreshToolButton.clicked.connect(self.refresh_topics)
        self._widget.addTopicLineEdit.returnPressed.connect(self.new_topic)
        self._widget.topicTreeWidget.setContextMenuPolicy(Qt.CustomContextMenu)  
        self._widget.topicTreeWidget.customContextMenuRequested.connect(self.topic_context_menu)  

        self._widget.savePushButton.clicked.connect(self.save_setup)

        ### Initialize defaut setup from /setup_template_pkg on first run
        setup_path = pathlib.Path(self.setup_storage).expanduser() / self.setup_ns
        if not setup_path.exists():
            self.new_setup(os.environ.get('ROS_SETUP'))
        self.init_setup_combobox()

    def save_settings(self, plugin_settings, instance_settings):
        '''Save ui configuration'''
        self.settings.setValue('setup_storage',self.setup_storage)
        self.settings.setValue('data_storage_local',self.data_storage_local)
        self.settings.setValue('data_storage_deep',self.data_storage_deep)

    def restore_settings(self, plugin_settings, instance_settings):
        '''Restore some stored values for the ui'''
        self.settings = QSettings('SetupManager', 'SetupManager') # in ~/.config/

        self.setup_storage = self.settings.value('setup_storage', "~/.ros/setups_local/")
        if self.setup_storage != '':
            self._widget.setupStorageLineEdit.setText(self.setup_storage)
            self.set_setup_storage()

        self.setup_ns = os.environ.get('ROS_SETUP')
        if self.setup_ns is None:
            self.setup_ns = 'default_setup'
            os.environ['ROS_SETUP'] = self.setup_ns
        self.set_setup_ns(self.setup_ns)

        self.data_storage_local = self.settings.value('data_storage_local', '')
        if self.data_storage_local != '':
            self._widget.localDataStorageLineEdit.setText(self.data_storage_local)

        self.data_storage_deep = self.settings.value('data_storage_deep', '')
        if self.data_storage_deep != '':
            self._widget.deepDataStorageLineEdit.setText(self.data_storage_deep)
        
    def find_setup_storage(self):
        file = filedialog.askdirectory()
        if file is not None:
            self._widget.setupStorageLineEdit.setText(str(file))
            self.set_setup_storage()

    def set_setup_storage(self, setup_storage=None):
        if setup_storage is None:
            setup_storage = self._widget.setupStorageLineEdit.text()
        setup_storage_path = pathlib.Path(setup_storage).expanduser()
        if setup_storage_path.exists():
            setup_dir_link = pathlib.Path('~/.ros/setups/').expanduser()

            self.setup_storage = setup_storage
            
            setup_dir_link.unlink(missing_ok=True)
            setup_dir_link.symlink_to(setup_storage_path,target_is_directory=True)

            self._widget.setupStorageLineEdit.setStyleSheet("color: green;")
        else:
            self._widget.setupStorageLineEdit.setStyleSheet("color: red;")

        self.setup_ns = None
        # self._widget.setupNsLineEdit.setText(self.setup_ns)
    
    def init_setup_combobox(self):
        self.fill_setup_combo_box()
        selected = os.environ.get('ROS_SETUP')
        if selected is not None and selected in self.setup_names:
            self._widget.setupNsComboBox.setCurrentText(selected)

    def eventFilter(self, target, event):
        if target == self._widget.setupNsComboBox and event.type() == QEvent.MouseButtonPress:
            self.fill_setup_combo_box()
        return False
    
    def fill_setup_combo_box(self):
        setup_names = [str(f.name) for f in pathlib.Path(self.setup_storage).expanduser().iterdir() \
                if f.is_dir() \
                and (f/'setup.yaml').exists() \
                and not os.path.islink(f)]
        if hasattr(self,'setup_names') and setup_names == self.setup_names:
            return
        self.setup_names = setup_names
        self._widget.setupNsComboBox.clear()
        self._widget.setupNsComboBox.addItems(self.setup_names)

    def set_setup_from_box(self, index):
        self.set_setup_ns(self.setup_names[index])

    def set_setup_ns(self, setup_ns):
        setup_path = pathlib.Path(self.setup_storage).expanduser() / setup_ns
        if not setup_path.exists():
            rospy.logerr(f'Selected setup does not exist: {setup_path}')
            return
        self.setup_ns = setup_ns
        os.environ['ROS_SETUP'] = self.setup_ns
        self._widget.setupNsComboBox.setCurrentText(self.setup_ns)

        # make symlink for deterministic path
        ### TODO: remove this??? Doesn't work on shared setup storage
        selected_setup_path = pathlib.Path(self.setup_storage).expanduser() / 'selected_setup'
        selected_setup_path.unlink(missing_ok=True)
        selected_setup_path.symlink_to(setup_path,target_is_directory=True)
        ###
        self.load_setup_to_trees(setup_path)

    def new_setup(self, setup_name=None, setup_template_pkg=None):
        '''create a new setup'''
        # TODO: make new setups from TEMPLATES or COPY existing setup format
        # setup_ns = self._widget.setupNsLineEdit.text()
        if setup_name is None or not isinstance(setup_name, str):
            setup_name = simpledialog.askstring("Input", "New unique setup name (convention is: {machine/cell}_{pchostname})")
        setup_path = pathlib.Path(self.setup_storage).expanduser() / setup_name
        if setup_path.exists():
            rospy.logerr('Setup already exists, choose a unique name')
            messagebox.showerror("Error", "Setup already exists, choose a unique name")
            return
        setup_path.mkdir(exist_ok=True,parents=True)

        # Copy setup template 
        if setup_template_pkg is None:
            setup_template_pkg = os.environ.get('ROS_SETUP_TEMPLATE','calibration_manager')
        setup_template_pkg = pathlib.Path(rospack.get_path(setup_template_pkg)).expanduser()
        shutil.copy(setup_template_pkg/'default_setup.yaml',setup_path/'setup.yaml')
        with open(setup_path/'setup.yaml', 'r') as file:
            filedata = file.read()
        filedata = filedata.replace('$(env ROS_SETUP)', os.environ.get('ROS_SETUP'))
        with open(setup_path/'setup.yaml', 'w') as file:
            file.write(filedata)

        self.set_setup_ns(setup_ns=setup_name) # TODO not working?
        self.save_setup()

    def set_data_storage_local(self):
        self.data_storage_local = self._widget.localDataStorageLineEdit.text()

    def set_data_storage_deep(self):
        self.data_storage_deep = self._widget.deepDataStorageLineEdit.text()

    def list_components(self):
        '''Find all launch files eligible to be added as components'''
        pkg_list = rospack.list()
        pkg_paths = [pathlib.Path(rospack.get_path(pkg)) for pkg in pkg_list]
        
        self.launch_files_info = []
        for pkg, pth in zip(pkg_list,pkg_paths):
            lfs = list(pth.glob('**/*.launch'))
            for lf in lfs:
                lf = str(lf)
                self.launch_files_info.append({
                    'package':pkg,
                    'package_path':pth,
                    'launch_path':lf
                    })

    def load_setup_to_trees(self,setup_path):
        '''Parse prior setup and construct a param tree'''
        self._widget.componentTreeWidget.clear()
        self._widget.topicTreeWidget.clear()

        if not (setup_path / 'setup.yaml').exists():
            return
        
        self.setup = yaml.load(setup_path / 'setup.yaml')

        self._widget.localDataStorageLineEdit.setText(self.setup['data_storage_local'])
        self.set_data_storage_local()
        self._widget.deepDataStorageLineEdit.setText(self.setup['data_storage_deep'])
        self.set_data_storage_deep()

        # put components into tree
        if 'components' in self.setup and self.setup['components'] is not None:
            for cmp in self.setup['components']:
                self.add_component_to_tree(cmp)
        self._widget.componentTreeWidget.resizeColumnToContents(0)

        # put recording topics into tree
        if 'bags' in self.setup and self.setup['bags'] is not None:
            for grp in self.setup['bags']:
                grp_item = self.new_topic_group(group_name=grp['group_name'],enabled=grp['enabled'])
                for tpc in grp['topics']: #self.setup['topics'][group_name].items():
                    self.load_topic(tpc, grp_item)
        self._widget.topicTreeWidget.resizeColumnToContents(0)

    def save_setup_as(self):
        '''TODO: Create new setup from current setup with changes'''

    def rename_setup(self):
        '''TODO: Rename current setup, altering paths'''

    def add_component_to_tree(self, cmp: dict):
        cmp_item = TreeWidgetItem(self._widget.componentTreeWidget)
        cmp_item.setFlags(cmp_item.flags() | Qt.ItemIsUserCheckable)
        cmp_item.setCheckState(0,bool(cmp['enabled'])*2) # for whatever reason checked = 2
        cmp_item.setFlags(cmp_item.flags() | Qt.ItemIsEditable)
        cmp_item.editable = [1,0,1]
        cmp_item._name = cmp['component_name']
        cmp_item.setText(0,cmp_item._name)
        cmp_item.setText(1,cmp['component_package'])

        cmb = QComboBox()
        cmb.addItem('driver','1')
        cmb.addItem('service','2')
        cmb.addItem('routine', '3')
        cmb.setCurrentText(cmp['component_type'])
        self._widget.componentTreeWidget.setItemWidget(cmp_item, 2 , cmb)
        self.cmp_types.append((cmp_item,cmb))

        # add meta params
        p = TreeWidgetItem(cmp_item)
        p.editable = [0,0,0]
        p._name = 'component_launch_file'
        p.setText(0,p._name)
        p.setText(1,cmp['component_launch_file'])
        p.setText(2,'meta')

        p = TreeWidgetItem(cmp_item)
        p.setFlags(p.flags() | Qt.ItemIsEditable)
        p.editable = [0,1,0]
        p._name = 'group_name'
        p.setText(0,p._name)
        p.setText(1,cmp['group_name'])
        p.setText(2,'meta')

        # add arguments
        for arg_name, val in cmp['args'].items():
            p = TreeWidgetItem(cmp_item)
            p.setFlags(p.flags() | Qt.ItemIsEditable)
            p._name = arg_name
            p.setText(0,p._name)
            p.setText(1,val)
            p.setText(2,'arg')

        # TODO: add ros parameters

    def new_component_from_launch(self, component_path: str = None):
        '''Add a new component to the tree'''
        if not component_path:
            component_path = pathlib.Path(self._widget.addComponentLineEdit.text())
        component_name = str(component_path.name).split('.')[0] # TODO: list package path too?

        if component_name is None:
            return
        
        launch_file_info = [lf for lf in self.launch_files_info if lf['launch_path'] in str(component_path)][0]
        component_package = launch_file_info['package']
        component_relative_path = pathlib.Path(*list(component_path.parts[component_path.parts.index(component_package)+1:]))

        # existing_cmp_names = [key for key in self.setup['components']]
        existing_cmp_names = [self._widget.componentTreeWidget.topLevelItem(i).data(0,0)
                              for i in range(self._widget.componentTreeWidget.topLevelItemCount())]

        matches = []
        for existing_cmp_name in existing_cmp_names:
            m = re.match(f'^{component_name}(\d*)',existing_cmp_name)
            if m is not None:
                matches.append(int(m[1]))
        if len(matches) > 0:
            component_name = component_name + str(max(matches)+1)
        else:
            component_name = component_name + '0' # TODO: start at '', rename old to 0 if exact match found

        cmp = {
            'component_name':str(component_name),
            'group_name': '/',
            'component_package': component_package,
            'component_type': 'driver', # driver, service, or routine
            'component_launch_file':str(component_relative_path),
            'enabled': True,
            'args':{}
            }
                
        # parse launch file for editable parameters
        xmlroot = etree.parse(str(component_path))
        for arg in xmlroot.findall('.//arg'):
            arg_name = arg.attrib['name']
            if 'value' in arg.attrib:
                continue # TODO: show but make uneditable?
            elif 'default' in arg.attrib:
                val = arg.attrib['default']
            else:
                val = None
            if '$' in val: # filters out calculated params
                continue
            
            cmp['args'][arg_name] = val
        
        self.add_component_to_tree(cmp)

        # TODO: parse include files recursivly...?

        # self.setup['components'].append(cmp) 
        # BAD, don't construct here so that we have to read the tree (and won't be out of date)

    def run_component(self):
        '''run a single component in an external terminal'''
        root = self._widget.componentTreeWidget.invisibleRootItem()
        cmp_item = self._widget.componentTreeWidget.selectedItems()[0]

        nodes = get_subtree_nodes(cmp_item)
        component_name = str(cmp_item.data(0,0))

        cmp = {
            'component_name':component_name,
            'component_package': str(cmp_item.data(1,0)),
            'component_type': str(cmp_item.data(2,0)), # driver, routine, or service 
            'enabled':bool(cmp_item.checkState(0)==2),
            'args':{}
        }

        cmp['component_ns'] = cmp_item.data(0,0)
        cmp['args'] = {}
        for node in nodes:
            if node.data(2,0) == 'arg':
                arg_name = node.data(0,0)
                arg_val = node.data(1,0)
                cmp['args'][arg_name] = arg_val
            elif node.data(2,0) == 'meta':
                cmp[node.data(0,0)] = node.data(1,0) # metadata like launch file
            elif node.data(2,0) == 'ros_param':
                pass

        root = etree.Element("launch")
        el = root
        # el = etree.SubElement(el, "group") # TODO: make setup_ns group optional?
        # el.attrib['ns'] = self.setup_ns 
        if 'group_name' in cmp and not (cmp['group_name'] is None or cmp['group_name']==""):
            el = etree.SubElement(el, "group")
            el.attrib['ns'] = cmp['group_name']
        cmp_child = etree.SubElement(el, "include")
        cmp_child.attrib['file'] = f"$(find {cmp['component_package']})/{cmp['component_launch_file']}"

        for arg_name, arg_val in cmp['args'].items():
            arg_child = etree.SubElement(cmp_child, "arg")
            arg_child.attrib['name'] = arg_name
            arg_child.attrib['default'] = arg_val
            
        et = etree.ElementTree(root)
        launch_path = str(pathlib.Path(self.setup_storage).expanduser() / self.setup_ns / 'temp_routine.launch')
        et.write(launch_path, pretty_print=True)

        subprocess.Popen(['xterm', '-e', 'roslaunch', launch_path])

    def del_component(self):
        root = self._widget.componentTreeWidget.invisibleRootItem()
        for item in self._widget.componentTreeWidget.selectedItems():
            (item.parent() or root).removeChild(item)

    def component_context_menu(self, point):
        index = self._widget.componentTreeWidget.indexAt(point)
        if not index.isValid():
            return
        
        item = self._widget.componentTreeWidget.itemAt(point)
        name = item.text(0)
        
        menu = QMenu()
        if item.parent() is None: # get if it's a top level item... a component
            run_action = menu.addAction("Run")
            # disable_action = menu.addAction("Disable")
            del_action = menu.addAction("Delete")

        action_picked = menu.exec_(self._widget.componentTreeWidget.mapToGlobal(point))
        if action_picked is None:
            return
        if action_picked == run_action:
            self.run_component()
        # elif action_picked == disable_action:
        #     self.disable_component()
        elif action_picked == del_action:
            self.del_component()
    
    def run_drivers(self):
        launch_path = str(pathlib.Path(self.setup_storage).expanduser() / self.setup_ns / 'drivers.launch')
        subprocess.Popen(['xterm', '-e', 'roslaunch', launch_path])

    def list_topics(self):
        topics_and_types = rospy.get_published_topics()
        topics = [i[0] for i in topics_and_types]
        return topics
    
    def refresh_topics(self):
        self.topic_completer = QCompleter(self.list_topics())
        self.topic_completer.setFilterMode(Qt.MatchContains)
        self._widget.addTopicLineEdit.setCompleter(self.topic_completer)

    def load_topic(self, topic: dict, group: QTreeWidgetItem):
        tpc_item = QTreeWidgetItem(group)
        tpc_item.setFlags(tpc_item.flags() | Qt.ItemIsUserCheckable)
        tpc_item.setCheckState(0,int(int(topic['enabled'])*2)) # for whatever reason checked = 2
        # tpc_item.setFlags(tpc_item.flags() | Qt.ItemIsEditable)
        # tpc_item.editable = [1,0,1]
        tpc_item._name = topic['topic_name']
        tpc_item.setText(0,tpc_item._name)
    
    def new_topic_group(self, group_name: str='UNTITLEDBAGGROUP', enabled: bool=True):
        if group_name == False:
            group_name = 'UNTITLEDBAGGROUP'
        grp_item = TopicGroupTreeWidgetItem(self._widget.topicTreeWidget)
        grp_item.setFlags(grp_item.flags() | Qt.ItemIsEditable)
        grp_item.setFlags(grp_item.flags() | Qt.ItemIsUserCheckable)
        grp_item.setCheckState(0,bool(enabled)*2) # for whatever reason checked = 2
        
        # cmp_item.setFlags(cmp_item.flags() | Qt.ItemIsUserCheckable)
        # cmp_item.setCheckState(0,bool(cmp['enabled'])*2) # for whatever reason checked = 2

        grp_item.editable = [1,1]
        grp_item._name = group_name
        grp_item.setText(0,grp_item._name)
        grp_item.setText(1,'0')
        return grp_item

    def new_topic(self):
        root = self._widget.topicTreeWidget.invisibleRootItem()
        if len(self._widget.topicTreeWidget.selectedItems()) != 1:
            return
        grp_item = list(self._widget.topicTreeWidget.selectedItems())[0]

        tpc_item = QTreeWidgetItem(grp_item)
        tpc_item.setFlags(tpc_item.flags() | Qt.ItemIsUserCheckable)
        tpc_item.setCheckState(0,2) # for whatever reason checked = 2
        tpc_item._name = self._widget.addTopicLineEdit.text()
        tpc_item.setText(0,tpc_item._name)

    def del_topic(self):
        root = self._widget.topicTreeWidget.invisibleRootItem()
        for item in self._widget.topicTreeWidget.selectedItems():
            (item.parent() or root).removeChild(item)

    def topic_context_menu(self, point):
        index = self._widget.topicTreeWidget.indexAt(point)
        if not index.isValid():
            return
        
        item = self._widget.topicTreeWidget.itemAt(point)
        name = item.text(0)
        
        menu = QMenu()
        del_action = menu.addAction("Delete")

        action_picked = menu.exec_(self._widget.topicTreeWidget.mapToGlobal(point))
        if action_picked is None:
            return
        elif action_picked == del_action:
            self.del_topic()
    
    def save_setup(self):
        '''Save the configured setup and launch files'''

        self.setup['data_storage_local'] = self.data_storage_local
        self.setup['data_storage_deep'] = self.data_storage_deep

        # read component tree back to the dictionary           
        self.setup['components'] = []
        for i in range(self._widget.componentTreeWidget.topLevelItemCount()):

            cmp_item = self._widget.componentTreeWidget.topLevelItem(i)
            nodes = get_subtree_nodes(cmp_item)
            component_name = str(cmp_item.data(0,0))

            for stored_cmp_item, cmb in self.cmp_types: # read comboboxes
                if cmp_item is stored_cmp_item:
                    cmp_type = cmb.currentText()

            cmp = {
                'component_name':component_name,
                'component_package': str(cmp_item.data(1,0)),
                'component_type': cmp_type, # driver, routine, or service 
                'enabled':bool(cmp_item.checkState(0)==2),
                'args':{}
            }

            cmp['component_ns'] = cmp_item.data(0,0)
            cmp['args'] = {}
            for node in nodes:
                if node.data(2,0) == 'arg':
                    arg_name = node.data(0,0)
                    arg_val = node.data(1,0)
                    cmp['args'][arg_name] = arg_val
                elif node.data(2,0) == 'meta':
                    cmp[node.data(0,0)] = node.data(1,0) # metadata like launch file
                elif node.data(2,0) == 'ros_param':
                    pass

            self.setup['components'].append(cmp)

        setup_dir = pathlib.Path(self.setup_storage).expanduser() / self.setup_ns

        # write drivers.launch
        root = etree.Element("launch")
        el = root
        # setup_el = etree.SubElement(el, "group") # TODO: make setup_ns grouping optional
        # setup_el.attrib['ns'] = self.setup_ns
        # el = setup_el
        for cmp in self.setup['components']:
            if cmp['component_type'] != 'driver':
                continue
            if not cmp['enabled']:
                continue
            
            if 'group_name' in cmp and not (cmp['group_name'] is None or cmp['group_name']==""):
                print(cmp['group_name'],flush=True)
                el = etree.SubElement(root, "group")
                el.attrib['ns'] = cmp['group_name']
            cmp_child = etree.SubElement(el, "include")
            cmp_child.attrib['file'] = f"$(find {cmp['component_package']})/{cmp['component_launch_file']}"

            for arg_name, arg_val in cmp['args'].items():
                arg_child = etree.SubElement(cmp_child, "arg")
                arg_child.attrib['name'] = arg_name
                arg_child.attrib['default'] = arg_val
               
        et = etree.ElementTree(root)
        et.write(str(setup_dir / 'drivers.launch'), pretty_print=True)

        # TODO: write services launch? Start services?

        # TODO: write routines launches?

        # Save topics to record
        self.setup['bags'] = []
        for i in range(self._widget.topicTreeWidget.topLevelItemCount()):
            grp_item = self._widget.topicTreeWidget.topLevelItem(i)
            grp_name = str(grp_item.data(0,0))
            grp_end_delay = float(grp_item.data(1,0))
            grp = {'group_name':grp_name,
                   'end_delay':grp_end_delay,
                   'enabled': bool(grp_item.checkState(0)==2),
                   'topics':[]}

            tpc_items = [grp_item.child(i) for i in range(grp_item.childCount())]
            for tpc_item in tpc_items:
                topic_name = str(tpc_item.data(0,0))
                tpc = {
                    'topic_name': topic_name,
                    'enabled': bool(tpc_item.checkState(0)==2)
                }
                grp['topics'].append(tpc)

            self.setup['bags'].append(grp)

        yaml.dump(self.setup, pathlib.Path(self.setup_storage).expanduser() / self.setup_ns / 'setup.yaml')

    def discard_setup_changes(self):
        pass

    def shutdown_plugin(self):
        self.save_settings(None,None)

    def trigger_configuration(self): 
        pass # stub for gear icon

# QT Tree management
class TreeWidgetItem(QTreeWidgetItem):
    def __init__(self, parent=None):
        super(TreeWidgetItem, self).__init__(parent)
        self.editable = [0,1,0] # defaults to locking name and type, not val

    def setData(self, column, role, value): 
        if self.editable[column] == 0 and role == 2:
            return
        super(TreeWidgetItem, self).setData(column, role, value)
        self._name = str(value)
        # TODO: make tree highlight changes until saved? Below does not work.
        # super(TreeWidgetItem, self).setStyleSheet("color: red;")
        # super(TreeWidgetItem, self).setBackground(1,QColor('red')) # WORKS when outside of the class??
        # super(TreeWidgetItem, self).setBackgroundColor(1, QColor('red'))
        # self.setStyleSheet("background-color: green;")

class TopicGroupTreeWidgetItem(QTreeWidgetItem):
    def __init__(self, parent=None):
        super(TopicGroupTreeWidgetItem, self).__init__(parent)
        self.editable = [1,1] # editable by default

    def setData(self, column, role, value): 
        if self.editable[column] == 0 and role == 2:
            return
        blacklist = [' ',',','_','-','.','/','\\',':','*','?','"', '<','>','|']
        if column == 0 and isinstance(value,str): #TODO: check unique group name too # and any(x in value for x in blacklist)
            for c in blacklist:
                value = value.replace(c,'')
        if column == 1 and not value.isnumeric():
            return # TODO: set red
        super(TopicGroupTreeWidgetItem, self).setData(column, role, value)
        self._name = str(value)

def get_subtree_nodes(tree_widget_item):
    """Returns all QTreeWidgetItems in the subtree rooted at the given node."""
    nodes = []
    nodes.append(tree_widget_item)
    for i in range(tree_widget_item.childCount()):
        nodes.extend(get_subtree_nodes(tree_widget_item.child(i)))
    return nodes


'''
TODO list
- Figure out how this is supposed to work with multiple computers...
    - seperate setup per computer
        - needs log in and run setup on each
        - can't run all machines from one 
    - same setup per computer
        - collisions: drivers.launch...
    - use 'machine' tag + a meta field to remote launch
        - same setup on 'primary' pc
        - do includes work remotely? with args? needs testing, may only work with package+launch, not file...
- change cm to use ONE cal/cfg at a time, so we can do setup.cal['prop'] directly


X make a disable component (right click option, check box...)
X add a 'run driver' (button on component?)
X add a 'run routine' dropdown + button? (Or maybe right click + color to show running?)
X add topic recorder selection 

X convert build_manager to use setups
X add setup to things to copy into build folder
X get rid of recorder_settings
X change launch to use drivers.launch? (plus fallback if not found)
    - or seperate button to launch drivers again

later:
- fancify the topic 
- enable video recording as an option
- enable throttling message rate during recording
- make a copy setup? 
- add metadata manager to build_manager
X move setup_manager into calibratation_manager package
'''



# Scrap tree right click management
    # def disable_component(self): # PROBLEM - setting as disabled prevents user from selecting to re-enable
        # root = self._widget.componentTreeWidget.invisibleRootItem()
        # for item in self._widget.componentTreeWidget.selectedItems():
        #     print(item.flags())
        #     print(item.flags() & Qt.ItemIsEnabled )
        #     enabled = item.flags() & Qt.ItemIsEnabled
        #     if enabled:
        #         item.setDisabled(True)
        #         item.setFlags(item.flags() | Qt.ItemIsSelectable)
        #     else: 
        #         # item.setDisabled(True)
        #         item.setFlags(item.flags() | Qt.ItemIsEditable)
        #         item.setFlags(item.flags() | Qt.ItemIsSelectable)


        
        # print(index)
        # print(index.row())
        # print(index.column())
        # print(index.parent())
        # print(name)
        # data = index.model().data(index,0)
        # for key in index.model().itemData(index):
        #     print('self.model.itemData(index):    key: %s  value: %s'%(key, str(index.model().itemData(index)[key])))