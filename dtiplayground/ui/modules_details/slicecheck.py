from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 

from dtiplayground.ui.modules_details_communicate import ModulesDetailsCommunicate

class SliceCheck(QWidget):
  communicate = ModulesDetailsCommunicate()

  def __init__(self, protocol_template, slicecheck_yml):
    QWidget.__init__(self)
    self.stack = QWidget()
    self.SliceCheckStack(protocol_template, slicecheck_yml)

  def SliceCheckStack(self, protocol_template, slicecheck_yml):

    ## Module
    self.tab_name = QLabel()

    ## Description
    for template_ite in range(len(protocol_template["options"]["execution"]["pipeline"]["candidates"])):
      if protocol_template["options"]["execution"]["pipeline"]["candidates"][template_ite]["value"] == "SLICE_Check":
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
    # bSubregionalCheck
    self.bSubregionalCheck_true = QRadioButton("True")
    self.bSubregionalCheck_false = QRadioButton("False")
    bSubregionalCheck_layout = QHBoxLayout()
    bSubregionalCheck_layout.addWidget(self.bSubregionalCheck_true)
    bSubregionalCheck_layout.addWidget(self.bSubregionalCheck_false)
    self.bSubregionalCheck_buttongroup = QButtonGroup()
    self.bSubregionalCheck_buttongroup.addButton(self.bSubregionalCheck_true)
    self.bSubregionalCheck_buttongroup.addButton(self.bSubregionalCheck_false)
    self.bSubregionalCheck_true.toggled.connect(self.GetParams)
    self.bSubregionalCheck_true.setStatusTip(slicecheck_yml["protocol"]["bSubregionalCheck"]["description"])
    self.bSubregionalCheck_false.setStatusTip(slicecheck_yml["protocol"]["bSubregionalCheck"]["description"])
    protocol_layout.addRow(slicecheck_yml["protocol"]["bSubregionalCheck"]["caption"], bSubregionalCheck_layout)
    # subregionalCheckRelaxationFactor:
    self.subregionalCheckRelaxationFactor = QDoubleSpinBox()
    self.subregionalCheckRelaxationFactor.setAlignment(Qt.AlignRight)
    self.subregionalCheckRelaxationFactor.setSingleStep(0.1)
    self.subregionalCheckRelaxationFactor.setDecimals(3)
    self.subregionalCheckRelaxationFactor.setStatusTip(slicecheck_yml["protocol"]["subregionalCheckRelaxationFactor"]["description"])
    protocol_layout.addRow(slicecheck_yml["protocol"]["subregionalCheckRelaxationFactor"]["caption"], self.subregionalCheckRelaxationFactor)    
    self.subregionalCheckRelaxationFactor.valueChanged.connect(self.GetParams)
    # chekTimes
    self.checkTimes = QSpinBox()
    self.checkTimes.setAlignment(Qt.AlignRight)
    self.checkTimes.setStatusTip(slicecheck_yml["protocol"]["checkTimes"]["description"])
    protocol_layout.addRow(slicecheck_yml["protocol"]["checkTimes"]["caption"], self.checkTimes)
    self.checkTimes.valueChanged.connect(self.GetParams)
    # headSkipSlicePercentage
    self.headSkipSlicePercentage = QDoubleSpinBox()
    self.headSkipSlicePercentage.setAlignment(Qt.AlignRight)
    self.headSkipSlicePercentage.setSingleStep(0.1)
    self.headSkipSlicePercentage.setDecimals(3)
    self.headSkipSlicePercentage.setStatusTip(slicecheck_yml["protocol"]["headSkipSlicePercentage"]["description"])
    protocol_layout.addRow(slicecheck_yml["protocol"]["headSkipSlicePercentage"]["caption"], self.headSkipSlicePercentage)   
    self.headSkipSlicePercentage.valueChanged.connect(self.GetParams)
    # tailSkipSlicePercentage
    self.tailSkipSlicePercentage = QDoubleSpinBox()
    self.tailSkipSlicePercentage.setAlignment(Qt.AlignRight)
    self.tailSkipSlicePercentage.setSingleStep(0.1)
    self.tailSkipSlicePercentage.setDecimals(3)
    self.tailSkipSlicePercentage.setStatusTip(slicecheck_yml["protocol"]["tailSkipSlicePercentage"]["description"])
    protocol_layout.addRow(slicecheck_yml["protocol"]["tailSkipSlicePercentage"]["caption"], self.tailSkipSlicePercentage)    
    self.tailSkipSlicePercentage.valueChanged.connect(self.GetParams)
    # correlationDeviationThresholdbaseline
    self.correlationDeviationThresholdbaseline = QDoubleSpinBox()
    self.correlationDeviationThresholdbaseline.setAlignment(Qt.AlignRight)
    self.correlationDeviationThresholdbaseline.setSingleStep(0.1)
    self.correlationDeviationThresholdbaseline.setDecimals(3)
    self.correlationDeviationThresholdbaseline.setStatusTip(slicecheck_yml["protocol"]["correlationDeviationThresholdbaseline"]["description"])
    protocol_layout.addRow(slicecheck_yml["protocol"]["correlationDeviationThresholdbaseline"]["caption"], self.correlationDeviationThresholdbaseline)
    self.correlationDeviationThresholdbaseline.valueChanged.connect(self.GetParams)
    # correlationDeviationThresholdgradient
    self.correlationDeviationThresholdgradient = QDoubleSpinBox()
    self.correlationDeviationThresholdgradient.setAlignment(Qt.AlignRight)
    self.correlationDeviationThresholdgradient.setSingleStep(0.1)
    self.correlationDeviationThresholdgradient.setDecimals(3)
    self.correlationDeviationThresholdgradient.setStatusTip(slicecheck_yml["protocol"]["correlationDeviationThresholdgradient"]["description"])
    protocol_layout.addRow(slicecheck_yml["protocol"]["correlationDeviationThresholdgradient"]["caption"], self.correlationDeviationThresholdgradient)
    self.correlationDeviationThresholdgradient.valueChanged.connect(self.GetParams)
    # quadFit
    self.quadFit_true = QRadioButton("True")
    self.quadFit_false = QRadioButton("False")
    quadFit_layout = QHBoxLayout()
    quadFit_layout.addWidget(self.quadFit_true)
    quadFit_layout.addWidget(self.quadFit_false)
    self.quadFit_buttongroup = QButtonGroup()
    self.quadFit_buttongroup.addButton(self.quadFit_true)
    self.quadFit_buttongroup.addButton(self.quadFit_false)
    self.quadFit_true.toggled.connect(self.GetParams)
    self.quadFit_true.setStatusTip(slicecheck_yml["protocol"]["quadFit"]["description"])
    self.quadFit_false.setStatusTip(slicecheck_yml["protocol"]["quadFit"]["description"])
    protocol_layout.addRow(slicecheck_yml["protocol"]["quadFit"]["caption"], quadFit_layout)    
    
    ## Layout
    layout_v = QVBoxLayout()
    layout_v.addWidget(self.tab_name)
    layout_v.addWidget(description_label)
    layout_v.addWidget(options_groupbox)
    layout_v.addWidget(protocol_groupbox)
    layout_v.addStretch(1)
    self.stack.setLayout(layout_v)


  def GetParams(self):
    params = [
      'Slicewise Check',
      'SLICE_Check', 
      {'options': {
        'overwrite': self.overwrite.isChecked(), 
        'skip': self.skip.isChecked(), 
        'write_image': self.writeimage.isChecked()
        }, 
      'protocol': {
        'bSubregionalCheck': self.bSubregionalCheck_true.isChecked(), 
        'checkTimes': self.checkTimes.value(), 
        'correlationDeviationThresholdbaseline': self.correlationDeviationThresholdbaseline.value(), 
        'correlationDeviationThresholdgradient': self.correlationDeviationThresholdgradient.value(), 
        'headSkipSlicePercentage': self.headSkipSlicePercentage.value(), 
        'quadFit': self.quadFit_true.isChecked(), 
        'subregionalCheckRelaxationFactor': self.subregionalCheckRelaxationFactor.value(), 
        'tailSkipSlicePercentage': self.tailSkipSlicePercentage.value()
        }
      }
    ]
    self.communicate.SendParams(params)