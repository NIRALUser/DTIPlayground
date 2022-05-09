from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 
import sys
import yaml
from yaml.loader import SafeLoader
from pathlib import Path
import os
import re
import argparse

import numpy

from PIL import Image, ImageEnhance
from PIL.ImageQt import ImageQt

from functools import partial

from dtiplayground.ui.dmriprepUI import Widgets

class Window(QMainWindow):

  def __init__(self, protocol_template, args):
    super().__init__()
    self.setWindowTitle("DMRIPrep")
    dmriprep = Widgets(self, protocol_template, args)
    self.setCentralWidget(dmriprep)

    # Exit application
    exitAct = QAction('&Exit', self)
    exitAct.setShortcut('Ctrl+Q')
    exitAct.setStatusTip('Exit application')
    exitAct.triggered.connect(qApp.quit)
    
    # Save protocol file
    saveAct = QAction('&Save', self)
    saveAct.setShortcut('Ctrl+S')
    saveAct.setStatusTip('Save protocol file')
    saveAct.triggered.connect(dmriprep.protocol_tab.SaveProtocol)

    # Save As
    saveasAct = QAction('&Save As', self)
    saveasAct.setStatusTip('Save protocol file as...')
    saveasAct.triggered.connect(dmriprep.protocol_tab.SaveAs)

    self.statusBar() 
    
    # Menu
    menubar = self.menuBar()
    fileMenu = menubar.addMenu('&File')
    fileMenu.addAction(saveAct)
    fileMenu.addAction(saveasAct)
    fileMenu.addAction(exitAct)
    
    self.show()
