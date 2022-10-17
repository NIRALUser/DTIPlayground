from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 
import yaml
from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSignal as Signal
import os
import dtiplayground.config as config

class ProtocolCommunicate(QObject):

  call_clear_protocol = Signal()
  set_general_param_from_read_protocol = Signal(dict)
  add_module_to_protocol_widget = Signal(dict)
  get_protocol_io = Signal(list)
  call_unsaved_modif = Signal()
  get_index_and_key_to_update_module_details = Signal()
  get_list_widget_modules = Signal()
  get_selected_modules = Signal()
  set_module_data = Signal(list)
  call_execute_exclude_gradients_popup = Signal()
  call_execute_merge_images_popup = Signal()
  enable_modules_list_widget = Signal(bool)
  enable_exclude_gradients_module = Signal(bool)
  enable_merge_images_module = Signal(bool)
  update_selector_data = Signal(str, int)
  enable_eddymotion_param = Signal(bool)

  def CallClearProtocol(self):
    self.call_clear_protocol.emit()

  def SetGeneralParamFromReadProtocol(self, protocol_io):
    self.set_general_param_from_read_protocol.emit(protocol_io)

  def AddModuleToProtocolWidget(self, module):
    self.add_module_to_protocol_widget.emit(module)

  def GetProtocolIO(self, list):
    self.get_protocol_io.emit(list)

  def CallUnsavedModif(self):
    self.call_unsaved_modif.emit()
  
  def GetListWidgetModules(self):
    self.get_list_widget_modules.emit()

  def GetSelectedModules(self):
    self.get_selected_modules.emit()

  def SetModuleData(self, module_and_data):
    self.set_module_data.emit(module_and_data)
  
  def CallExecuteExcludeGradientsPopup(self):
    self.call_execute_exclude_gradients_popup.emit()

  def CallExecuteMergeImagesPopup(self):
    self.call_execute_merge_images_popup.emit()

  def EnableModulesListWidget(self, new_state):
    self.enable_modules_list_widget.emit(new_state)

  def EnableExcludeGradientsModule(self, new_state):
    self.enable_exclude_gradients_module.emit(new_state)

  def EnableMergeImagesModule(self, new_state):
    self.enable_merge_images_module.emit(new_state)

  def UpdateSelectorData(self, module_name, new_data):
    self.update_selector_data.emit(module_name, new_data)

  def EnableEddyMotionParam(self, value):
    self.enable_eddymotion_param.emit(value)

