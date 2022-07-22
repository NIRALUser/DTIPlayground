from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 

from dtiplayground.ui.modules_details_communicate import ModulesDetailsCommunicate

class BrainMask(QWidget):
  communicate = ModulesDetailsCommunicate()

  def __init__(self, protocol_template, brainmask_yml):
    QWidget.__init__(self)
    self.brainmask_yml = brainmask_yml
    self.method_it = 0
    self.averagingmethod_it = 0
    self.stack = QWidget()
    self.BrainMaskStack(protocol_template)

  def BrainMaskStack(self, protocol_template):

    ## Module
    self.tab_name = QLabel()
    
    ## Description
    for template_ite in range(len(protocol_template["options"]["execution"]["pipeline"]["candidates"])):
      if protocol_template["options"]["execution"]["pipeline"]["candidates"][template_ite]["value"] == "BRAIN_Mask":
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

    ## Protocol:
    protocol_groupbox = QGroupBox("Protocol:")
    protocol_layout = QVBoxLayout()
    protocol_sublayout1 = QFormLayout()
    protocol_sublayout2 = QHBoxLayout()
    protocol_groupbox.setLayout(protocol_layout)
    # method
    self.method = QComboBox()
    for ite in self.brainmask_yml["protocol"]["method"]["candidates"]:
      self.method.addItem(ite["caption"])
      self.method.setItemData(self.method.count()-1, ite["description"], QtCore.Qt.ToolTipRole)
    self.method.currentTextChanged.connect(self.GetMethodIt)
    self.method.setStatusTip(self.brainmask_yml["protocol"]["method"]["description"])
    protocol_sublayout1.addRow(self.brainmask_yml["protocol"]["method"]["caption"], self.method)
    self.method.currentTextChanged.connect(self.GetParams)
    # averaging method
    self.averagingmethod = QComboBox()
    for ite in self.brainmask_yml["protocol"]["averagingMethod"]["candidates"]:
      self.averagingmethod.addItem(ite["caption"])
      self.averagingmethod.setItemData(self.averagingmethod.count()-1, ite["description"], QtCore.Qt.ToolTipRole)
    self.averagingmethod.currentTextChanged.connect(self.GetAveragingMethodIt)
    self.averagingmethod.setStatusTip(self.brainmask_yml["protocol"]["averagingMethod"]["description"])
    protocol_sublayout1.addRow(self.brainmask_yml["protocol"]["averagingMethod"]["caption"], self.averagingmethod)
    self.averagingmethod.currentTextChanged.connect(self.GetParams)
    # modality
    self.modality_label = QLabel("Modality")
    self.modality_t2 = QRadioButton("T2")
    self.modality_fa = QRadioButton("FA")
    modality_buttongroup = QButtonGroup()
    modality_buttongroup.addButton(self.modality_t2)
    modality_buttongroup.addButton(self.modality_fa)
    #protocol_sublayout2.addWidget(self.modality_label)
    #protocol_sublayout2.addWidget(self.modality_fa)
    #protocol_sublayout2.addWidget(self.modality_t2)
    #self.method.currentTextChanged.connect(self.DisplayModality)  
    #self.GetModalityIt()
    self.modality_t2.toggled.connect(self.GetModalityIt)
    self.modality_t2.toggled.connect(self.GetParams)
    #self.modality_label.setStatusTip(self.brainmask_yml["protocol"]["modality"]["description"])
    #self.modality_t2.setToolTip(self.brainmask_yml["protocol"]["modality"]["candidates"][0]["description"])
    #self.modality_fa.setToolTip(self.brainmask_yml["protocol"]["modality"]["candidates"][1]["description"])

    ## Layout
    protocol_layout.addLayout(protocol_sublayout1)
    protocol_layout.addLayout(protocol_sublayout2)
    layout_v = QVBoxLayout()
    layout_v.addWidget(self.tab_name)
    layout_v.addWidget(description_label)
    layout_v.addWidget(options_groupbox)
    layout_v.addWidget(protocol_groupbox)
    layout_v.addStretch(1)
    self.stack.setLayout(layout_v)

  def GetMethodIt(self, text): # get "method" parameter
    self.method_it = 0
    for it in range(len(self.brainmask_yml["protocol"]["method"]["candidates"])):
      if self.brainmask_yml["protocol"]["method"]["candidates"][it]["caption"] == text:
        self.method_it = it

  def GetAveragingMethodIt(self, text): # get "average method" parameter
    for it in range(len(self.brainmask_yml["protocol"]["averagingMethod"]["candidates"])):
      if self.brainmask_yml["protocol"]["averagingMethod"]["candidates"][it]["caption"] == text:
        self.averagingmethod_it = it

  def GetModalityIt(self): # get "modality" parameter
    self.modality_it = 0
    if self.modality_t2.isChecked():
      self.modality_it = 0
    if self.modality_fa.isChecked():
      self.modality_it = 1

  def DisplayModality(self):
    if self.method.currentText() != "AntsPyNet":
      self.modality_t2.setHidden(True)
      self.modality_fa.setHidden(True)
      self.modality_label.setHidden(True)
    else:
      self.modality_t2.setHidden(False)
      self.modality_fa.setHidden(False)
      self.modality_label.setHidden(False)

  def GetParams(self):
    params = [
      'Brain Masking',
      'BRAIN_Mask', 
      {'options': {
        'overwrite': self.overwrite.isChecked(), 
        'skip': self.skip.isChecked(), 
        }, 
      'protocol': {
        'averagingMethod': self.brainmask_yml["protocol"]["averagingMethod"]["candidates"][self.averagingmethod_it]["value"],
        'method': self.brainmask_yml["protocol"]["method"]["candidates"][self.method_it]["value"], 
        #'modality': self.brainmask_yml["protocol"]["modality"]["candidates"][self.modality_it]["value"]
        }
      }
    ]
    self.communicate.SendParams(params)