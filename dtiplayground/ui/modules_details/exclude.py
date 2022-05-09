from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 
import re

from dtiplayground.ui.modules_details_communicate import ModulesDetailsCommunicate

class ExcludeGradients(QWidget):
  communicate = ModulesDetailsCommunicate()

  def __init__(self, protocol_template, exclude_yml):
    QWidget.__init__(self)
    self.stack = QWidget()

    self.gradientsToExclude_list = []

    self.ExcludeGradientsStack(protocol_template, exclude_yml)

  def ExcludeGradientsStack(self, protocol_template, exclude_yml):

    ## Module
    self.tab_name = QLabel()

    ## Description
    for template_ite in range(len(protocol_template["options"]["execution"]["pipeline"]["candidates"])):
      if protocol_template["options"]["execution"]["pipeline"]["candidates"][template_ite]["value"] == "MANUAL_Exclude":
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
    protocol_layout = QVBoxLayout()
    protocol_groupbox.setLayout(protocol_layout)
    # selectionMethod
    self.selectionMethod = QComboBox()
    self.selectionMethod.addItem("Manual Selection")
    self.selectionMethod.addItem("QuickView")
    self.selectionMethod.setStatusTip("Method used to select the gradients to exclude")
    self.selectionMethod.currentTextChanged.connect(self.EnableDisable)  
    protocol_layout.addWidget(self.selectionMethod)
    self.selectionMethod.currentTextChanged.connect(self.GetParams)
    # gradientsToExclude
    protocol_layout.addWidget(QLabel(exclude_yml["protocol"]["gradientsToExclude"]["caption"] + " (comma separated list)"))
    self.gradients2exclude = QTextEdit()
    self.gradients2exclude.setStatusTip(exclude_yml["protocol"]["gradientsToExclude"]["description"])
    self.gradients2exclude.textChanged.connect(self.GetGradients)
    protocol_layout.addWidget(self.gradients2exclude)
    self.gradients2exclude.textChanged.connect(self.GetParams)

    ## Layout
    layout_v = QVBoxLayout()
    layout_v.addWidget(self.tab_name)
    layout_v.addWidget(description_label)
    layout_v.addWidget(options_groupbox)
    layout_v.addWidget(protocol_groupbox)
    layout_v.addStretch(1)
    self.stack.setLayout(layout_v)

  def GetGradients(self): # get list of gradients typed by user
    self.gradientsToExclude_list = []
    text = self.gradients2exclude.toPlainText()
    text = text.split(",")
    for elmt in text:
      elmt = re.sub(r"\s+", "", elmt)
      if elmt.isnumeric():
        self.gradientsToExclude_list.append(int(elmt))    

  def EnableDisable(self): # disable space to write gradient indexes if QuickView is selected
    if self.selectionMethod.currentText() != "Manual Selection":
      self.gradients2exclude.setEnabled(False)
    else:
      self.gradients2exclude.setEnabled(True)

  def GetParams(self):
    params = [
      'Exclude Gradients',
      'MANUAL_Exclude', 
      {'options': {
        'overwrite': self.overwrite.isChecked(), 
        'skip': self.skip.isChecked(), 
        'write_image': self.writeimage.isChecked()
        }, 
      'protocol': {
        'gradientsToExclude': self.gradientsToExclude_list, 
        }
      }
    ]
    self.communicate.SendParams(params)