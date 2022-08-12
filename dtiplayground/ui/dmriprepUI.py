from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
import os
import yaml
from pathlib import Path
import glob
import dtiplayground.config as config
from dtiplayground.ui.protocoltab import ProtocolTab
from dtiplayground.ui.executiontab import ExecutionTab
from dtiplayground.ui.protocol import Protocol
from dtiplayground.ui.quickview import QuickView

class Widgets(QWidget):
    
  def __init__(self, parent, protocol_template, args):
    super(QWidget, self).__init__(parent)
    self.protocol_template = protocol_template
    self.unsaved_changes = True

    # User preferences
    user_directory = os.path.expanduser("~/.niral-dti")
    if not os.path.exists(user_directory + "/user_preferences.yml"):
      self.CreateUserPreferencesFile()
    preferences_yml = yaml.safe_load(open(user_directory + "/user_preferences.yml", 'r'))
    
    # Load yml file used to initialize modules
    def_protocol_path = Path(__file__).parent.joinpath('data/init_protocol.yml')
    protocol_yml = yaml.safe_load(open(def_protocol_path.__str__(),'r'))
    
    # instanciation of classes
    
    self.protocol_tab = ProtocolTab(protocol_template, protocol_yml, preferences_yml) #elements related to the protocol tab
    self.execution_tab = ExecutionTab(protocol_template, args) #elements related to the execution tab
    init_module_id = self.protocol_tab.selector.modules_list_widget.count()
    self.protocol = Protocol(protocol_template, protocol_yml, preferences_yml, init_module_id) #functions related to the manipulations of the protocol

    # Initialize tabs
    self.tabs = QTabWidget()    
    self.tabs.addTab(self.protocol_tab.tab, "Protocol")
    self.tabs.addTab(self.execution_tab.tab, "Execution")       

    # Add tabs to widget
    layout = QVBoxLayout(self)
    layout.addWidget(self.tabs)
    self.setLayout(layout)

    # Create red and green icons : could be a function
    pixmap = QPixmap(100, 100)
    pixmap.fill(QColor("red"))
    self.red_icon = QIcon(pixmap)
    pixmap.fill(QColor("green"))
    self.green_icon = QIcon(pixmap)

    # Communication between QuickView and Dmriprep
    QuickView.signal_quickview.execute_exclude_gradients.connect(self.ExecuteExcludeGradientsFromQuickView)
    # Communicatin between modules_details classes and Protocol class
    self.protocol_tab.details.baselineaverage.communicate.send_params.connect(self.UpdateModuleParams)
    self.protocol_tab.details.brainmask.communicate.send_params.connect(self.UpdateModuleParams)
    self.protocol_tab.details.dtiestimate.communicate.send_params.connect(self.UpdateModuleParams)
    self.protocol_tab.details.eddymotion.communicate.send_params.connect(self.UpdateModuleParams)
    self.protocol_tab.details.exclude.communicate.send_params.connect(self.UpdateModuleParams)
    self.protocol_tab.details.interlacecheck.communicate.send_params.connect(self.UpdateModuleParams)
    self.protocol_tab.details.slicecheck.communicate.send_params.connect(self.UpdateModuleParams)
    self.protocol_tab.details.susceptibility.communicate.send_params.connect(self.UpdateModuleParams)
    self.protocol_tab.details.susceptibility.communicate.call_update_user_preferences_file.connect(self.UpdateUserPreferencesFile)
    self.protocol_tab.details.utilheader.communicate.send_params.connect(self.UpdateModuleParams)
    self.protocol_tab.details.utilmerge.communicate.send_params.connect(self.UpdateModuleParams)
    self.protocol_tab.details.qcreport.communicate.send_params.connect(self.UpdateModuleParams)
    self.protocol_tab.details.dtiregister.communicate.send_params.connect(self.UpdateModuleParams)
    self.protocol_tab.details.singletract.communicate.send_params.connect(self.UpdateModuleParams)
    self.protocol_tab.details.braintractography.communicate.send_params.connect(self.UpdateModuleParams)
    # Communication from module selector subtab
    self.protocol_tab.selector.communicate.module_added_to_protocol_drop.connect(self.protocol.ModuleAddedToProtocolDrop)
    self.protocol_tab.selector.communicate.call_execute_exclude_gradients_popup.connect(self.protocol_tab.exclude_popup.exec_)
    self.protocol_tab.selector.communicate.call_execute_merge_images_popup.connect(self.protocol_tab.merge_popup.exec_)
    # Communication from module details subtab
    self.protocol_tab.details.communicate.set_update_module_details.connect(self.SetUpdateModuleDetails)
    self.protocol_tab.details.communicate.call_OrderModulesInProtocolList.connect(self.GetDicProtocolKeys)
    self.protocol_tab.details.communicate.get_selected_item_data.connect(self.GetDicProtocolSelectedItem)
    # Communication from general subtab
    self.protocol_tab.general.communicate.call_UnsavedModif.connect(self.UnsavedModif)    
    # Communication from execution tab
    self.execution_tab.communicate.call_DeleteTempDirectory.connect(self.DeleteTempDirectory)
    self.execution_tab.communicate.check_manual_exclude.connect(self.CheckManualExcludeInProtocol)
    self.execution_tab.communicate.call_write_protocol_yml.connect(self.protocol.WriteProtocolYML)
    self.execution_tab.communicate.check_unsaved_changes.connect(self.CheckUnsavedChangesBeforeCompute)
    self.execution_tab.communicate.call_save_protocol.connect(self.protocol_tab.SaveProtocol)
    # Communication from protocol tab
    self.protocol_tab.communicate.call_module_added_to_protocol.connect(self.protocol.ModuleAddedToProtocol)
    self.protocol_tab.communicate.call_unsaved_modif.connect(self.UnsavedModif)
    self.protocol_tab.communicate.call_order_modules_in_protocol_list.connect(self.GetDicProtocolKeys)
    self.protocol_tab.communicate.set_loading_protocol.connect(self.protocol.SetLoadingProtocol)
    self.protocol_tab.communicate.set_module_id.connect(self.protocol.SetModuleId)
    self.protocol_tab.communicate.get_module_id.connect(self.GetModuleId)
    self.protocol_tab.communicate.call_set_default_protocol.connect(self.protocol.SettingDefaultProtocol)
    self.protocol_tab.communicate.call_read_protocol.connect(self.protocol.ReadProtocol)
    self.protocol_tab.communicate.call_remove_module_from_dic_protocol.connect(self.protocol.RemoveModuleFromDicProtocol)
    self.protocol_tab.communicate.enable_eddymotion_param.connect(self.EnableEddymotionParam)
    self.protocol_tab.communicate.set_dic_protocol.connect(self.protocol.SetDicProtocol)
    self.protocol_tab.communicate.call_no_unsaved_modif.connect(self.NoUnsavedModif)
    self.protocol_tab.communicate.call_write_protocol_yml.connect(self.protocol.WriteProtocolYML)
    self.protocol_tab.communicate.module_added_to_protocol_loading.connect(self.protocol.ModuleAddedToProtocolLoading)
    self.protocol_tab.communicate.call_update_user_preferences_file.connect(self.UpdateUserPreferencesFile)
    # Communication from protocol class
    self.protocol.communicate.call_clear_protocol.connect(self.protocol_tab.ClearProtocol)
    self.protocol.communicate.set_general_param_from_read_protocol.connect(self.SetGeneralParam)
    self.protocol.communicate.add_module_to_protocol_widget.connect(self.protocol_tab.AddModuleToProtocolWidget)
    self.protocol.communicate.get_protocol_io.connect(self.GetProtocolIO)
    self.protocol.communicate.call_unsaved_modif.connect(self.UnsavedModif)
    self.protocol.communicate.get_list_widget_modules.connect(self.protocol_tab.GetListWidgetModules)
    self.protocol.communicate.get_selected_modules.connect(self.protocol_tab.selector.GetListWidgetSelectedModules)
    self.protocol.communicate.set_module_data.connect(self.protocol_tab.SetModuleData)
    self.protocol.communicate.call_execute_exclude_gradients_popup.connect(self.protocol_tab.exclude_popup.exec_)
    self.protocol.communicate.call_execute_merge_images_popup.connect(self.protocol_tab.merge_popup.exec_)
    self.protocol.communicate.enable_modules_list_widget.connect(self.protocol_tab.selector.EnableModulesListWidget)
    self.protocol.communicate.enable_exclude_gradients_module.connect(self.protocol_tab.selector.EnableExcludeGradientsModule)
    self.protocol.communicate.enable_merge_images_module.connect(self.protocol_tab.selector.EnableMergeImagesModule)
    self.protocol.communicate.update_selector_data.connect(self.protocol_tab.selector.UpdateSelectorData)
    self.protocol.communicate.enable_eddymotion_param.connect(self.EnableEddymotionParam)


    self.tabs.tabBarClicked.connect(self.MultiInput)
    
    # Command Line arguments
    if args.protocol:
      #arg_protocol = yaml.safe_load(open(args.protocol,'r'))
      self.protocol.ReadProtocol(args.protocol)
    if args.output_directory:
      self.execution_tab.output_line.setText(args.output_directory)
    if args.image:
      if len(args.image) == 1:
        self.execution_tab.input_filename = args.image[0]
        if args.quickview:
          self.protocol.dic_protocol[0] = self.protocol.exclude_default_params
          self.execution_tab.multi_input = 0
          self.execution_tab.Compute([True, True]) #launch QuickView window
      else:
        self.execution_tab.input_filename1 = args.image[0]
        self.execution_tab.input_filename2 = args.image[1]


    self.unsaved_changes = False    

  def UnsavedModif(self):
    if self.unsaved_changes == False:
      self.unsaved_changes = True
      self.tabs.setTabIcon(0, self.red_icon)
      self.tabs.setTabToolTip(0, "Unsaved modifications have been made to protocol")

  def NoUnsavedModif(self):
    self.unsaved_changes = False
    self.tabs.setTabIcon(0, self.green_icon)
    self.tabs.setTabToolTip(0, "Protocol saved")

  def CreateUserPreferencesFile(self):
    user_directory = os.path.expanduser("~/.niral-dti")
    default = {"fslConfigurationFilePath": user_directory + "/dmriprep-" + config.INFO["dmriprep"]["version"] + "/parameters/fsl/fsl_regb02b0.cnf",
      "showExcludeGradientsPopup": True, 
      "showMergeImagesPopup": True}
    with open(user_directory + "/user_preferences.yml", 'w')as filename:
      yaml.dump(default, filename)

  def UpdateUserPreferencesFile(self, preferences):
    user_directory = os.path.expanduser("~/.niral-dti")
    with open(user_directory + "/user_preferences.yml", 'w')as filename:
      yaml.dump(preferences, filename)
    
  def DeleteTempDirectory(self):
    if os.path.exists("temp_dmriprep_ui/protocol.yml"):
      os.remove("temp_dmriprep_ui/protocol.yml")
    if os.path.exists("temp_dmriprep_ui"):
      os.rmdir("temp_dmriprep_ui")

  def ExecuteExcludeGradientsFromQuickView(self, list_gradients):
    key = list(self.protocol.dic_protocol.keys())[0]
    self.protocol.dic_protocol[key][2]["protocol"]['gradientsToExclude'] = list_gradients

    if not os.path.exists("temp_dmriprep_ui"):
      os.mkdir("temp_dmriprep_ui")
      print("Directory 'temp_dmriprep_ui' created")
    else:
      print("Directory 'temp_dmriprep_ui' already exists")
    self.protocol.WriteProtocolYML("temp_dmriprep_ui/protocol.yml")

    self.execution_tab.StartComputation("temp_dmriprep_ui/protocol.yml")

  def SetUpdateModuleDetails(self, bool_update_module_details):
    self.protocol.update_module_details = bool_update_module_details
  
  def GetDicProtocolSelectedItem(self, data):
    key = data[0]
    index = data[1]
    selected_module = self.protocol.dic_protocol[key]
    self.protocol_tab.details.communicate.SendDicProtocolSelectedItem([selected_module, index])

  def MultiInput(self):
    multi_input = 0
    for index in self.protocol.dic_protocol:
      for module_yml in self.protocol_tab.details.modules_yml_list:
        if self.protocol.dic_protocol[index][1] in module_yml["name"]:
          if "multi_input" in module_yml["process_attributes"]:
            multi_input = 1
            if self.protocol.dic_protocol[index][0] == "Merge Images":
              multi_input = 2

    self.execution_tab.communicate.NumberOfInputs(multi_input)

  def CheckManualExcludeInProtocol(self):
    computation_details = [False, False]
    if len(self.protocol.dic_protocol) > 0:
      key = list(self.protocol.dic_protocol.keys())[0]
      if self.protocol.dic_protocol[key][1] == "MANUAL_Exclude":
        computation_details[0] = True
        if self.protocol_tab.details.exclude.selectionMethod.currentText() == "QuickView":
          computation_details[1] = True
    self.execution_tab.communicate.CallCompute(computation_details)

  def CheckUnsavedChangesBeforeCompute(self):
    if self.unsaved_changes == True:
      self.execution_tab.unsaved_changes_popup.exec_()
    filename = self.protocol_tab.protocol_filename
    self.execution_tab.StartComputation(filename)

  def GetModuleId(self):
    identifier = self.protocol.module_id
    self.protocol_tab.DefaultProtocol(identifier)
  
  def SetModuleId(self, new_id):
    self.protocol.module_id = new_id

  def SetGeneralParam(self, protocol):
    self.execution_tab.output_line.setText(protocol["output_directory"])
    if protocol["no_output_image"] == False:
      self.protocol_tab.general.no_output_image_false.setChecked(True)
    else:
      self.protocol_tab.general.no_output_image_true.setChecked(True)
    image_type = ["output_format"]
    for ite in self.protocol_template["options"]["io"]["output_format"]["candidates"]:
      if ite["value"] == image_type:
        self.protocol_tab.general.output_format.setCurrentText(ite["caption"])
        self.protocol_tab.general.GetOutputImageTypeIt(ite["caption"])
    self.protocol_tab.general.b0.setValue(protocol["baseline_threshold"])

  def GetProtocolIO(self, data):
    data[0]["io"] = {
        'baseline_threshold': self.protocol_tab.general.b0.value(),
        'no_output_image': self.protocol_tab.general.no_output_image_true.isChecked(),
        'output_directory': '',
        'output_format': self.protocol_template["options"]["io"]["output_format"]["candidates"][self.protocol_tab.general.outputimagetype_it]["value"]
      }
    self.protocol.Writing(data)

  def GetIndexAndKey(self):
    index = self.protocol_tab.protocol_list_widget.currentRow() #in protocol_list_widget
    key = self.protocol_tab.protocol_list_widget.item(index).data(QtCore.Qt.UserRole) #module_id, in dic_protocol (dictionary)
    return index, key

  def UpdateModuleParams(self, params):
    self.UnsavedModif()
    index, key = self.GetIndexAndKey()
    if index >= 0 and self.protocol.update_module_details == True:
      self.protocol.dic_protocol[key] = params

  def GetDicProtocolKeys(self):
    list_new_keys = []
    for module_index in range(len(self.protocol.dic_protocol)): 
      list_new_keys.append(self.protocol_tab.protocol_list_widget.item(module_index).data(QtCore.Qt.UserRole))
    self.protocol.OrderModulesInProtocolList(list_new_keys)

  def EnableEddymotionParam(self, value):
    self.protocol_tab.details.eddymotion.estimateMoveBySusceptibility_true.setEnabled(value)
    self.protocol_tab.details.eddymotion.estimateMoveBySusceptibility_false.setEnabled(value)