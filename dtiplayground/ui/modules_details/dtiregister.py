from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 

from dtiplayground.ui.modules_details_communicate import ModulesDetailsCommunicate

class DTIRegister(QWidget):
  communicate = ModulesDetailsCommunicate()

  def __init__(self, protocol_template, dtiregister_yml):
    QWidget.__init__(self)
    self.dtiregister_yml = dtiregister_yml
    self.method_it = 0
    self.registrationType_it = 0
    self.similarityMetric_it = 0
    self.stack = QWidget()
    self.DTIRegisterStack(protocol_template)

  def DTIRegisterStack(self, protocol_template):

    ## Module
    self.tab_name = QLabel()

    ## Description
    for template_ite in range(len(protocol_template["options"]["execution"]["pipeline"]["candidates"])):
      if protocol_template["options"]["execution"]["pipeline"]["candidates"][template_ite]["value"] == "DTI_Register":
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
    for ite in self.dtiregister_yml["protocol"]["method"]["candidates"]:
      self.method.addItem(ite["caption"])
      self.method.setItemData(self.method.count()-1, ite["description"], QtCore.Qt.ToolTipRole)
    self.method.currentTextChanged.connect(self.GetMethodIt)
    self.method.setStatusTip(self.dtiregister_yml["protocol"]["method"]["description"])
    protocol_layout.addRow(self.dtiregister_yml["protocol"]["method"]["caption"], self.method)
    self.method.currentTextChanged.connect(self.GetParams)
    # referenceImage
    self.referenceImage = QLineEdit()
    self.referenceImage.setAlignment(Qt.AlignRight)
    self.referenceImage.setStatusTip(self.dtiregister_yml["protocol"]["referenceImage"]["description"])
    protocol_layout.addRow(self.dtiregister_yml["protocol"]["referenceImage"]["caption"], self.referenceImage)
    self.referenceImage.textChanged.connect(self.GetParams)
    # ANTsPath
    self.ANTsPath = QLineEdit()
    self.ANTsPath.setAlignment(Qt.AlignRight)
    self.ANTsPath.setStatusTip(self.dtiregister_yml["protocol"]["ANTsPath"]["description"])
    #protocol_layout.addRow(self.dtiregister_yml["protocol"]["ANTsPath"]["caption"], self.ANTsPath)
    #self.ANTsPath.textChanged.connect(self.GetParams)
    # ANTsMethod
    self.ANTsMethod = QLineEdit()
    self.ANTsMethod.setAlignment(Qt.AlignRight)
    #self.ANTsMethod.setStatusTip(self.dtiregister_yml["protocol"]["ANTsMethod"]["description"])
    protocol_layout.addRow(self.dtiregister_yml["protocol"]["ANTsMethod"]["caption"], self.ANTsMethod)
    self.ANTsMethod.textChanged.connect(self.GetParams)
    # registrationType
    self.registrationType = QComboBox()
    for ite in self.dtiregister_yml["protocol"]["registrationType"]["candidates"]:
      self.registrationType.addItem(ite["caption"])
      self.registrationType.setItemData(self.method.count()-1, ite["description"], QtCore.Qt.ToolTipRole)
    self.registrationType.currentTextChanged.connect(self.GetRegistrationTypeIt)
    self.registrationType.setStatusTip(self.dtiregister_yml["protocol"]["registrationType"]["description"])
    protocol_layout.addRow(self.dtiregister_yml["protocol"]["registrationType"]["caption"], self.registrationType)
    self.registrationType.currentTextChanged.connect(self.GetParams)
    # similarityMetric
    self.similarityMetric = QComboBox()
    for ite in self.dtiregister_yml["protocol"]["similarityMetric"]["candidates"]:
      self.similarityMetric.addItem(ite["caption"])
      self.similarityMetric.setItemData(self.method.count()-1, ite["description"], QtCore.Qt.ToolTipRole)
    self.similarityMetric.currentTextChanged.connect(self.GetSimilarityMetricIt)
    self.similarityMetric.setStatusTip(self.dtiregister_yml["protocol"]["similarityMetric"]["description"])
    protocol_layout.addRow(self.dtiregister_yml["protocol"]["similarityMetric"]["caption"], self.similarityMetric)
    self.similarityMetric.currentTextChanged.connect(self.GetParams)
    # similarityParameter
    self.similarityParameter = QDoubleSpinBox()
    self.similarityParameter.setAlignment(Qt.AlignRight)
    self.similarityParameter.setSingleStep(0.1)
    self.similarityParameter.setDecimals(3)
    self.similarityParameter.setStatusTip(self.dtiregister_yml["protocol"]["similarityParameter"]["description"])
    protocol_layout.addRow(self.dtiregister_yml["protocol"]["similarityParameter"]["caption"], self.similarityParameter) 
    self.similarityParameter.valueChanged.connect(self.GetParams)
    # ANTsIterations
    self.ANTsIterations = QLineEdit()
    self.ANTsIterations.setAlignment(Qt.AlignRight)
    self.ANTsIterations.setStatusTip(self.dtiregister_yml["protocol"]["ANTsIterations"]["description"])
    protocol_layout.addRow(self.dtiregister_yml["protocol"]["ANTsIterations"]["caption"], self.ANTsIterations)
    self.ANTsIterations.textChanged.connect(self.GetParams)
    # gaussianSigma
    self.gaussianSigma = QDoubleSpinBox()
    self.gaussianSigma.setAlignment(Qt.AlignRight)
    self.gaussianSigma.setSingleStep(0.1)
    self.gaussianSigma.setDecimals(3)
    self.gaussianSigma.setStatusTip(self.dtiregister_yml["protocol"]["gaussianSigma"]["description"])
    protocol_layout.addRow(self.dtiregister_yml["protocol"]["gaussianSigma"]["caption"], self.gaussianSigma) 
    self.gaussianSigma.valueChanged.connect(self.GetParams)
    
    ## Layout
    layout_v = QVBoxLayout()
    layout_v.addWidget(self.tab_name)
    layout_v.addWidget(description_label)
    layout_v.addWidget(options_groupbox)
    layout_v.addWidget(protocol_groupbox)
    layout_v.addStretch(1)
    self.stack.setLayout(layout_v)

  
  def GetMethodIt(self, text): # dti register parameter
    for it in range(len(self.dtiregister_yml["protocol"]["method"]["candidates"])):
      if self.dtiregister_yml["protocol"]["method"]["candidates"][it]["caption"] == text:
        self.method_it = it

  def GetRegistrationTypeIt(self, text): # dti register parameter
    for it in range(len(self.dtiregister_yml["protocol"]["registrationType"]["candidates"])):
      if self.dtiregister_yml["protocol"]["registrationType"]["candidates"][it]["caption"] == text:
        self.registrationType_it = it

  def GetSimilarityMetricIt(self, text): # dti register parameter
    for it in range(len(self.dtiregister_yml["protocol"]["similarityMetric"]["candidates"])):
      if self.dtiregister_yml["protocol"]["similarityMetric"]["candidates"][it]["caption"] == text:
        self.similarityMetric_it = it


  def GetParams(self):
    params = [
      'Register DTI (ANTs)',
      'DTI_Register', 
      {'options': {
        'overwrite': self.overwrite.isChecked(), 
        'skip': self.skip.isChecked(), 
        'write_image': self.writeimage.isChecked()
        }, 
      'protocol': {
        'method': self.dtiregister_yml["protocol"]["method"]["candidates"][self.method_it]["value"], 
        'referenceImage': self.referenceImage.text(), 
        'ANTsPath': '',
        'ANTsMethod': self.ANTsMethod.text(),
        'registrationType': self.dtiregister_yml["protocol"]["method"]["candidates"][self.registrationType_it]["value"],
        'similarityMetric': self.dtiregister_yml["protocol"]["method"]["candidates"][self.similarityMetric_it]["value"],
        'similarityParameter': round(self.similarityParameter.value(), 3), 
        'ANTsIterations': self.ANTsIterations.text(),
        'gaussianSigma': round(self.gaussianSigma.value(), 3)
        }
      }
    ]
    self.communicate.SendParams(params)