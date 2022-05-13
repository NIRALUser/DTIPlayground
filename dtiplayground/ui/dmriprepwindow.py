from PyQt5.QtWidgets import * 

from functools import partial
from dtiplayground.ui.softwarepaths import SoftwarePaths
from dtiplayground.ui.dmriprepUI import Widgets
import dtiplayground.config as config


class Window(QMainWindow):

  def __init__(self, protocol_template, args):
    super().__init__()
    self.setWindowTitle("DMRIPrep - " + config.INFO["dmriprep"]["version"])
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

    # Configurate software paths
    configSoftware = QAction('Softwares', self)
    configSoftware.setStatusTip('Set software paths')
    self.software_window = SoftwarePaths()
    configSoftware.triggered.connect(self.ShowSoftwareWindow)

    self.statusBar() 
    
    # Menu
    menubar = self.menuBar()
    fileMenu = menubar.addMenu('&File')
    fileMenu.addAction(saveAct)
    fileMenu.addAction(saveasAct)
    fileMenu.addAction(exitAct)
    configMenu = menubar.addMenu('Config')
    configMenu.addAction(configSoftware)
    
    self.show()

  def ShowSoftwareWindow(self): 
    self.software_window.show()