class Protocol():
  communicate = ProtocolCommunicate()

  def __init__(self, protocol_template, protocol_yml, preferences_yml, init_module_id):
    self.protocol_template = protocol_template
    self.preferences_yml = preferences_yml
    self.module_id = init_module_id
    self.dic_protocol = {}
    self.loading_protocol = False
    self.update_module_details = True
    self.InitializeModulesParameters(protocol_yml)

  def ReadProtocol(self, protocol):
    print("Reading protocol", protocol)
    self.communicate.CallClearProtocol()
    self.loading_protocol = True

    protocol_yml = yaml.safe_load(open(protocol,'r'))

    self.communicate.SetGeneralParamFromReadProtocol(protocol_yml["io"])    

    for protocol_module in protocol_yml["pipeline"]:
      if protocol_module[0] == "SLICE_Check":
        self.slicecheck_params[2] = protocol_module[1]
      if protocol_module[0] == "INTERLACE_Check":
        self.interlacecheck_params[2] = protocol_module[1]
      if protocol_module[0] == "BASELINE_Average":
        self.baselineaverage_params[2] = protocol_module[1]
      if protocol_module[0] == "SUSCEPTIBILITY_Correct":
        self.susceptibility_params[2] = protocol_module[1]
      if protocol_module[0] == "EDDYMOTION_Correct":
        self.eddymotion_params[2] = protocol_module[1]
      if protocol_module[0] == "BRAIN_Mask":
        self.brainmask_params[2] = protocol_module[1]
      if protocol_module[0] == "DTI_Estimate":
        self.dtiestimate_params[2] = protocol_module[1]
      if protocol_module[0] == "MANUAL_Exclude":
        self.exclude_params[2] = protocol_module[1]
      if protocol_module[0] == "UTIL_Header":
        self.utilheader_params[2] = protocol_module[1]
      if protocol_module[0] == "UTIL_Merge":
        self.utilmerge_params[2] = protocol_module[1]
      if protocol_module[0] == "QC_Report":
        self.qcreport_params[2] = protocol_module[1]
      if protocol_module[0] == "DTI_Register":
        self.dtiregister_params[2] = protocol_module[1]
      # if protocol_module[0] == "SINGLETRACT_Process DTI":
      #   self.singletract_params[2] = protocol_module[1]
      if protocol_module[0] == "BRAIN_Tractography":
        self.braintractography_params[2] = protocol_module[1]


      # modules list
      for template_module in self.protocol_template["options"]["execution"]["pipeline"]["candidates"]:
        if template_module["value"] == protocol_module[0]:
          template_module["id"] = self.module_id
          self.communicate.AddModuleToProtocolWidget(template_module)

      self.module_id += 1
      
    self.loading_protocol = False

  def WriteProtocolYML(self, name):
    protocol = {
      'io': None, 
      'pipeline': [
      ]
    }
    
    for module in self.dic_protocol.keys():
      if self.dic_protocol[module][1] == "DTI_Register":
        software_paths_filepath = os.path.expanduser("~/.niral-dti/dmriprep-" + config.INFO["dmriprep"]["version"] + "/software_paths.yml")
        software_paths_yml = yaml.safe_load(open(software_paths_filepath, 'r'))
        self.dic_protocol[module][2]['protocol']['ANTsPath'] = software_paths_yml['softwares']['ANTs']['path']
      protocol["pipeline"].append(self.dic_protocol[module][1:])

    protocol["version"] = self.protocol_template["version"]

    data = [protocol, name]
    self.communicate.GetProtocolIO(data)

  def Writing(self, data):
    protocol = data[0]
    name = data[1]
    with open(name, 'w') as protocolfile:
      yaml.dump(protocol, protocolfile)

  def OrderModulesInProtocolList(self, list_new_keys):
    new_dic_protocol = {}
    for key in list_new_keys:
      new_dic_protocol[key] = self.dic_protocol[key]
    self.SetDicProtocol(new_dic_protocol)

  def ModuleAddedToProtocol(self):    
    if self.loading_protocol == True:
      self.communicate.GetListWidgetModules()      
    else:
      self.communicate.GetSelectedModules()
    self.communicate.CallUnsavedModif()

  def ModuleAddedToProtocolLoading(self, list_modules):
    exclude_in_protocol = False
    merge_in_protocol = False
    for module in list_modules:
      key = module.data(QtCore.Qt.UserRole)
      if module.text() == "Exclude Gradients":
        exclude_in_protocol = True
        self.dic_protocol[key] = self.exclude_params
      if module.text() == "Susceptibility correction":
        self.communicate.EnableEddyMotionParam(True)
        self.dic_protocol[key] = self.susceptibility_params
      if module.text() == "Slicewise Check":
        self.dic_protocol[key] = self.slicecheck_params
      if module.text() == "Interlace Correlation Check":
        self.dic_protocol[key] = self.interlacecheck_params
      if module.text() == "Baseline Average":
        self.dic_protocol[key] = self.baselineaverage_params
      if module.text() == "Eddy motion Correction":
        self.dic_protocol[key] = self.eddymotion_params
      if module.text() == "Brain Masking":
        self.dic_protocol[key] = self.brainmask_params
      if module.text() == "Estimate DTI":
        self.dic_protocol[key] = self.dtiestimate_params
      if module.text() == "View Header":
        self.dic_protocol[key] = self.utilheader_params
      if module.text() == "Merge Images":
        self.dic_protocol[key] = self.utilmerge_params
        merge_in_protocol = True
      if module.text() == "QC Report":
        self.dic_protocol[key] = self.qcreport_params
      if module.text() == "Register DTI (ANTs)":
        self.dic_protocol[key] = self.dtiregister_params
      if module.text() == "SINGLETRACT_Process DTI":
        self.dic_protocol[key] = self.singletract_params
      if module.text() == "Brain Tractography":
        self.dic_protocol[key] = self.braintractography_params

    self.CheckSpecialModulesInProtocol(exclude_in_protocol, merge_in_protocol)

  def ModuleAddedToProtocolDrop(self, list_selected_modules):
    exclude_in_protocol = False
    merge_in_protocol = False
    for module in list_selected_modules:
      current_id = module.data(QtCore.Qt.UserRole)
      if module.text() == "Exclude Gradients":
        exclude_in_protocol = True
        self.dic_protocol[current_id] = self.exclude_default_params
      if module.text() == "Susceptibility correction":
        self.dic_protocol[current_id] = self.susceptibility_default_params
        self.communicate.EnableEddyMotionParam(True)
      if module.text() == "Slicewise Check":
        self.dic_protocol[current_id] = self.slicecheck_default_params
      if module.text() == "Interlace Correlation Check":
        self.dic_protocol[current_id] = self.interlacecheck_default_params
      if module.text() == "Baseline Average":
        self.dic_protocol[current_id] = self.baselineaverage_default_params
      if module.text() == "Eddy motion Correction":
        self.dic_protocol[current_id] = self.eddymotion_default_params
      if module.text() == "Brain Masking":
        self.dic_protocol[current_id] = self.brainmask_default_params
      if module.text() == "Estimate DTI":
        self.dic_protocol[current_id] = self.dtiestimate_default_params
      if module.text() == "View Header":
        self.dic_protocol[current_id] = self.utilheader_default_params
      if module.text() == "Merge Images":
        self.dic_protocol[current_id] = self.utilmerge_default_params
        merge_in_protocol = True
      if module.text() == "QC Report":
        self.dic_protocol[current_id] = self.qcreport_default_params
      if module.text() == "Register DTI (ANTs)":
        self.dic_protocol[current_id] = self.dtiregister_default_params
      if module.text() == "SINGLETRACT_Process DTI":
        self.dic_protocol[current_id] = self.singletract_default_params
      if module.text() == "Brain Tractography":
        self.dic_protocol[current_id] = self.braintractography_default_params

      
      self.communicate.SetModuleData([module, current_id])
      self.module_id += 1
      self.communicate.UpdateSelectorData(module.text(), self.module_id)

    self.CheckSpecialModulesInProtocol(exclude_in_protocol, merge_in_protocol)

  def CheckSpecialModulesInProtocol(self, exclude_in_protocol, merge_in_protocol):
    if exclude_in_protocol:
      if self.preferences_yml["showExcludeGradientsPopup"] == True:
        self.communicate.CallExecuteExcludeGradientsPopup()
      self.communicate.EnableModulesListWidget(False)
    elif merge_in_protocol:
      if self.preferences_yml["showMergeImagesPopup"] == True:
        self.communicate.CallExecuteMergeImagesPopup()
      self.communicate.EnableModulesListWidget(False)
    else:
      self.communicate.EnableModulesListWidget(True)
      self.communicate.EnableMergeImagesModule(False)
      self.communicate.EnableExcludeGradientsModule(False)

    
  def InitializeModulesParameters(self, protocol_yml):
    for ite in range(len(protocol_yml["pipeline"])):

      if protocol_yml["pipeline"][ite][0] == "SLICE_Check":
        self.slicecheck_default_params = protocol_yml["pipeline"][ite]
        self.slicecheck_default_params.insert(0, "Slicewise Check")

      if protocol_yml["pipeline"][ite][0] == "INTERLACE_Check":
        self.interlacecheck_default_params = protocol_yml["pipeline"][ite]
        self.interlacecheck_default_params.insert(0, "Interlace Correlation Check")
        
      if protocol_yml["pipeline"][ite][0] == "BASELINE_Average":
        self.baselineaverage_default_params = protocol_yml["pipeline"][ite]
        self.baselineaverage_default_params.insert(0, "Baseline Average")
        
      if protocol_yml["pipeline"][ite][0] == "SUSCEPTIBILITY_Correct":
        protocol_yml["pipeline"][ite][1]["protocol"]["configurationFilePath"] = self.preferences_yml["fslConfigurationFilePath"]
        self.susceptibility_default_params = protocol_yml["pipeline"][ite]
        self.susceptibility_default_params.insert(0, "Susceptibility correction")
        
      if protocol_yml["pipeline"][ite][0] == "EDDYMOTION_Correct":
        self.eddymotion_default_params = protocol_yml["pipeline"][ite]
        self.eddymotion_default_params.insert(0, "Eddy motion Correction")
        
      if protocol_yml["pipeline"][ite][0] == "BRAIN_Mask":
        self.brainmask_default_params = protocol_yml["pipeline"][ite]
        self.brainmask_default_params.insert(0, "Brain Masking")

      if protocol_yml["pipeline"][ite][0] == "DTI_Estimate":
        self.dtiestimate_default_params = protocol_yml["pipeline"][ite]
        self.dtiestimate_default_params.insert(0, "Estimate DTI")

      if protocol_yml["pipeline"][ite][0] == "MANUAL_Exclude":
        self.exclude_default_params = protocol_yml["pipeline"][ite]
        self.exclude_default_params.insert(0, "Exclude Gradients")
        
      if protocol_yml["pipeline"][ite][0] == "UTIL_Header":
        self.utilheader_default_params = protocol_yml["pipeline"][ite]
        self.utilheader_default_params.insert(0, "View Header")

      if protocol_yml["pipeline"][ite][0] == "UTIL_Merge":
        self.utilmerge_default_params = protocol_yml["pipeline"][ite]
        self.utilmerge_default_params.insert(0, "Merge Images")

      if protocol_yml["pipeline"][ite][0] == "QC_Report":
        self.qcreport_default_params = protocol_yml["pipeline"][ite]
        self.qcreport_default_params.insert(0, "QC Report")

      if protocol_yml['pipeline'][ite][0] == 'DTI_Register':
        self.dtiregister_default_params = protocol_yml['pipeline'][ite]
        self.dtiregister_default_params.insert(0, 'Register DTI (ANTs)')
      
      if protocol_yml['pipeline'][ite][0] == "SINGLETRACT_Process":
        self.singletract_default_params = protocol_yml['pipeline'][ite]
        self.singletract_default_params.insert(0, 'SINGLETRACT_Process DTI')

      if protocol_yml['pipeline'][ite][0] == "BRAIN_Tractography":
        self.braintractography_default_params = protocol_yml['pipeline'][ite]
        self.braintractography_default_params.insert(0, "Brain Tractography")

    self.slicecheck_params = self.slicecheck_default_params.copy()
    self.interlacecheck_params = self.interlacecheck_default_params.copy()
    self.baselineaverage_params = self.baselineaverage_default_params.copy()
    self.susceptibility_params = self.susceptibility_default_params.copy()
    self.eddymotion_params = self.eddymotion_default_params.copy()
    self.brainmask_params = self.brainmask_default_params.copy()
    self.dtiestimate_params = self.dtiestimate_default_params.copy()
    self.exclude_params = self.exclude_default_params.copy()
    self.utilheader_params = self.utilheader_default_params.copy()
    self.utilmerge_params = self.utilmerge_default_params.copy()
    self.qcreport_params = self.qcreport_default_params.copy()
    self.dtiregister_params = self.dtiregister_default_params.copy()
    # self.singletract_params = self.singletract_default_params.copy()
    self.braintractography_params = self.braintractography_default_params.copy()


  def SetDicProtocol(self, new_dic_protocol):
    self.dic_protocol = new_dic_protocol.copy()

  def SetModuleId(self, identifier):
    self.module_id = identifier

  def SetLoadingProtocol(self, new_value):
    self.loading_protocol = new_value

  def SettingDefaultProtocol(self, module_name):
    if module_name ==  "SLICE_Check":
      self.slicecheck_params = self.slicecheck_default_params
    if module_name == "INTERLACE_Check":
      self.interlacecheck_params = self.interlacecheck_default_params
    if module_name == "BASELINE_Average":
      self.baselineaverage_params = self.baselineaverage_default_params
    if module_name == "SUSCEPTIBILITY_Correct":
      self.susceptibility_params = self.susceptibility_default_params
    if module_name == "EDDYMOTION_Correct":
      self.eddymotion_params = self.eddymotion_default_params
    if module_name == "BRAIN_Masking":
      self.brainmask_params = self.brainmask_default_params
    if module_name == "DTI_Estimate":
      self.dtiestimate_params = self.dtiestimate_default_params
    if module_name == "MANUAL_Exclude":
      self.exclude_params = self.exclude_default_params
    #if module_name == "UTIL_Header":
    #  self.utilheader_params = self.utilheader_default_params
    #if module_name == "UTIL_Merge":
    #  self.utilmerge_params = self.utilmerge_default_params
    if module_name == "QC_Report":
      self.qcreport_params = self.qcreport_default_params
    if module_name == "DTI_Register":
      self.dtiregister_params = self.dtiregister_default_params
    if module_name == "SINGLETRACT_Process":
      self.singletract_params = self.singletract_default_params
    if module_name == "BRAIN_Tractography":
      self.braintractography_params = self.braintractography_default_params

  def RemoveModuleFromDicProtocol(self, item_to_remove_key):
    self.dic_protocol.pop(item_to_remove_key)
    
