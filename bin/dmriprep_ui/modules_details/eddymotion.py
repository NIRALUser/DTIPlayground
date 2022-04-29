from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 

from dmriprep_ui.modules_details_communicate import ModulesDetailsCommunicate

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
    # susceptibilityCorrection
    self.susceptibilityCorrection_true = QRadioButton("True")
    self.susceptibilityCorrection_false = QRadioButton("False")
    susceptibilityCorrection_layout = QHBoxLayout()
    susceptibilityCorrection_layout.addWidget(self.susceptibilityCorrection_true)
    susceptibilityCorrection_layout.addWidget(self.susceptibilityCorrection_false)
    susceptibilityCorrection_buttongroup = QButtonGroup()
    susceptibilityCorrection_buttongroup.addButton(self.susceptibilityCorrection_true)
    susceptibilityCorrection_buttongroup.addButton(self.susceptibilityCorrection_false)
    self.susceptibilityCorrection_true.toggled.connect(self.GetParams)
    self.susceptibilityCorrection_true.setStatusTip(eddymotion_yml["protocol"]["susceptibilityCorrection"]["description"])
    self.susceptibilityCorrection_false.setStatusTip(eddymotion_yml["protocol"]["susceptibilityCorrection"]["description"])
    protocol_layout.addRow(eddymotion_yml["protocol"]["susceptibilityCorrection"]["caption"], susceptibilityCorrection_layout)
    
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
        'susceptibilityCorrection': self.susceptibilityCorrection_true.isChecked()
        }
      }
    ]
    self.communicate.SendParams(params)