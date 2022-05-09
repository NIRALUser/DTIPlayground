from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 

from dtiplayground.ui.modules_details_communicate import ModulesDetailsCommunicate

class QCReport(QWidget):
  communicate = ModulesDetailsCommunicate()

  def __init__(self, protocol_template, qcreport_yml):
    QWidget.__init__(self)
    self.stack = QWidget()
    self.QCReportStack(protocol_template, qcreport_yml)

  def QCReportStack(self, protocol_template, qcreport_yml):

    ## Module
    self.tab_name = QLabel()

    ## Description
    for template_ite in range(len(protocol_template["options"]["execution"]["pipeline"]["candidates"])):
      if protocol_template["options"]["execution"]["pipeline"]["candidates"][template_ite]["value"] == "QC_Report":
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
    protocol_layout = QFormLayout()
    protocol_groupbox.setLayout(protocol_layout)
    # generatePDF
    self.generatePDF_true = QRadioButton("True")
    self.generatePDF_false = QRadioButton("False")
    generatePDF_layout = QHBoxLayout()
    generatePDF_layout.addWidget(self.generatePDF_true)
    generatePDF_layout.addWidget(self.generatePDF_false)
    self.generatePDF_buttongroup = QButtonGroup()
    self.generatePDF_buttongroup.addButton(self.generatePDF_true)
    self.generatePDF_buttongroup.addButton(self.generatePDF_false)
    self.generatePDF_true.toggled.connect(self.GetParams)
    self.generatePDF_true.setStatusTip(qcreport_yml["protocol"]["generatePDF"]["description"])
    self.generatePDF_false.setStatusTip(qcreport_yml["protocol"]["generatePDF"]["description"])
    protocol_layout.addRow(qcreport_yml["protocol"]["generatePDF"]["caption"], generatePDF_layout)
    # generateCSV
    self.generateCSV_true = QRadioButton("True")
    self.generateCSV_false = QRadioButton("False")
    generateCSV_layout = QHBoxLayout()
    generateCSV_layout.addWidget(self.generateCSV_true)
    generateCSV_layout.addWidget(self.generateCSV_false)
    self.generateCSV_buttongroup = QButtonGroup()
    self.generateCSV_buttongroup.addButton(self.generateCSV_true)
    self.generateCSV_buttongroup.addButton(self.generateCSV_false)
    self.generateCSV_true.toggled.connect(self.GetParams)
    self.generateCSV_true.setStatusTip(qcreport_yml["protocol"]["generateCSV"]["description"])
    self.generateCSV_false.setStatusTip(qcreport_yml["protocol"]["generateCSV"]["description"])
    protocol_layout.addRow(qcreport_yml["protocol"]["generateCSV"]["caption"], generateCSV_layout)    
    
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
      'QC Report',
      'QC_Report', 
      {'options': {
        'overwrite': self.overwrite.isChecked(), 
        'skip': self.skip.isChecked(), 
        }, 
      'protocol': {
        'generatePDF': self.generatePDF_true.isChecked(), 
        'generateCSV': self.generateCSV_true.isChecked()
        }
      }
    ]
    self.communicate.SendParams(params)