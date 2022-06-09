from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 

from dtiplayground.ui.modules_details_communicate import ModulesDetailsCommunicate

class SusceptibilityCorrection(QWidget):
  communicate = ModulesDetailsCommunicate()

  def __init__(self, protocol_template, susceptibility_yml, preferences_yml):
    QWidget.__init__(self)
    self.preferences_yml = preferences_yml
    self.stack = QWidget()
    self.SusceptibilityCorrectionStack(protocol_template, susceptibility_yml)

  def SusceptibilityCorrectionStack(self, protocol_template, susceptibility_yml):

    ## Module
    self.tab_name = QLabel()

    ## Description
    for template_ite in range(len(protocol_template["options"]["execution"]["pipeline"]["candidates"])):
      if protocol_template["options"]["execution"]["pipeline"]["candidates"][template_ite]["value"] == "SUSCEPTIBILITY_Correct":
        description_label = QLabel(protocol_template["options"]["execution"]["pipeline"]["candidates"][template_ite]["description"])
    description_label.setWordWrap(True)

    ## Options:
    options_groupbox = QGroupBox("Options:")
    options_layout = QGridLayout()
    options_groupbox.setLayout(options_layout)   
    # overwrite
    self.overwrite = QCheckBox("Overwrite")
    self.overwrite.stateChanged.connect(self.GetParams)
    options_layout.addWidget(self.overwrite, 0, 0)
    # skip
    self.skip = QCheckBox("Skip")
    self.skip.stateChanged.connect(self.GetParams)
    options_layout.addWidget(self.skip, 0, 1)
    # write image
    self.writeimage = QCheckBox("Write Image")
    self.writeimage.stateChanged.connect(self.GetParams)
    options_layout.addWidget(self.writeimage, 0, 2)

    ## Protocol:
    protocol_groupbox = QGroupBox("Protocol:")
    protocol_layout = QGridLayout()
    protocol_sublayout = QGridLayout()
    protocol_groupbox.setLayout(protocol_layout)
    # phaseEncodingAxis
    self.phaseEncodingAxis_list = []
    protocol_layout.addWidget(QLabel("Phase Encoding Axis"), 0, 0, 1, 3)
    protocol_layout.addWidget(QLabel(susceptibility_yml["protocol"]["phaseEncodingAxis"]["caption"]), 0, 3, 1, 3)
    self.phaseEncodingAxis_p0 = QCheckBox("+0")
    self.phaseEncodingAxis_p1 = QCheckBox("+1")
    self.phaseEncodingAxis_p2 = QCheckBox("+2")

    self.phaseEncodingAxis_n0 = QCheckBox("-0") # for later implementation 
    self.phaseEncodingAxis_n1 = QCheckBox("-1")    
    self.phaseEncodingAxis_n2 = QCheckBox("-2")
    self.phaseEncodingAxis_n0.setEnabled(False)
    self.phaseEncodingAxis_n1.setEnabled(False)
    self.phaseEncodingAxis_n2.setEnabled(False)
    
    protocol_layout.addWidget(self.phaseEncodingAxis_n0, 1, 0)
    protocol_layout.addWidget(self.phaseEncodingAxis_p0, 1, 1)
    protocol_layout.addWidget(self.phaseEncodingAxis_n1, 1, 2)
    protocol_layout.addWidget(self.phaseEncodingAxis_p1, 1, 3)
    protocol_layout.addWidget(self.phaseEncodingAxis_n2, 1, 4)
    protocol_layout.addWidget(self.phaseEncodingAxis_p2, 1, 5)
    
    self.phaseEncodingAxis = QListWidget()
    self.phaseEncodingAxis.setDragDropMode(QAbstractItemView.InternalMove)
    self.phaseEncodingAxis.setSelectionMode(QAbstractItemView.ExtendedSelection)
    self.phaseEncodingAxis.model().rowsMoved.connect(self.UpdatePhaseEncodingAxisList)
    protocol_layout.addWidget(self.phaseEncodingAxis, 0, 6, 2, 1)
    self.phaseEncodingAxis_p0.stateChanged.connect(self.UpdatePhaseEncodingAxisWidget)
    self.phaseEncodingAxis_p0.stateChanged.connect(self.GetParams)
    self.phaseEncodingAxis_p1.stateChanged.connect(self.UpdatePhaseEncodingAxisWidget)
    self.phaseEncodingAxis_p1.stateChanged.connect(self.GetParams)
    self.phaseEncodingAxis_p2.stateChanged.connect(self.UpdatePhaseEncodingAxisWidget)
    self.phaseEncodingAxis_p2.stateChanged.connect(self.GetParams)
    # phaseEncodingValue
    self.phaseEncodingValue = QDoubleSpinBox()
    self.phaseEncodingValue.setAlignment(Qt.AlignRight)
    self.phaseEncodingValue.setSingleStep(0.001)
    self.phaseEncodingValue.setDecimals(3)
    self.phaseEncodingValue.setStatusTip(susceptibility_yml["protocol"]["phaseEncodingValue"]["description"])
    protocol_sublayout.addWidget(QLabel(susceptibility_yml["protocol"]["phaseEncodingValue"]["caption"]), 0, 0, 1, 1)
    protocol_sublayout.addWidget(self.phaseEncodingValue, 0, 1, 1, 4)
    self.phaseEncodingValue.valueChanged.connect(self.GetParams)
    # configurationFilePath
    self.configurationFilePath = QLineEdit()
    self.configurationFilePath.setStatusTip(susceptibility_yml["protocol"]["configurationFilePath"]["description"])
    protocol_sublayout.addWidget(QLabel(susceptibility_yml["protocol"]["configurationFilePath"]["caption"]), 1, 0, 1, 1)
    protocol_sublayout.addWidget(self.configurationFilePath, 2, 0, 1, 5)
    self.configurationFilePath_browse = QPushButton("Browse")
    protocol_sublayout.addWidget(self.configurationFilePath_browse, 1, 1, 1, 1)
    self.configurationFilePath.textChanged.connect(self.GetParams)
    self.configurationFilePath_browse.clicked.connect(self.BrowseFSLConfigFilePath)

    ## Layout
    for i in range(7):
      protocol_layout.setColumnStretch(i, 2)
    for i in range(4):
      protocol_layout.setRowStretch(i, 1)
    protocol_layout.addLayout(protocol_sublayout, 2, 0, 1, 7)
    
    layout_v = QVBoxLayout()
    layout_v.addWidget(self.tab_name)
    layout_v.addWidget(description_label)
    layout_v.addWidget(options_groupbox)
    layout_v.addWidget(protocol_groupbox)
    layout_v.addStretch(1)
    self.stack.setLayout(layout_v)

  def UpdatePhaseEncodingAxisWidget(self): # update QListWidget according to selected axis
    if self.phaseEncodingAxis_p0.isChecked():
      #if 0 not in list, then add it; else do nothing
      item_in_list = self.phaseEncodingAxis.findItems("0", Qt.MatchFixedString) # (QListWidget are not iterable)
      if not item_in_list:
        self.phaseEncodingAxis.addItem("0")
    else:
      #if 0 in list, then remove it; else do nothing
      item_in_list = self.phaseEncodingAxis.findItems("0", Qt.MatchFixedString)
      if item_in_list:
        self.phaseEncodingAxis.takeItem(self.phaseEncodingAxis.row(item_in_list[0]))
    
    if self.phaseEncodingAxis_p1.isChecked():
      #if 1 not in list, then add it; else do nothing
      item_in_list = self.phaseEncodingAxis.findItems("1", Qt.MatchFixedString)
      if not item_in_list:
        self.phaseEncodingAxis.addItem("1")      
    else:
      #if 1 in list, then remove it; else do nothing
      item_in_list = self.phaseEncodingAxis.findItems("1", Qt.MatchFixedString)
      if item_in_list:
        self.phaseEncodingAxis.takeItem(self.phaseEncodingAxis.row(item_in_list[0]))

    if self.phaseEncodingAxis_p2.isChecked():
      #if 2 not in list, then add it; else do nothing
      item_in_list = self.phaseEncodingAxis.findItems("2", Qt.MatchFixedString)
      if not item_in_list:
        self.phaseEncodingAxis.addItem("2") 
    else:
      #if 2 in list, then remove it; else do nothing
      item_in_list = self.phaseEncodingAxis.findItems("2", Qt.MatchFixedString)
      if item_in_list:
        self.phaseEncodingAxis.takeItem(self.phaseEncodingAxis.row(item_in_list[0]))
    self.UpdatePhaseEncodingAxisList()
    
  def UpdatePhaseEncodingAxisList(self): # update list according to QListWidget
    self.phaseEncodingAxis_list = []
    for ite in range(self.phaseEncodingAxis.count()):
      self.phaseEncodingAxis_list.append(int(self.phaseEncodingAxis.item(ite).text()))
    self.GetParams()

  def BrowseFSLConfigFilePath(self):
    file_filter = "Configuration file (*.cnf)"
    file_path = QFileDialog.getOpenFileName(
      parent = self,
      caption = "Select an configuration file",
      filter = file_filter
      )
    file_path = file_path[0]
    if file_path != "":
      self.preferences_yml["fslConfigurationFilePath"] = file_path
      self.configurationFilePath.setText(self.preferences_yml["fslConfigurationFilePath"])
      self.communicate.CallUpdateUserPreferencesFile(self.preferences_yml)

  def GetParams(self):
    params = [
      'Susceptibility correction',
      'SUSCEPTIBILITY_Correct', 
      {'options': {
        'overwrite': self.overwrite.isChecked(), 
        'skip': self.skip.isChecked(), 
        'write_image': self.writeimage.isChecked()
        }, 
      'protocol': {
        'configurationFilePath': self.configurationFilePath.text(), 
        'phaseEncodingAxis': self.phaseEncodingAxis_list, 
        'phaseEncodingValue': self.phaseEncodingValue.value()
        }
      } 
    ]
    self.communicate.SendParams(params)
