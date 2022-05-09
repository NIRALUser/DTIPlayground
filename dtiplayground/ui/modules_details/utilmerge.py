from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 

from dtiplayground.ui.modules_details_communicate import ModulesDetailsCommunicate

class UtilMerge(QWidget):
  communicate = ModulesDetailsCommunicate()

  def __init__(self, protocol_template, utilmerge_yml):
    QWidget.__init__(self)
    self.stack = QWidget()
    self.UtilMergeStack(protocol_template, utilmerge_yml)

  def UtilMergeStack(self, protocol_template, utilmerge_yml):

    ## Module
    self.tab_name = QLabel()

    ## Description
    for template_ite in range(len(protocol_template["options"]["execution"]["pipeline"]["candidates"])):
      if protocol_template["options"]["execution"]["pipeline"]["candidates"][template_ite]["value"] == "UTIL_Merge":
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
    self.testparam = QLineEdit()
    self.testparam.setAlignment(Qt.AlignRight)
    self.testparam.setStatusTip(utilmerge_yml["protocol"]["TestParam"]["description"])
    protocol_layout.addRow(utilmerge_yml["protocol"]["TestParam"]["caption"], self.testparam)
    self.testparam.textChanged.connect(self.GetParams)

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
      'Merge Images',
      'UTIL_Merge', 
      {'options': {
        'overwrite': self.overwrite.isChecked(), 
        'skip': self.skip.isChecked(), 
        'write_image': self.writeimage.isChecked()
        },
      'protocol': {
        'TestParam': self.testparam.text(), 
        }
      }
    ]
    self.communicate.SendParams(params)