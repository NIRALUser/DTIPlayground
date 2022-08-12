from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 

from dtiplayground.ui.modules_details_communicate import ModulesDetailsCommunicate

class Singletract(QWidget):
  communicate = ModulesDetailsCommunicate()

  def __init__(self, protocol_template, singletract_yml):
    QWidget.__init__(self)
    self.singletract_yml = singletract_yml
    self.method_it = 0
    self.scalar_it = 0
    self.stack = QWidget()
    self.SingletractStack(protocol_template)

  def SingletractStack(self, protocol_template):

    ## Module
    self.tab_name = QLabel()

    ## Description
    for template_ite in range(len(protocol_template["options"]["execution"]["pipeline"]["candidates"])):
      if protocol_template["options"]["execution"]["pipeline"]["candidates"][template_ite]["value"] == "SINGLETRACT_Process":
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
    protocol_layout = QFormLayout()
    protocol_groupbox.setLayout(protocol_layout)
    # method
    self.method = QComboBox()
    for ite in self.singletract_yml["protocol"]["method"]["candidates"]:
      self.method.addItem(ite["caption"])
      self.method.setItemData(self.method.count()-1, ite["description"], QtCore.Qt.ToolTipRole)
    self.method.currentTextChanged.connect(self.GetMethodIt)
    self.method.setStatusTip(self.singletract_yml["protocol"]["method"]["description"])
    protocol_layout.addRow(self.singletract_yml["protocol"]["method"]["caption"], self.method)
    self.method.currentTextChanged.connect(self.GetParams)
    # scalar
    self.scalar = QComboBox()
    for ite in self.singletract_yml["protocol"]["scalar"]["candidates"]:
      self.scalar.addItem(ite["caption"])
      self.scalar.setItemData(self.scalar.count()-1, ite["description"], QtCore.Qt.ToolTipRole)
    self.scalar.currentTextChanged.connect(self.GetScalarIt)
    #self.scalar.setStatusTip(self.singletract_yml["protocol"]["scalar"]["description"])
    protocol_layout.addRow(self.singletract_yml["protocol"]["scalar"]["caption"], self.scalar)
    self.scalar.currentTextChanged.connect(self.GetParams)
    # NIRALUtilitiesPath
    self.NIRALUtilitiesPath = QLineEdit()
    self.NIRALUtilitiesPath.setAlignment(Qt.AlignRight)
    self.NIRALUtilitiesPath.setStatusTip(self.singletract_yml["protocol"]["NIRALUtilitiesPath"]["description"])
    protocol_layout.addRow(self.singletract_yml["protocol"]["NIRALUtilitiesPath"]["caption"], self.NIRALUtilitiesPath)
    self.NIRALUtilitiesPath.textChanged.connect(self.GetParams)
    # referenceTractFile
    self.referenceTractFile = QLineEdit()
    self.referenceTractFile.setAlignment(Qt.AlignRight)
    self.referenceTractFile.setStatusTip(self.singletract_yml["protocol"]["referenceTractFile"]["description"])
    protocol_layout.addRow(self.singletract_yml["protocol"]["referenceTractFile"]["caption"], self.referenceTractFile)
    self.referenceTractFile.textChanged.connect(self.GetParams)
    # displacementFieldFile
    self.displacementFieldFile = QLineEdit()
    self.displacementFieldFile.setAlignment(Qt.AlignRight)
    self.displacementFieldFile.setStatusTip(self.singletract_yml["protocol"]["displacementFieldFile"]["description"])
    protocol_layout.addRow(self.singletract_yml["protocol"]["displacementFieldFile"]["caption"], self.displacementFieldFile)
    self.displacementFieldFile.textChanged.connect(self.GetParams)
    # dilationRadius
    self.dilationRadius = QSpinBox()
    self.dilationRadius.setAlignment(Qt.AlignRight)
    self.dilationRadius.setStatusTip(self.singletract_yml["protocol"]["dilationRadius"]["description"])
    protocol_layout.addRow(self.singletract_yml["protocol"]["dilationRadius"]["caption"], self.dilationRadius) 
    self.dilationRadius.valueChanged.connect(self.GetParams)
    
    ## Layout
    layout_v = QVBoxLayout()
    layout_v.addWidget(self.tab_name)
    layout_v.addWidget(description_label)
    layout_v.addWidget(options_groupbox)
    layout_v.addWidget(protocol_groupbox)
    layout_v.addStretch(1)
    self.stack.setLayout(layout_v)

  
  def GetMethodIt(self, text): # dti register parameter
    for it in range(len(self.singletract_yml["protocol"]["method"]["candidates"])):
      if self.singletract_yml["protocol"]["method"]["candidates"][it]["caption"] == text:
        self.method_it = it

  def GetScalarIt(self, text): # dti register parameter
    for it in range(len(self.singletract_yml["protocol"]["scalar"]["candidates"])):
      if self.singletract_yml["protocol"]["scalar"]["candidates"][it]["caption"] == text:
        self.scalar_it = it

  def GetSimilarityMetricIt(self, text): # dti register parameter
    for it in range(len(self.singletract_yml["protocol"]["similarityMetric"]["candidates"])):
      if self.singletract_yml["protocol"]["similarityMetric"]["candidates"][it]["caption"] == text:
        self.similarityMetric_it = it


  def GetParams(self):
    params = [
      'Register DTI (ANTs)',
      'SINGLETRACT_Process', 
      {'options': {
        'overwrite': self.overwrite.isChecked(), 
        'skip': self.skip.isChecked(), 
        'write_image': self.writeimage.isChecked()
        }, 
      'protocol': {
        'method': self.singletract_yml["protocol"]["method"]["candidates"][self.method_it]["value"], 
        'scalar': self.singletract_yml['protocol']['scalar']['candidates'][self.scalar_it]['value'],
        'NIRALUtilitiesPath': self.NIRALUtilitiesPath.text(),
        'referenceTractFile': self.referenceTractFile.text(), 
        'displacementFieldFile': self.displacementFieldFile.text(),
        'dilationRadius': self.dilationRadius.value()
        }
      }
    ]
    self.communicate.SendParams(params)