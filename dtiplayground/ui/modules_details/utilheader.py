from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 

from dtiplayground.ui.modules_details_communicate import ModulesDetailsCommunicate

class UtilHeader(QWidget):
  communicate = ModulesDetailsCommunicate()

  def __init__(self, protocol_template, utilheader_yml):
    QWidget.__init__(self)
    self.stack = QWidget()
    self.UtilHeaderStack(protocol_template, utilheader_yml)

  def UtilHeaderStack(self, protocol_template, utilheader_yml):

    ## Module
    self.tab_name = QLabel()

    ## Description
    for template_ite in range(len(protocol_template["options"]["execution"]["pipeline"]["candidates"])):
      if protocol_template["options"]["execution"]["pipeline"]["candidates"][template_ite]["value"] == "UTIL_Header":
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
    # options
    self.options = QLineEdit()
    self.options.setAlignment(Qt.AlignRight)
    self.options.setStatusTip(utilheader_yml["protocol"]["options"]["description"])
    protocol_layout.addRow(utilheader_yml["protocol"]["options"]["caption"], self.options)
    self.options.textChanged.connect(self.GetParams)

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
      'View Header',
      'UTIL_Header', 
      {'options': {
        'overwrite': self.overwrite.isChecked(), 
        'skip': self.skip.isChecked(), 
        'write_image': self.writeimage.isChecked()
        },
      'protocol': {
        'options': self.options.text(), 
        }
      }
    ]
    self.communicate.SendParams(params)