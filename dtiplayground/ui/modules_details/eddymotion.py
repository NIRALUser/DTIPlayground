from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 

from dtiplayground.ui.modules_details_communicate import ModulesDetailsCommunicate

class EddyMotion(QWidget):
  communicate = ModulesDetailsCommunicate()

  def __init__(self, protocol_template, eddymotion_yml):
    QWidget.__init__(self)
    self.stack = QWidget()
    self.EddyMotionStack(protocol_template, eddymotion_yml)

  def EddyMotionStack(self, protocol_template, eddymotion_yml):

    ## Module
    self.tab_name = QLabel()

    ## Description
    for template_ite in range(len(protocol_template["options"]["execution"]["pipeline"]["candidates"])):
      if protocol_template["options"]["execution"]["pipeline"]["candidates"][template_ite]["value"] == "EDDYMOTION_Correct":
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
    # estimateMoveBySusceptibility
    self.estimateMoveBySusceptibility_true = QRadioButton("True")
    self.estimateMoveBySusceptibility_false = QRadioButton("False")
    estimateMoveBySusceptibility_layout = QHBoxLayout()
    estimateMoveBySusceptibility_layout.addWidget(self.estimateMoveBySusceptibility_true)
    estimateMoveBySusceptibility_layout.addWidget(self.estimateMoveBySusceptibility_false)
    self.estimateMoveBySusceptibility_buttongroup = QButtonGroup()
    self.estimateMoveBySusceptibility_buttongroup.addButton(self.estimateMoveBySusceptibility_true)
    self.estimateMoveBySusceptibility_buttongroup.addButton(self.estimateMoveBySusceptibility_false)
    self.estimateMoveBySusceptibility_true.toggled.connect(self.GetParams)
    self.estimateMoveBySusceptibility_true.setStatusTip(eddymotion_yml["protocol"]["estimateMoveBySusceptibility"]["description"])
    self.estimateMoveBySusceptibility_false.setStatusTip(eddymotion_yml["protocol"]["estimateMoveBySusceptibility"]["description"])
    protocol_layout.addRow(eddymotion_yml["protocol"]["estimateMoveBySusceptibility"]["caption"], estimateMoveBySusceptibility_layout)
    self.estimateMoveBySusceptibility_true.setEnabled(False)
    self.estimateMoveBySusceptibility_false.setEnabled(False)
    # interpolateBadData
    self.interpolateBadData_true = QRadioButton("True")
    self.interpolateBadData_false = QRadioButton("False")
    interpolateBadData_layout = QHBoxLayout()
    interpolateBadData_layout.addWidget(self.interpolateBadData_true)
    interpolateBadData_layout.addWidget(self.interpolateBadData_false)
    self.interpolateBadData_buttongroup = QButtonGroup()
    self.interpolateBadData_buttongroup.addButton(self.interpolateBadData_true)
    self.interpolateBadData_buttongroup.addButton(self.interpolateBadData_false)
    self.interpolateBadData_true.toggled.connect(self.GetParams)
    self.interpolateBadData_true.setStatusTip(eddymotion_yml["protocol"]["interpolateBadData"]["description"])
    self.interpolateBadData_false.setStatusTip(eddymotion_yml["protocol"]["interpolateBadData"]["description"])
    protocol_layout.addRow(eddymotion_yml["protocol"]["interpolateBadData"]["caption"], interpolateBadData_layout)
    # dataIsShelled
    self.dataIsShelled_true = QRadioButton("True")
    self.dataIsShelled_false = QRadioButton("False")
    dataIsShelled_layout = QHBoxLayout()
    dataIsShelled_layout.addWidget(self.dataIsShelled_true)
    dataIsShelled_layout.addWidget(self.dataIsShelled_false)
    self.dataIsShelled_buttongroup = QButtonGroup()
    self.dataIsShelled_buttongroup.addButton(self.dataIsShelled_true)
    self.dataIsShelled_buttongroup.addButton(self.dataIsShelled_false)
    self.dataIsShelled_true.toggled.connect(self.GetParams)
    self.dataIsShelled_true.setStatusTip(eddymotion_yml["protocol"]["dataIsShelled"]["description"])
    self.dataIsShelled_false.setStatusTip(eddymotion_yml["protocol"]["dataIsShelled"]["description"])
    protocol_layout.addRow(eddymotion_yml["protocol"]["dataIsShelled"]["caption"], dataIsShelled_layout)
    # qcReport
    self.qcReport_true = QRadioButton("True")
    self.qcReport_false = QRadioButton("False")
    qcReport_layout = QHBoxLayout()
    qcReport_layout.addWidget(self.qcReport_true)
    qcReport_layout.addWidget(self.qcReport_false)
    self.qcReport_buttongroup = QButtonGroup()
    self.qcReport_buttongroup.addButton(self.qcReport_true)
    self.qcReport_buttongroup.addButton(self.qcReport_false)
    self.qcReport_true.toggled.connect(self.GetParams)
    self.qcReport_true.setStatusTip(eddymotion_yml["protocol"]["qcReport"]["description"])
    self.qcReport_false.setStatusTip(eddymotion_yml["protocol"]["qcReport"]["description"])
    protocol_layout.addRow(eddymotion_yml["protocol"]["qcReport"]["caption"], qcReport_layout)

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
      'Eddy motion Correction',
      'EDDYMOTION_Correct', 
      {'options': {
        'overwrite': self.overwrite.isChecked(), 
        'skip': self.skip.isChecked(), 
        'write_image': self.writeimage.isChecked()
        }, 
      'protocol': {
        'estimateMoveBySusceptibility': self.estimateMoveBySusceptibility_true.isChecked(),
        'interpolateBadData': self.interpolateBadData_true.isChecked(),
        'dataIsShelled': self.dataIsShelled_true.isChecked(),
        'qcReport': self.qcReport_true.isChecked()
        }
      }
    ]
    self.communicate.SendParams(params)