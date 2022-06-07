from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 
import os
from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSignal as Signal

from dtiplayground.ui.module_selector_tab import ModuleSelector
from dtiplayground.ui.modules_details_tab import ModuleDetails
from dtiplayground.ui.general_tab import General

class ProtocolTabCommunicate(QObject):
  
  call_module_added_to_protocol = Signal()
  call_unsaved_modif = Signal()
  call_order_modules_in_protocol_list = Signal()
  set_loading_protocol = Signal(bool)
  get_module_id = Signal()
  set_module_id = Signal(int)
  call_set_default_protocol = Signal(str)
  call_read_protocol = Signal(str)
  call_remove_module_from_dic_protocol = Signal (int)
  enable_eddymotion_param = Signal(bool)
  set_dic_protocol = Signal(dict)
  call_no_unsaved_modif = Signal()
  call_write_protocol_yml = Signal(str)
  module_added_to_protocol_loading = Signal(list)
  call_update_user_preferences_file = Signal(dict)

  def CallModuleAddedToProtocol(self):
    self.call_module_added_to_protocol.emit()

  def CallUnsavedModif(self):
    self.call_unsaved_modif.emit()

  def CallOrderModulesInProtocolList(self):
    self.call_order_modules_in_protocol_list.emit()

  def SetLoadingProtocol(self, loading_protocol):
    self.set_loading_protocol.emit(loading_protocol)

  def GetModuleId(self):
    self.get_module_id.emit()
  
  def SetModuleId(self, new_id):
    self.set_module_id.emit(new_id)

  def CallSetDefaultProtocol(self, module_name):
    self.call_set_default_protocol.emit(module_name)

  def CallReadProtocol(self, filename):
    self.call_read_protocol.emit(filename)

  def CallRemoveModuleFromDicProtocol(self, key):
    self.call_remove_module_from_dic_protocol.emit(key)

  def EnableEddyMotionParam(self, value):
    self.enable_eddymotion_param.emit(value)

  def SetDicProtocol(self, new_dic_protocol):
    self.set_dic_protocol.emit(new_dic_protocol)

  def CallNoUnsavedModif(self):
    self.call_no_unsaved_modif.emit()

  def CallWriteProtocolYML(self, filename):
    self.call_write_protocol_yml.emit(filename)

  def ModuleAddedToProtocolLoading(self, list_modules):
    self.module_added_to_protocol_loading.emit(list_modules)

  def CallUpdateUserPreferencesFile(self, new_preferences):
    self.call_update_user_preferences_file.emit(new_preferences)


