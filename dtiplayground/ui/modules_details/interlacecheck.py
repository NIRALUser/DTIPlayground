from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 

from dtiplayground.ui.modules_details_communicate import ModulesDetailsCommunicate

class InterlaceCheck(QWidget):
  communicate = ModulesDetailsCommunicate()

  def __init__(self, protocol_template, interlacecheck_yml):
    QWidget.__init__(self)
    self.stack = QWidget()
    self.InterlaceCheckStack(protocol_template, interlacecheck_yml)

  def InterlaceCheckStack(self, protocol_template, interlacecheck_yml):

    ## Module
    self.tab_name = QLabel()

    ## Description
    for template_ite in range(len(protocol_template["options"]["execution"]["pipeline"]["candidates"])):
      if protocol_template["options"]["execution"]["pipeline"]["candidates"][template_ite]["value"] == "INTERLACE_Check":
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
    # correlationThresholdBaseline
    self.correlationThresholdBaseline = QDoubleSpinBox()
    self.correlationThresholdBaseline.setAlignment(Qt.AlignRight)
    self.correlationThresholdBaseline.setSingleStep(0.01)
    self.correlationThresholdBaseline.setDecimals(3)
    self.correlationThresholdBaseline.setStatusTip(interlacecheck_yml["protocol"]["correlationThresholdBaseline"]["description"])
    protocol_layout.addRow(interlacecheck_yml["protocol"]["correlationThresholdBaseline"]["caption"], self.correlationThresholdBaseline) 
    self.correlationThresholdBaseline.valueChanged.connect(self.GetParams)
    # correlationThresholdGradient
    self.correlationThresholdGradient = QDoubleSpinBox()
    self.correlationThresholdGradient.setAlignment(Qt.AlignRight)
    self.correlationThresholdGradient.setSingleStep(0.001)
    self.correlationThresholdGradient.setDecimals(3)
    self.correlationThresholdGradient.setStatusTip(interlacecheck_yml["protocol"]["correlationThresholdGradient"]["description"])
    protocol_layout.addRow(interlacecheck_yml["protocol"]["correlationThresholdGradient"]["caption"], self.correlationThresholdGradient)   
    self.correlationThresholdGradient.valueChanged.connect(self.GetParams)
    # correlationDeviationBaseline
    self.correlationDeviationBaseline = QDoubleSpinBox()
    self.correlationDeviationBaseline.setAlignment(Qt.AlignRight)
    self.correlationDeviationBaseline.setSingleStep(0.1)
    self.correlationDeviationBaseline.setDecimals(3)
    self.correlationDeviationBaseline.setStatusTip(interlacecheck_yml["protocol"]["correlationDeviationBaseline"]["description"])
    protocol_layout.addRow(interlacecheck_yml["protocol"]["correlationDeviationBaseline"]["caption"], self.correlationDeviationBaseline)   
    self.correlationDeviationBaseline.valueChanged.connect(self.GetParams)
    # correlationDeviationGradient
    self.correlationDeviationGradient = QDoubleSpinBox()
    self.correlationDeviationGradient.setAlignment(Qt.AlignRight)
    self.correlationDeviationGradient.setSingleStep(0.1)
    self.correlationDeviationGradient.setDecimals(3)
    self.correlationDeviationGradient.setStatusTip(interlacecheck_yml["protocol"]["correlationDeviationGradient"]["description"])
    protocol_layout.addRow(interlacecheck_yml["protocol"]["correlationDeviationGradient"]["caption"], self.correlationDeviationGradient)         
    self.correlationDeviationGradient.valueChanged.connect(self.GetParams)
    # translationThreshold
    self.translationThreshold = QDoubleSpinBox()
    self.translationThreshold.setAlignment(Qt.AlignRight)
    self.translationThreshold.setSingleStep(0.1)
    self.translationThreshold.setDecimals(3)
    self.translationThreshold.setStatusTip(interlacecheck_yml["protocol"]["translationThreshold"]["description"])
    protocol_layout.addRow(interlacecheck_yml["protocol"]["translationThreshold"]["caption"], self.translationThreshold)    
    self.translationThreshold.valueChanged.connect(self.GetParams)
    # rotationThreshold
    self.rotationThreshold = QDoubleSpinBox()
    self.rotationThreshold.setAlignment(Qt.AlignRight)
    self.rotationThreshold.setSingleStep(0.1)
    self.rotationThreshold.setDecimals(3)
    self.rotationThreshold.setStatusTip(interlacecheck_yml["protocol"]["rotationThreshold"]["description"])
    protocol_layout.addRow(interlacecheck_yml["protocol"]["rotationThreshold"]["caption"], self.rotationThreshold)    
    self.rotationThreshold.valueChanged.connect(self.GetParams)

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
      'Interlace Correlation Check',
      'INTERLACE_Check', 
      {'options': {
        'overwrite': self.overwrite.isChecked(), 
        'skip': self.skip.isChecked(), 
        'write_image': self.writeimage.isChecked()
        }, 
      'protocol': {
        'correlationDeviationBaseline': self.correlationDeviationBaseline.value(), 
        'correlationDeviationGradient': self.correlationDeviationGradient.value(), 
        'correlationThresholdBaseline': self.correlationThresholdBaseline.value(), 
        'correlationThresholdGradient': self.correlationThresholdGradient.value(), 
        'rotationThreshold': self.rotationThreshold.value(), 
        'translationThreshold': self.translationThreshold.value()
        }
      }
    ]
    self.communicate.SendParams(params)