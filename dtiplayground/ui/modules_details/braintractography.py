from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 

from dtiplayground.ui.modules_details_communicate import ModulesDetailsCommunicate

class BrainTractography(QWidget):
  communicate = ModulesDetailsCommunicate()

  def __init__(self, protocol_template, braintractography_yml):
    QWidget.__init__(self)
    self.braintractography_yml = braintractography_yml
    self.whiteMatterMaskThreshold_it = 0
    self.method_it = 0
    self.stack = QWidget()
    self.BrainTractographyStack(protocol_template)

  def BrainTractographyStack(self, protocol_template):

    ## Module
    self.tab_name = QLabel()
    
    ## Description
    for template_ite in range(len(protocol_template["options"]["execution"]["pipeline"]["candidates"])):
      if protocol_template["options"]["execution"]["pipeline"]["candidates"][template_ite]["value"] == "BRAIN_Tractography":
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
    protocol_sublayout = QFormLayout()
    protocol_layout = QVBoxLayout()
    protocol_layout.addLayout(protocol_sublayout)
    protocol_groupbox.setLayout(protocol_layout)
    # whiteMatterMaskThreshold
    self.whiteMatterMaskThreshold = QComboBox()
    for ite in self.braintractography_yml["protocol"]["whiteMatterMaskThreshold"]["candidates"]:
      self.whiteMatterMaskThreshold.addItem(ite["caption"])
      self.whiteMatterMaskThreshold.setItemData(self.whiteMatterMaskThreshold.count()-1, ite["description"], QtCore.Qt.ToolTipRole)
    self.whiteMatterMaskThreshold.currentTextChanged.connect(self.GetWhiteMatterMaskThresholdIt)
    self.whiteMatterMaskThreshold.setStatusTip(self.braintractography_yml["protocol"]["whiteMatterMaskThreshold"]["description"])
    protocol_sublayout.addRow(self.braintractography_yml["protocol"]["whiteMatterMaskThreshold"]["caption"], self.whiteMatterMaskThreshold)
    self.whiteMatterMaskThreshold.currentTextChanged.connect(self.GetParams)
    self.whiteMatterMaskThreshold.currentTextChanged.connect(self.DisplayWhiteMatterMaskThresholds)
    # thresholdLow
    self.thresholdLow = QDoubleSpinBox()
    self.thresholdLow.setAlignment(Qt.AlignRight)
    self.thresholdLow.setSingleStep(0.1)
    self.thresholdLow.setDecimals(3)
    self.thresholdLow.setStatusTip(self.braintractography_yml["protocol"]["thresholdLow"]["description"])
    self.thresholdLow_label = QLabel(self.braintractography_yml["protocol"]["thresholdLow"]["caption"])
    protocol_sublayout.addRow(self.thresholdLow_label, self.thresholdLow)
    self.thresholdLow.valueChanged.connect(self.GetParams)
    # thresholdUp
    self.thresholdUp = QDoubleSpinBox()
    self.thresholdUp.setAlignment(Qt.AlignRight)
    self.thresholdUp.setSingleStep(0.1)
    self.thresholdUp.setDecimals(3)
    self.thresholdUp.setStatusTip(self.braintractography_yml["protocol"]["thresholdUp"]["description"])
    self.thresholdUp_label = QLabel(self.braintractography_yml["protocol"]["thresholdUp"]["caption"])
    protocol_sublayout.addRow(self.thresholdUp_label, self.thresholdUp)
    self.thresholdUp.valueChanged.connect(self.GetParams)
    # method
    self.method = QComboBox()
    for ite in self.braintractography_yml["protocol"]["method"]["candidates"]:
      self.method.addItem(ite["caption"])
      self.method.setItemData(self.method.count()-1, ite["description"], QtCore.Qt.ToolTipRole)
    self.method.currentTextChanged.connect(self.GetMethodIt)
    self.method.setStatusTip(self.braintractography_yml["protocol"]["method"]["description"])
    protocol_sublayout.addRow(self.braintractography_yml["protocol"]["method"]["caption"], self.method)
    self.method.currentTextChanged.connect(self.GetParams)
    # shOrder
    self.shOrder = QSpinBox()
    self.shOrder.setAlignment(Qt.AlignRight)
    self.shOrder.setSingleStep(2)
    self.shOrder.setStatusTip(self.braintractography_yml["protocol"]["shOrder"]["description"])
    self.shOrder_label = QLabel(self.braintractography_yml["protocol"]["shOrder"]["caption"])
    protocol_sublayout.addRow(self.shOrder_label, self.shOrder)
    self.shOrder.valueChanged.connect(self.GetParams)
    # relativePeakThreshold
    self.relativePeakThreshold = QDoubleSpinBox()
    self.relativePeakThreshold.setAlignment(Qt.AlignRight)
    self.relativePeakThreshold.setSingleStep(0.1)
    self.relativePeakThreshold.setDecimals(3)
    self.relativePeakThreshold.setStatusTip(self.braintractography_yml["protocol"]["relativePeakThreshold"]["description"])
    protocol_sublayout.addRow(self.braintractography_yml["protocol"]["relativePeakThreshold"]["caption"], self.relativePeakThreshold)
    self.relativePeakThreshold.valueChanged.connect(self.GetParams)
    # minPeakSeparationAngle
    self.minPeakSeparationAngle = QDoubleSpinBox()
    self.minPeakSeparationAngle.setAlignment(Qt.AlignRight)
    self.minPeakSeparationAngle.setSingleStep(1)
    self.minPeakSeparationAngle.setDecimals(3)
    self.minPeakSeparationAngle.setMaximum(90)
    self.minPeakSeparationAngle.setStatusTip(self.braintractography_yml["protocol"]["minPeakSeparationAngle"]["description"])
    protocol_sublayout.addRow(self.braintractography_yml["protocol"]["minPeakSeparationAngle"]["caption"], self.minPeakSeparationAngle)
    self.minPeakSeparationAngle.valueChanged.connect(self.GetParams)
    # stoppingCriterionThreshold
    self.stoppingCriterionThreshold = QDoubleSpinBox()
    self.stoppingCriterionThreshold.setAlignment(Qt.AlignRight)
    self.stoppingCriterionThreshold.setSingleStep(0.1)
    self.stoppingCriterionThreshold.setDecimals(3)
    self.stoppingCriterionThreshold.setStatusTip(self.braintractography_yml["protocol"]["stoppingCriterionThreshold"]["description"])
    protocol_sublayout.addRow(self.braintractography_yml["protocol"]["stoppingCriterionThreshold"]["caption"], self.stoppingCriterionThreshold)
    self.stoppingCriterionThreshold.valueChanged.connect(self.GetParams)
    # vtk42
    self.vtk42_true = QRadioButton("True")
    self.vtk42_false = QRadioButton("False")
    vtk42_layout = QHBoxLayout()
    vtk42_layout.addWidget(self.vtk42_true)
    vtk42_layout.addWidget(self.vtk42_false)
    self.vtk42_buttongroup = QButtonGroup()
    self.vtk42_buttongroup.addButton(self.vtk42_true)
    self.vtk42_buttongroup.addButton(self.vtk42_false)
    self.vtk42_true.toggled.connect(self.GetParams)
    self.vtk42_true.setStatusTip(self.braintractography_yml["protocol"]["vtk42"]["description"])
    self.vtk42_false.setStatusTip(self.braintractography_yml["protocol"]["vtk42"]["description"])
    protocol_sublayout.addRow(self.braintractography_yml["protocol"]["vtk42"]["caption"], vtk42_layout)
    # removeShortTracts
    self.removeShortTracts = QCheckBox(self.braintractography_yml["protocol"]["removeShortTracts"]["caption"])
    self.removeShortTracts.stateChanged.connect(self.GetParams)
    self.removeShortTracts.stateChanged.connect(self.EnableShortTractsThreshold)
    self.shortTractsThreshold = QDoubleSpinBox()
    self.shortTractsThreshold.valueChanged.connect(self.GetParams)
    self.shortTractsThreshold.setEnabled(False)
    self.shortTractsThreshold.setMaximum(500)
    shortTracts_layout = QHBoxLayout()
    shortTracts_layout.addWidget(self.removeShortTracts)
    shortTracts_layout.addWidget(QLabel("Threshold:"))
    shortTracts_layout.addWidget(self.shortTractsThreshold)
    protocol_layout.addLayout(shortTracts_layout)
    # removeLongTracts
    self.removeLongTracts = QCheckBox(self.braintractography_yml["protocol"]["removeLongTracts"]["caption"])
    self.removeLongTracts.stateChanged.connect(self.GetParams)
    self.removeLongTracts.stateChanged.connect(self.EnableLongTractsThreshold)
    self.longTractsThreshold = QDoubleSpinBox()
    self.longTractsThreshold.valueChanged.connect(self.GetParams)
    self.longTractsThreshold.setEnabled(False)
    self.longTractsThreshold.setMaximum(500)
    longTracts_layout = QHBoxLayout()
    longTracts_layout.addWidget(self.removeLongTracts)
    longTracts_layout.addWidget(QLabel("Threshold:"))
    longTracts_layout.addWidget(self.longTractsThreshold)
    protocol_layout.addLayout(longTracts_layout)

    ## Layout
    layout_v = QVBoxLayout()
    layout_v.addWidget(self.tab_name)
    layout_v.addWidget(description_label)
    layout_v.addWidget(options_groupbox)
    layout_v.addWidget(protocol_groupbox)
    layout_v.addStretch(1)
    self.stack.setLayout(layout_v)

  def GetWhiteMatterMaskThresholdIt(self, text): # get "whiteMatterMaskThreshold" parameter
    self.whiteMatterMaskThreshold_it = 0
    for it in range(len(self.braintractography_yml["protocol"]["whiteMatterMaskThreshold"]["candidates"])):
      if self.braintractography_yml["protocol"]["whiteMatterMaskThreshold"]["candidates"][it]["caption"] == text:
        self.whiteMatterMaskThreshold_it = it

  def GetMethodIt(self, text): # get "method" parameter
    for it in range(len(self.braintractography_yml["protocol"]["method"]["candidates"])):
      if self.braintractography_yml["protocol"]["method"]["candidates"][it]["caption"] == text:
        self.method_it = it

  def DisplayWhiteMatterMaskThresholds(self):
    if self.whiteMatterMaskThreshold.currentText() != "Manual Threshold":
      self.thresholdLow_label.setHidden(True)
      self.thresholdLow.setHidden(True)
      self.thresholdUp_label.setHidden(True)
      self.thresholdUp.setHidden(True)
    else:
      self.thresholdLow_label.setHidden(False)
      self.thresholdLow.setHidden(False)
      self.thresholdUp_label.setHidden(False)
      self.thresholdUp.setHidden(False)

  def DisplayShOrder(self):
    if self.method.currentText() not in ["CSA model", "OPDT model"]:
      self.shOrder.setHidden(True)
      self.shOrder_label.setHidden(True)
    else:
      self.shOrder.setHidden(False)
      self.shOrder_label.setHidden(False)

  def EnableShortTractsThreshold(self):
    if self.removeShortTracts.isChecked():
      self.shortTractsThreshold.setEnabled(True)
    else:
      self.shortTractsThreshold.setEnabled(False)

  def EnableLongTractsThreshold(self):
    if self.removeLongTracts.isChecked():
      self.longTractsThreshold.setEnabled(True)
    else:
      self.longTractsThreshold.setEnabled(False)

  def GetParams(self):
    params = [
      'Brain Tractography',
      'BRAIN_Tractography', 
      {'options': {
        'overwrite': self.overwrite.isChecked(), 
        'skip': self.skip.isChecked(), 
        }, 
      'protocol': {
        'whiteMatterMaskThreshold': self.braintractography_yml["protocol"]["whiteMatterMaskThreshold"]["candidates"][self.whiteMatterMaskThreshold_it]["value"],
        'thresholdLow': self.thresholdLow.value(),
        'thresholdUp': self.thresholdUp.value(),
        'method': self.braintractography_yml["protocol"]["method"]["candidates"][self.method_it]["value"],
        'shOrder': self.shOrder.value(),
        'relativePeakThreshold': self.relativePeakThreshold.value(),
        'minPeakSeparationAngle': self.minPeakSeparationAngle.value(),
        'stoppingCriterionThreshold': self.stoppingCriterionThreshold.value(),
        'vtk42': self.vtk42_true.isChecked(),
        'removeShortTracts': self.removeShortTracts.isChecked(),
        'shortTractsThreshold': self.shortTractsThreshold.value(),
        'removeLongTracts': self.removeLongTracts.isChecked(),
        'longTractsThreshold': self.longTractsThreshold.value()
        }
      }
    ]
    self.communicate.SendParams(params)