class ProtocolTab(QWidget):
  communicate = ProtocolTabCommunicate()

  def __init__(self, protocol_template, protocol_yml, preferences_yml):
    QWidget.__init__(self)
    self.preferences_yml = preferences_yml
    self.protocol_template = protocol_template
    self.tab = QWidget()

    # Tabs
    self.subtabs = QTabWidget()
    self.selector = ModuleSelector(self.protocol_template)
    self.details = ModuleDetails(self.protocol_template, preferences_yml) 
    self.general = General(self.protocol_template, protocol_yml) 
    self.subtabs.addTab(self.selector.tab, "Select")
    self.subtabs.addTab(self.details.tab, "Module Details")
    self.subtabs.addTab(self.general.tab, "General")
    self.subtabs.tabBarClicked.connect(self.details.ModuleDetailsClicked)    

    self.details.communicate.set_modules_details_tab.connect(self.SetDetailsDisplayTab)
    self.ProtocolTab()
    self.selector.communicate.set_drop_mode_protocol_list_widget.connect(lambda: self.protocol_list_widget.setDragDropMode(QAbstractItemView.DropOnly))
    self.ExcludePopup()
    self.MergePopup()

  def ProtocolTab(self):
    
    ### Protocol file path
    protocol_list_label = QLabel("Protocol:")
    if not hasattr(self, 'protocol_filename'):
      self.protocol_filename = os.getcwd() + "/protocol.yml"
    self.protocol_path_label = QLabel(self.protocol_filename)
    self.protocol_path_label.setWordWrap(True)

    ### Protocol List    
    self.protocol_list_widget = QListWidget()
    self.protocol_list_widget.setMouseTracking(True)
    self.protocol_list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
    self.protocol_list_widget.setDragDropMode(QAbstractItemView.InternalMove) # default mode
    self.protocol_list_widget.itemPressed.connect(self.InternalMoveMode)
    self.protocol_list_widget.itemClicked.connect(self.GetSelectedItemData)
    self.protocol_list_widget.model().rowsInserted.connect(self.communicate.CallModuleAddedToProtocol)
    self.protocol_list_widget.model().rowsMoved.connect(self.communicate.CallUnsavedModif)
    self.protocol_list_widget.model().rowsMoved.connect(self.communicate.CallOrderModulesInProtocolList)

    ### Buttons
    # Default protocol button
    self.default_protocol_button = QPushButton("Default Protocol")
    self.default_protocol_button.clicked.connect(self.communicate.GetModuleId)
    self.default_protocol_button.setStatusTip("Sets the default protocol") 
    # Load protocol button
    self.load_protocol_button = QPushButton("Load Protocol")
    self.load_protocol_button.clicked.connect(self.LoadProtocol)
    self.load_protocol_button.setStatusTip("Load protocol file to use")    
    # Remove button
    self.remove_button = QPushButton("Remove selected module(s)")
    self.remove_button.clicked.connect(self.RemoveModule)
    self.remove_button.setStatusTip("Remove selected module(s) from the protocol list (DEL)") 
    # Clear button
    self.clear_button = QPushButton("Clear protocol")
    self.clear_button.clicked.connect(self.ClearProtocol)
    self.clear_button.setStatusTip("Remove all modules from the protocol list")    
    # Save button
    self.save_button = QPushButton("Save protocol")
    self.save_button.clicked.connect(self.SaveProtocol)
    self.save_button.setStatusTip("Save protocol file")    
    # Save As button
    self.saveas_button = QPushButton("Save protocol as...")
    self.saveas_button.clicked.connect(self.SaveAs)
    self.saveas_button.setStatusTip("Save protocol file as...")    

    ### Layout
    layout_protocol_h1 = QHBoxLayout()
    layout_protocol_h1.addWidget(self.remove_button)
    layout_protocol_h1.addWidget(self.clear_button)

    layout_protocol_v1 = QVBoxLayout()
    layout_protocol_v1.addWidget(protocol_list_label)
    layout_protocol_v1.addWidget(self.protocol_path_label)
    layout_protocol_v1.addWidget(self.default_protocol_button)
    layout_protocol_v1.addWidget(self.load_protocol_button)
    layout_protocol_v1.addWidget(self.protocol_list_widget)
    layout_protocol_v1.addLayout(layout_protocol_h1)
    layout_protocol_v1.addWidget(self.save_button)
    layout_protocol_v1.addWidget(self.saveas_button)
        
    layout_protocol_v2 = QVBoxLayout()
    layout_protocol_v2.addWidget(self.subtabs)

    layout_protocol = QHBoxLayout()
    layout_protocol.addLayout(layout_protocol_v1)
    layout_protocol.addLayout(layout_protocol_v2)
    self.tab.setLayout(layout_protocol)

  def InternalMoveMode(self):
    self.protocol_list_widget.setDragDropMode(QAbstractItemView.InternalMove)

  def DefaultProtocol(self, module_id):
    self.ClearProtocol()
    self.details.details_stack.setCurrentIndex(0)

    self.communicate.SetLoadingProtocol(True)

    for module_iterator_1 in self.protocol_template["options"]["execution"]["pipeline"]["default_value"]:
      for module_iterator_2 in self.protocol_template["options"]["execution"]["pipeline"]["candidates"]:
        if module_iterator_2["value"] == module_iterator_1:
          new_module = QListWidgetItem()
          new_module.setText(module_iterator_2["caption"])
          new_module.setData(QtCore.Qt.UserRole, module_id)
          new_module.setToolTip(module_iterator_2["description"])
          self.protocol_list_widget.addItem(new_module)
          module_id += 1

          self.communicate.CallSetDefaultProtocol(module_iterator_2["value"])
    self.communicate.SetModuleId(module_id)
    self.communicate.CallModuleAddedToProtocol()
    self.communicate.SetLoadingProtocol(False)

            
  def LoadProtocol(self):
    protocol_filter = "Protocol file (*.yaml *.yml)"
    input_protocol = QFileDialog.getOpenFileName(
      parent = self,
      caption = "Select a protocol file",
      filter = protocol_filter
    )
    filename = input_protocol[0]
    if filename != "":
      self.protocol_filename = filename
      self.protocol_path_label.setText(self.protocol_filename)
      self.communicate.CallReadProtocol(self.protocol_filename)
      self.details.details_stack.setCurrentIndex(0)

  def RemoveModule(self):

    self.communicate.CallOrderModulesInProtocolList()

    items = self.protocol_list_widget.selectedItems()

    for i in items:
      removed_item_index = self.protocol_list_widget.indexFromItem(i).row()
      removed_item_key = i.data(QtCore.Qt.UserRole)
      self.communicate.CallRemoveModuleFromDicProtocol(removed_item_key)
      removed_item = self.protocol_list_widget.takeItem(removed_item_index)
      if removed_item.text() == "Exclude Gradients":
        self.selector.EnableModulesListWidget(True)
      if removed_item.text() == "Susceptibility correction":
        self.communicate.EnableEddyMotionParam(False)

    if self.protocol_list_widget.count() == 0:
      self.selector.EnableExcludeGradientsModule(True)
      self.selector.EnableMergeImagesModule(True)
      self.selector.EnableModulesListWidget(True) 
      self.details.details_stack.setCurrentIndex(0)

    if len(items) > 0:
      self.communicate.CallUnsavedModif()
    
  def ClearProtocol(self):    
    self.subtabs.setCurrentIndex(0)

    if self.protocol_list_widget.count() > 0:
      self.communicate.CallUnsavedModif()

    for ite in range(self.protocol_list_widget.count()):
      removed_item = self.protocol_list_widget.takeItem(0)
    self.selector.EnableModulesListWidget(True)  
    self.selector.EnableExcludeGradientsModule(True)
    self.selector.EnableMergeImagesModule(True)
    self.communicate.EnableEddyMotionParam(False)
    self.communicate.SetDicProtocol({})

  def SaveAs(self):
    file_filter = "Protocol file (*.yml *.yaml)"
    filename = QFileDialog.getSaveFileName(
      parent = self,
      caption = "Select a protocol file",
      directory = "protocol.yml",
      filter = file_filter
      )
    if filename[0] != "":
      self.protocol_filename = filename[0]
      self.protocol_path_label.setText(self.protocol_filename)
      self.SaveProtocol()
      print("protocol saved as ", self.protocol_filename)

  def SaveProtocol(self):
    if not hasattr(self, 'protocol_filename'):
      self.protocol_filename = os.getcwd() + "/protocol.yml"
    self.communicate.CallOrderModulesInProtocolList()
    self.communicate.CallWriteProtocolYML(self.protocol_filename)
    self.communicate.CallNoUnsavedModif()

  def ExcludePopup(self):
    self.exclude_popup = QMessageBox()
    self.exclude_popup.setText("The Exclude Gradients module must run separately.")
    self.exclude_popup.setWindowTitle("DMRIPrep message")
    self.notshowagain_exclude = QCheckBox("Do not show again.")
    self.notshowagain_exclude.stateChanged.connect(self.NotShowAgainExcludePopupStateChanged)
    self.exclude_popup.setCheckBox(self.notshowagain_exclude)
    
  def NotShowAgainExcludePopupStateChanged(self):
    if self.notshowagain_exclude.isChecked():
      self.preferences_yml["showExcludeGradientsPopup"] = False
    else:
      self.preferences_yml["showExcludeGradientsPopup"] = True
    self.communicate.CallUpdateUserPreferencesFile(self.preferences_yml)

  def MergePopup(self):
    self.merge_popup = QMessageBox()
    self.merge_popup.setText("The Merge Images module must run separately.")
    self.merge_popup.setWindowTitle("DMRIPrep message")
    self.notshowagain_merge = QCheckBox("Do not show again.")
    self.notshowagain_merge.stateChanged.connect(self.NotShowAgainMergePopupStateChanged)
    self.merge_popup.setCheckBox(self.notshowagain_merge)
    
  def NotShowAgainMergePopupStateChanged(self):
    if self.notshowagain_merge.isChecked():
      self.preferences_yml["showMergeImagesPopup"] = False
    else:
      self.preferences_yml["showMergeImagesPopup"] = True
    self.communicate.CallUpdateUserPreferencesFile(self.preferences_yml)

  def SetDetailsDisplayTab(self):
    if self.subtabs.currentIndex() != 1: # if the active tab is not "Module Details"
      self.subtabs.setCurrentIndex(1)

  def GetSelectedItemData(self):
    item = self.protocol_list_widget.selectedItems()[0]
    data = item.data(QtCore.Qt.UserRole) #module_id, in dic_protocol (dictionary)
    index = self.protocol_list_widget.row(item)
    self.details.communicate.SendSelectedItemData([data, index])

  def AddModuleToProtocolWidget(self, module):
    new_module = QListWidgetItem()
    new_module.setText(module["caption"])
    new_module.setData(QtCore.Qt.UserRole, module["id"])
    new_module.setToolTip(module["description"])
    self.protocol_list_widget.addItem(new_module)

  def GetListWidgetModules(self):
    modules_list = []
    for module_iter in range(self.protocol_list_widget.count()):
      module = self.protocol_list_widget.item(module_iter)
      modules_list.append(module)
    self.communicate.ModuleAddedToProtocolLoading(modules_list)

  def SetModuleData(self, module_and_data):
    module = module_and_data[0]
    data = module_and_data[1]
    module.setData(QtCore.Qt.UserRole, data) #new module id
