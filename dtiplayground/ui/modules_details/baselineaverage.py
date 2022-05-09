from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 

from dtiplayground.ui.modules_details_communicate import ModulesDetailsCommunicate

class BaselineAverage(QWidget):
  
  communicate = ModulesDetailsCommunicate()

  def __init__(self, protocol_template, baselineaverage_yml):
    QWidget.__init__(self)
    self.baselineaverage_yml = baselineaverage_yml
    self.stack = QWidget()
    self.avgmethod_it = 0
    self.avginterpolmethod_it = 0

    self.BaselineAverageStack(protocol_template)

  def BaselineAverageStack(self, protocol_template):

    ## Module
    self.tab_name = QLabel()

    ## Description
    for template_ite in range(len(protocol_template["options"]["execution"]["pipeline"]["candidates"])):
      if protocol_template["options"]["execution"]["pipeline"]["candidates"][template_ite]["value"] == "BASELINE_Average":
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
    # averageMethod
    self.averageMethod = QComboBox()
    for ite in self.baselineaverage_yml["protocol"]["averageMethod"]["candidates"]:
      self.averageMethod.addItem(ite["caption"])
      self.averageMethod.setItemData(self.averageMethod.count()-1, ite["description"], QtCore.Qt.ToolTipRole)
    self.averageMethod.currentTextChanged.connect(self.GetAvgMethodIt)
    self.averageMethod.setStatusTip(self.baselineaverage_yml["protocol"]["averageMethod"]["description"])
    protocol_layout.addRow(self.baselineaverage_yml["protocol"]["averageMethod"]["caption"], self.averageMethod)
    self.averageMethod.currentTextChanged.connect(self.GetParams)
    # averageInterpolationMethod
    self.averageInterpolationMethod = QComboBox()
    for ite in self.baselineaverage_yml["protocol"]["averageInterpolationMethod"]["candidates"]:
      self.averageInterpolationMethod.addItem(ite["caption"])
      self.averageInterpolationMethod.setItemData(self.averageInterpolationMethod.count()-1, ite["description"], QtCore.Qt.ToolTipRole)
    self.averageInterpolationMethod.currentTextChanged.connect(self.GetAvgInterpolMethodIt)
    self.averageInterpolationMethod.setStatusTip(self.baselineaverage_yml["protocol"]["averageInterpolationMethod"]["description"])
    protocol_layout.addRow(self.baselineaverage_yml["protocol"]["averageInterpolationMethod"]["caption"], self.averageInterpolationMethod)
    self.averageInterpolationMethod.currentTextChanged.connect(self.GetParams)
    # stopThreshold
    self.stopThreshold = QDoubleSpinBox()
    self.stopThreshold.setAlignment(Qt.AlignRight)
    self.stopThreshold.setSingleStep(0.01)
    self.stopThreshold.setDecimals(3)
    self.stopThreshold.setStatusTip(self.baselineaverage_yml["protocol"]["stopThreshold"]["description"])
    protocol_layout.addRow(self.baselineaverage_yml["protocol"]["stopThreshold"]["caption"], self.stopThreshold) 
    self.stopThreshold.valueChanged.connect(self.GetParams)
    # maxIterations
    self.maxIterations = QSpinBox()
    self.maxIterations.setAlignment(Qt.AlignRight)
    self.maxIterations.setStatusTip(self.baselineaverage_yml["protocol"]["maxIterations"]["description"])
    protocol_layout.addRow(self.baselineaverage_yml["protocol"]["maxIterations"]["caption"], self.maxIterations)
    self.maxIterations.valueChanged.connect(self.GetParams)
    # outputDWIFileNameSuffix
    self.outputDWIFileNameSuffix = QLineEdit()
    self.outputDWIFileNameSuffix.setAlignment(Qt.AlignRight)
    self.outputDWIFileNameSuffix.setStatusTip(self.baselineaverage_yml["protocol"]["outputDWIFileNameSuffix"]["description"])
    protocol_layout.addRow(self.baselineaverage_yml["protocol"]["outputDWIFileNameSuffix"]["caption"], self.outputDWIFileNameSuffix)
    self.outputDWIFileNameSuffix.textChanged.connect(self.GetParams)

    ## Layout
    layout_v = QVBoxLayout()
    layout_v.addWidget(self.tab_name)
    layout_v.addWidget(description_label)
    layout_v.addWidget(options_groupbox)
    layout_v.addWidget(protocol_groupbox)
    layout_v.addStretch(1)
    self.stack.setLayout(layout_v)

  def GetAvgInterpolMethodIt(self, text): # baseline average parameter 
    for it in range(len(self.baselineaverage_yml["protocol"]["averageInterpolationMethod"]["candidates"])):
      if self.baselineaverage_yml["protocol"]["averageInterpolationMethod"]["candidates"][it]["caption"] == text:
        self.avginterpolmethod_it = it

  def GetAvgMethodIt(self, text): # baseline average parameter
    for it in range(len(self.baselineaverage_yml["protocol"]["averageMethod"]["candidates"])):
      if self.baselineaverage_yml["protocol"]["averageMethod"]["candidates"][it]["caption"] == text:
        self.avgmethod_it = it
  
  def GetParams(self):
    params = [
      'Baseline Average',
      'BASELINE_Average', 
      {'options': {
        'overwrite': self.overwrite.isChecked(), 
        'skip': self.skip.isChecked(), 
        'write_image': self.writeimage.isChecked()
        },
      'protocol': {
        'averageInterpolationMethod': self.baselineaverage_yml["protocol"]["averageInterpolationMethod"]["candidates"][self.avginterpolmethod_it]["value"], 
        'averageMethod': self.baselineaverage_yml["protocol"]["averageMethod"]["candidates"][self.avgmethod_it]["value"], 
        'maxIterations': self.maxIterations.value(), 
        'outputDWIFileNameSuffix': self.outputDWIFileNameSuffix.text(), 
        'stopThreshold': self.stopThreshold.value()
        }
      }
    ]
    self.communicate.SendParams(params)