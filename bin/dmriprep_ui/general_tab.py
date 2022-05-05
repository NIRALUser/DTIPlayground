from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 

from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSignal as Signal


class GeneralCommunicate(QObject):

  call_UnsavedModif = Signal()

  def CallUnsavedModif(self):
    self.call_UnsavedModif.emit()

class General(QWidget):
  communicate = GeneralCommunicate()

  def __init__(self, protocol_template, protocol_yml):
    QWidget.__init__(self)
    self.protocol_template = protocol_template
    self.tab = QWidget()

    self.GeneralParameters()
    self.InitializeParameters(protocol_yml)


  def GeneralParameters(self):
    general_layout = QFormLayout()
    self.tab.setLayout(general_layout)
    
    no_output_image = QHBoxLayout()
    self.no_output_image_false = QRadioButton("Yes")
    no_output_image.addWidget(self.no_output_image_false)
    self.no_output_image_true = QRadioButton("No")
    no_output_image.addWidget(self.no_output_image_true)
    general_layout.addRow("Create Output Image", no_output_image)
    self.no_output_image_false.toggled.connect(self.communicate.CallUnsavedModif)
    self.no_output_image_true.toggled.connect(self.communicate.CallUnsavedModif)

    self.output_format = QComboBox()
    for ite in self.protocol_template["options"]["io"]["output_format"]["candidates"]:
      self.output_format.addItem(ite["caption"])
      self.output_format.setItemData(self.output_format.count()-1, ite["description"], QtCore.Qt.ToolTipRole)
    self.output_format.currentTextChanged.connect(self.GetOutputImageTypeIt)
    general_layout.addRow(self.protocol_template["options"]["io"]["output_format"]["caption"], self.output_format)
    self.output_format.currentTextChanged.connect(self.communicate.CallUnsavedModif)

    self.no_output_image_false.clicked.connect(lambda: self.output_format.setEnabled(True))
    self.no_output_image_true.clicked.connect(lambda: self.output_format.setEnabled(False))

    self.b0 = QDoubleSpinBox()
    self.b0.setAlignment(Qt.AlignRight)
    self.b0.setSingleStep(0.1)
    self.b0.setDecimals(3)
    self.b0.setStatusTip(self.protocol_template["options"]["io"]["baseline_threshold"]["description"])
    general_layout.addRow(self.protocol_template["options"]["io"]["baseline_threshold"]["caption"], self.b0)
    self.b0.valueChanged.connect(self.communicate.CallUnsavedModif)

  def GetOutputImageTypeIt(self, text): # general parameter 
    self.outputimagetype_it = 0
    for it in range(len(self.protocol_template["options"]["io"]["output_format"]["candidates"])):
      if self.protocol_template["options"]["io"]["output_format"]["candidates"][it]["caption"] == text:
        self.outputimagetype_it = it
  
  def InitializeParameters(self, protocol_yml):
    if protocol_yml["io"]["no_output_image"] == False:
      self.no_output_image_false.setChecked(True)
    else:
      self.no_output_image_true.setChecked(True)
    image_type = protocol_yml["io"]["output_format"]
    for ite in self.protocol_template["options"]["io"]["output_format"]["candidates"]:
      if ite["value"] == image_type:
        self.output_format.setCurrentText(ite["caption"])
        self.GetOutputImageTypeIt(ite["caption"])
    self.b0.setValue(protocol_yml["io"]["baseline_threshold"])