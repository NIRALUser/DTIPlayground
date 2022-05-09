from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 

class NoModule(QWidget):

  def __init__(self):
    QWidget.__init__(self)
    self.stack = QWidget()
    self.NoModuleStack()

  def NoModuleStack(self):
    label0 = QLabel("No module selected.")
    label1 = QLabel("Click on a module in the Protocol list to display its parameters.")
    label2 = QLabel("To add a module in the Protocol list, go to 'Select' tab, then select the module(s) of your choice and drag the module(s) into the Protocol list on the left.")
    label2.setWordWrap(True)

    no_module_layout_v = QVBoxLayout()
    no_module_layout_v.addStretch(1)
    no_module_layout_v.addWidget(label0)
    no_module_layout_v.addStretch(1)
    no_module_layout_v.addWidget(label1)
    no_module_layout_v.addWidget(label2)
    no_module_layout_v.addStretch(4)
    self.stack.setLayout(no_module_layout_v)