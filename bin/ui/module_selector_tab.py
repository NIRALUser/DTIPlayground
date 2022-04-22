from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 
from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSignal as Signal


class ModuleSelectorCommunicate(QObject):

  set_drop_mode_protocol_list_widget = Signal()
  module_added_to_protocol_drop = Signal(list)

  def SetDropModeProtocolListWidget(self):
    self.set_drop_mode_protocol_list_widget.emit()

  def ModuleAddedToProtocolDrop(self, list_modules):
    self.module_added_to_protocol_drop.emit(list_modules)

class ModuleSelector(QWidget):

  communicate = ModuleSelectorCommunicate()

  def __init__(self, protocol_template):
    QWidget.__init__(self)
    self.protocol_template = protocol_template
    self.tab = QWidget()
    self.ModuleSelectorList()

  def ModuleSelectorList(self):
    modules_list_label = QLabel("Module Selector")
    self.modules_list_widget = QListWidget()    
    self.modules_list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)

    # setting drag drop mode
    self.modules_list_widget.setDragDropMode(QAbstractItemView.DragOnly)
    self.modules_list_widget.itemPressed.connect(self.DragDropMode)
    self.modules_list_widget.itemSelectionChanged.connect(self.ModulesMultiSelection)
    
    module_id = 0
    for module_iterator in self.protocol_template["options"]["execution"]["pipeline"]["candidates"]:
      if module_iterator["description"] != "Not implemented":
        new_module = QListWidgetItem()
        new_module.setText(module_iterator["caption"])
        new_module.setData(QtCore.Qt.UserRole, module_id)
        module_id += 1
        self.modules_list_widget.addItem(new_module)

    layout_v = QVBoxLayout()
    layout_v.addWidget(modules_list_label)
    layout_v.addWidget(self.modules_list_widget)
    self.tab.setLayout(layout_v)

  def DragDropMode(self):
    self.communicate.SetDropModeProtocolListWidget()
    self.modules_list_widget.setDefaultDropAction(Qt.CopyAction)

  def ModulesMultiSelection(self):
    self.modules_list_widget.blockSignals(True)
    group_selection_with_exclude = False
    if len(self.modules_list_widget.selectedItems()) > 1:
      for module in self.modules_list_widget.selectedItems():
        if module.text() == "Exclude Gradients":
          group_selection_with_exclude = True
          self.exclude_popup.exec_()
          break
      if group_selection_with_exclude:
        for module in self.modules_list_widget.selectedItems():
          module.setSelected(False)
    self.modules_list_widget.blockSignals(False)

  def GetListWidgetSelectedModules(self):
    modules_list = self.modules_list_widget.selectedItems()
    self.communicate.ModuleAddedToProtocolDrop(modules_list)

  def EnableModulesListWidget(self, new_state):
    self.modules_list_widget.setEnabled(new_state)

  def EnableExcludeGradientsModule(self, enable):
    if enable == True:
      self.modules_list_widget.findItems("Exclude Gradients", Qt.MatchExactly)[0].setFlags(self.modules_list_widget.findItems("Exclude Gradients", Qt.MatchExactly)[0].flags() | Qt.ItemIsEnabled)
    else:
      self.modules_list_widget.findItems("Exclude Gradients", Qt.MatchExactly)[0].setFlags(self.modules_list_widget.findItems("Exclude Gradients", Qt.MatchExactly)[0].flags() & ~Qt.ItemIsEnabled)