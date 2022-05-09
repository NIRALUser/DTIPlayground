from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 

from dtiplayground.ui.modules_details_communicate import ModulesDetailsCommunicate

class DTIEstimate(QWidget):
  communicate = ModulesDetailsCommunicate()

  def __init__(self, protocol_template, dtiestimate_yml):
    QWidget.__init__(self)
    self.dtiestimate_yml = dtiestimate_yml
    self.stack = QWidget()
    self.DTIEstimateStack(protocol_template)

  def DTIEstimateStack(self, protocol_template):

    ## Module
    self.tab_name = QLabel()

    ## Description
    for template_ite in range(len(protocol_template["options"]["execution"]["pipeline"]["candidates"])):
      if protocol_template["options"]["execution"]["pipeline"]["candidates"][template_ite]["value"] == "DTI_Estimate":
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
    for ite in self.dtiestimate_yml["protocol"]["method"]["candidates"]:
      self.method.addItem(ite["caption"])
      self.method.setItemData(self.method.count()-1, ite["description"], QtCore.Qt.ToolTipRole)
    self.method.currentTextChanged.connect(self.GetMethodIt)
    self.method.setStatusTip(self.dtiestimate_yml["protocol"]["method"]["description"])
    protocol_layout.addRow(self.dtiestimate_yml["protocol"]["method"]["caption"], self.method)
    self.method.currentTextChanged.connect(self.EnableDisableMethods)
    self.method.currentTextChanged.connect(self.GetParams)
    # optimizationMethod
    self.optimizationMethod = QComboBox()
    for ite in self.dtiestimate_yml["protocol"]["optimizationMethod"]["candidates"]:
      self.optimizationMethod.addItem(ite["caption"])
    self.optimizationMethod.currentTextChanged.connect(self.GetOptimizationMethodIt)
    #self.optimizationMethod.setStatusTip(self.dtiestimate_yml["protocol"]["optimizationMethod"]["description"])
    protocol_layout.addRow(self.dtiestimate_yml["protocol"]["optimizationMethod"]["caption"], self.optimizationMethod)
    self.optimizationMethod.currentTextChanged.connect(self.GetParams)
    # correctionMethod
    self.correctionMethod = QComboBox()
    for ite in self.dtiestimate_yml["protocol"]["correctionMethod"]["candidates"]:
      self.correctionMethod.addItem(ite["caption"])
      self.correctionMethod.setItemData(self.correctionMethod.count()-1, ite["description"], QtCore.Qt.ToolTipRole)
    self.correctionMethod.currentTextChanged.connect(self.GetCorrectionMethodIt)
    self.correctionMethod.setStatusTip(self.dtiestimate_yml["protocol"]["correctionMethod"]["description"])
    protocol_layout.addRow(self.dtiestimate_yml["protocol"]["correctionMethod"]["caption"], self.correctionMethod)
    self.correctionMethod.currentTextChanged.connect(self.GetParams)

    ## Layout
    layout_v = QVBoxLayout()
    layout_v.addWidget(self.tab_name)
    layout_v.addWidget(description_label)
    layout_v.addWidget(options_groupbox)
    layout_v.addWidget(protocol_groupbox)
    layout_v.addStretch(1)
    self.stack.setLayout(layout_v)

    self.EnableDisableMethods()

  def EnableDisableMethods(self): # enables and disables optimization methods and correction methods according to the selected method
    if self.method.currentText() == "DIPY":
      self.optimizationMethod.model().item(self.optimizationMethod.findText("RESTORE (DIPY Only)", Qt.MatchExactly)).setEnabled(True)
      self.optimizationMethod.model().item(self.optimizationMethod.findText("Maximum Likelihood (dtiestim Only)", Qt.MatchExactly)).setEnabled(False)
      self.correctionMethod.model().item(self.correctionMethod.findText("Nearest (dtiestim only)", Qt.MatchExactly)).setEnabled(False)
      self.correctionMethod.model().item(self.correctionMethod.findText("Absolute (dtiestim only)", Qt.MatchExactly)).setEnabled(False)
      self.correctionMethod.model().item(self.correctionMethod.findText("None (dtiestim only)", Qt.MatchExactly)).setEnabled(False)
      if self.correctionMethod.currentText() != "Zero":
        self.correctionMethod.setCurrentText("Zero")
      if self.optimizationMethod.currentText() == "Maximum Likelihood (dtiestim Only)":
        self.optimizationMethod.setCurrentText("Weighted Least Squares")
    if self.method.currentText() == "dtiestim":
      self.optimizationMethod.model().item(self.optimizationMethod.findText("RESTORE (DIPY Only)", Qt.MatchExactly)).setEnabled(False)
      self.optimizationMethod.model().item(self.optimizationMethod.findText("Maximum Likelihood (dtiestim Only)", Qt.MatchExactly)).setEnabled(True)
      self.correctionMethod.model().item(self.correctionMethod.findText("Nearest (dtiestim only)", Qt.MatchExactly)).setEnabled(True)
      self.correctionMethod.model().item(self.correctionMethod.findText("Absolute (dtiestim only)", Qt.MatchExactly)).setEnabled(True)
      self.correctionMethod.model().item(self.correctionMethod.findText("None (dtiestim only)", Qt.MatchExactly)).setEnabled(True)
      if self.optimizationMethod.currentText() == "RESTORE (DIPY Only)":
        self.optimizationMethod.setCurrentText("Weighted Least Squares")

  def GetMethodIt(self, text): # dti estimate parameter
    self.method_it = 0
    for it in range(len(self.dtiestimate_yml["protocol"]["method"]["candidates"])):
      if self.dtiestimate_yml["protocol"]["method"]["candidates"][it]["caption"] == text:
        self.method_it = it

  def GetOptimizationMethodIt(self, text): # dti estimate parameter
    self.optimizationmethod_it = 0
    for it in range(len(self.dtiestimate_yml["protocol"]["optimizationMethod"]["candidates"])):
      if self.dtiestimate_yml["protocol"]["optimizationMethod"]["candidates"][it]["caption"] == text:
        self.optimizationmethod_it = it

  def GetCorrectionMethodIt(self, text): # dti estimate parameter
    self.correctionmethod_it = 0
    for it in range(len(self.dtiestimate_yml["protocol"]["correctionMethod"]["candidates"])):
      if self.dtiestimate_yml["protocol"]["correctionMethod"]["candidates"][it]["caption"] == text:
        self.correctionmethod_it = it

  def GetParams(self):
    params = [
      'Estimate DTI',
      'DTI_Estimate', 
      {'options': {
        'overwrite': self.overwrite.isChecked(), 
        'skip': self.skip.isChecked(), 
        'write_image': self.writeimage.isChecked()
        }, 
      'protocol': {
        'correctionMethod': self.dtiestimate_yml["protocol"]["correctionMethod"]["candidates"][self.correctionmethod_it]["value"], 
        'method': self.dtiestimate_yml["protocol"]["method"]["candidates"][self.method_it]["value"],
        'optimizationMethod': self.dtiestimate_yml["protocol"]["optimizationMethod"]["candidates"][self.optimizationmethod_it]["value"],        
        }
      }
    ]
    self.communicate.SendParams(params)