from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 
from pathlib import Path
import re
import os
from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSignal as Signal

from ui.loadingbutton import LoadingButton
from ui.quickview import QuickView

class ExecutionTabCommunicate(QObject):

  call_DeleteTempDirectory = Signal()
  call_UpdateNumberOfInputs = Signal(int)
  check_manual_exclude = Signal()
  call_compute = Signal(list)
  call_write_protocol_yml = Signal(str)
  check_unsaved_changes = Signal()
  call_save_protocol = Signal()

  def CallDeleteTempDirectory(self):
    self.call_DeleteTempDirectory.emit()

  def NumberOfInputs(self, multi_input):
    self.call_UpdateNumberOfInputs.emit(multi_input)

  def CheckManualExclude(self):
    self.check_manual_exclude.emit()

  def CallCompute(self, computation_details):
    self.call_compute.emit(computation_details)

  def CallWriteProtocolYML(self, temp_path):
    self.call_write_protoocl_yml(temp_path)

  def CheckUnsavedChangesAndStartCompute(self):
    self.check_unsaved_changes.emit()

  def CallSaveProtocol(self):
    self.call_save_protocol.emit()


class ExecutionTab(QWidget):
  communicate = ExecutionTabCommunicate()

  def __init__(self, protocol_template):
    QWidget.__init__(self)
    self.mulri_input = 0
    
    self.tab = QWidget() 
    self.communicate.call_UpdateNumberOfInputs.connect(self.UpdateNumberOfInputs)
    self.communicate.call_compute.connect(self.Compute)

    self.ExecutionTab(protocol_template)

  def ExecutionTab(self, protocol_template):

    layout = QGridLayout()
    self.input_layout = QGridLayout()
    
    self.input_line = QLineEdit()
    if hasattr(self, "input_filename"):
      self.input_line.setText(self.input_filename)
    self.input_line.setAlignment(Qt.AlignRight)
    self.input_line.editingFinished.connect(self.UpdateOutputFilenameBase)
    self.input_line_label = QLabel("Input image:")
    self.input_browse_button = QPushButton("Browse")
    self.input_browse_button.clicked.connect(self.BrowseButton0)
    self.input_layout.addWidget(self.input_line_label, 0, 0)
    self.input_layout.addWidget(self.input_line, 0, 1)
    self.input_layout.addWidget(self.input_browse_button, 0, 2)
    layout.addLayout(self.input_layout, 0, 0, 1, 6)

    self.output_image_basename = QLineEdit()
    self.output_image_basename.setAlignment(Qt.AlignRight)
    output_image_basename_label = QLabel("Output image basename")
    layout.addWidget(output_image_basename_label, 1, 0)
    layout.addWidget(self.output_image_basename, 1, 1, 1, 5)
    
    self.output_line = QLineEdit()
    self.output_line.setAlignment(Qt.AlignRight)
    self.output_line.setStatusTip(protocol_template["options"]["io"]["output_directory"]["description"])
    output_line_label = QLabel(protocol_template["options"]["io"]["output_directory"]["caption"])
    layout.addWidget(output_line_label, 2, 0)
    layout.addWidget(self.output_line, 2, 1, 1, 5)

    layout.addWidget(QLabel("Computation:"), 3, 0)
    self.cluster_computation = QRadioButton("Cluster / Slurm")
    layout.addWidget(self.cluster_computation, 3, 1)
    self.local_computation = QRadioButton("Local")
    self.local_computation.setChecked(True)
    layout.addWidget(self.local_computation, 3, 2)

    self.threads_line = QLineEdit()
    self.threads_line.setValidator(QIntValidator())
    self.threads_line.setAlignment(Qt.AlignRight)
    layout.addWidget(QLabel("Number of threads to use:"), 3, 4)
    layout.addWidget(self.threads_line, 3, 5)

    compute_button = LoadingButton("Compute")
    compute_button.clicked.connect(self.CheckInputFile)
    gif_path = Path(__file__).parent.joinpath('workinprogress.gif')
    compute_button.setGif(gif_path.__str__())
    layout.addWidget(compute_button, 4, 0, 1, 4)

    stop_compute_button = QPushButton("Stop Computation")
    layout.addWidget(stop_compute_button, 4, 4, 1, 2)

    self.output_display = QTextEdit(readOnly = True)
    self.output_display.setAcceptRichText(True)
    layout.addWidget(QLabel("Output:"), 5, 0)
    layout.addWidget(self.output_display, 6, 0, 1, 4)
    layout.setColumnStretch(2, 2)
    self.output_display.document().setMaximumBlockCount(1000000)

    self.error_display = QTextEdit(readOnly = True)
    layout.addWidget(QLabel("Error(s):"), 5, 4)
    layout.addWidget(self.error_display, 6, 4, 1, 2)
    layout.setColumnStretch(3, 0)

    self.process = QtCore.QProcess(self)
    self.process.readyReadStandardError.connect(self.DisplayError)
    self.process.readyReadStandardOutput.connect(self.DisplayOutput)    
    self.process.started.connect(lambda: compute_button.start())
    self.process.started.connect(lambda: compute_button.setEnabled(False))
    self.process.finished.connect(lambda: compute_button.setEnabled(True))
    self.process.finished.connect(lambda: compute_button.stop())
    self.process.finished.connect(self.communicate.CallDeleteTempDirectory)
    stop_compute_button.clicked.connect(self.process.kill)
    
    self.no_input_popup = QMessageBox()
    self.no_input_popup.setText("Missing input file.")
    self.no_input_popup.setWindowTitle("DMRIPrep message")

    self.unsaved_changes_popup = QMessageBox()
    self.unsaved_changes_popup.setWindowTitle("Unsaved changes")
    self.unsaved_changes_popup.setText("Unsaved modicfications have been made to the protocol. Do you want to save the modifications or ignore them?")
    self.unsaved_changes_popup.setStandardButtons(QMessageBox.Save | QMessageBox.Ignore)
    self.unsaved_changes_popup.setDefaultButton(QMessageBox.Save)
    self.unsaved_changes_popup.buttonClicked.connect(self.UnsavedPopupClicked)

    self.tab.setLayout(layout)


  def UpdateNumberOfInputs(self, multi_input):
    self.multi_input = multi_input

    # remove all rows from QGridLayout input_layout 
    if self.input_layout.count() <= self.input_layout.columnCount(): #if only one line in input_layout 
      self.input_layout.removeWidget(self.input_line_label)
      self.input_line_label.deleteLater()
      del self.input_line_label
      self.input_layout.removeWidget(self.input_line)
      self.input_line.deleteLater()
      del self.input_line
      self.input_layout.removeWidget(self.input_browse_button)
      self.input_browse_button.deleteLater()
      del self.input_browse_button
    else: #if more than one line in input_layout
      self.input_layout.removeWidget(self.input_line_label1)
      self.input_line_label1.deleteLater()
      del self.input_line_label1
      self.input_layout.removeWidget(self.input_line1)
      self.input_line1.deleteLater()
      del self.input_line1
      self.input_layout.removeWidget(self.input_browse_button1)
      self.input_browse_button1.deleteLater()
      del self.input_browse_button1
      self.input_layout.removeWidget(self.input_line_label2)
      self.input_line_label2.deleteLater()
      del self.input_line_label2
      self.input_layout.removeWidget(self.input_line2)
      self.input_line2.deleteLater()
      del self.input_line2
      self.input_layout.removeWidget(self.input_browse_button2)
      self.input_browse_button2.deleteLater()
      del self.input_browse_button2
      
    # set new input_layout with 1 input file
    if self.multi_input == 0:
      self.input_line = QLineEdit()
      self.input_line.setAlignment(Qt.AlignRight)
      if hasattr(self, "input_filename"):
        self.input_line.setText(self.input_filename)
      self.input_line.editingFinished.connect(self.UpdateOutputFilenameBase)
      self.input_line_label = QLabel("Input image:")
      self.input_browse_button = QPushButton("Browse")
      self.input_browse_button.clicked.connect(self.BrowseButton0)
      self.input_layout.addWidget(self.input_line_label, 0, 0)
      self.input_layout.addWidget(self.input_line, 0, 1)
      self.input_layout.addWidget(self.input_browse_button, 0, 2)
      
    # set new input_layout with 2 input files
    if self.multi_input == 1:
      self.input_line_label1 = QLabel("Direction 1 input image:")
      self.input_layout.addWidget(self.input_line_label1, 0, 0)
      self.input_line1 = QLineEdit()
      self.input_line1.setAlignment(Qt.AlignRight)
      if hasattr(self, "input_filename1"):
        self.input_line1.setText(self.input_filename1)
      self.input_line1.editingFinished.connect(self.UpdateOutputFilenameBase)
      self.input_layout.addWidget(self.input_line1, 0, 1)
      self.input_browse_button1 = QPushButton("Browse")
      self.input_browse_button1.clicked.connect(self.BrowseButton1)
      self.input_layout.addWidget(self.input_browse_button1, 0, 2)
      self.input_line_label2 = QLabel("Direction 2 input image:")
      self.input_layout.addWidget(self.input_line_label2, 1, 0)
      self.input_line2 = QLineEdit()
      self.input_line2.setAlignment(Qt.AlignRight)
      if hasattr(self, "input_filename2"):
        self.input_line2.setText(self.input_filename2)
      self.input_layout.addWidget(self.input_line2, 1, 1)
      self.input_browse_button2 = QPushButton("Browse")
      self.input_browse_button2.clicked.connect(self.BrowseButton2)
      self.input_layout.addWidget(self.input_browse_button2, 1, 2)

  def UpdateOutputFilenameBase(self):
    if self.multi_input == 0:
      input_path = self.input_filename
    else:
      input_path = self.input_filename1
    image = input_path.split("/")[-1]
    basename = image.split(".")[0]
    self.output_image_basename.setText(basename)

  def CheckInputFile(self):
    if (self.multi_input == 0 and self.input_line.text() == "") or (self.multi_input == 1 and (self.input_line1.text() == "" or self.input_line2.text() == "")):
      self.no_input_popup.exec_()
    else:
      self.communicate.CheckManualExclude()

  def Compute(self, computation_details):
    
    manual_exclude = computation_details[0] #True if MANUAL_Exclude in protocol, False if not
    quickview = computation_details[1] #True if QuickView selected, False if not
    
    if manual_exclude and quickview:
      print("QuickView")
      self.quickview_window = QuickView(self.input_filename)
      self.quickview_window.show()

    if manual_exclude and not quickview: #update dic_protocol, write temp protocol, start compute temp protocol
      if not os.path.exists("temp_dmriprep_ui"):
        os.mkdir("temp_dmriprep_ui")
        print("Directory 'temp_dmriprep_ui' created")
      else:
        print("Directory 'temp_dmriprep_ui' already exists")
      self.communicate.CallWriteProtocolYML("temp_dmriprep_ui/protocol.yml")
      self.StartComputation("temp_dmriprep_ui/protocol.yml")
    if not manual_exclude and not quickview: 
      self.communicate.CheckUnsavedChangesAndStartCompute()

  def StartComputation(self, protocol):
    arguments = ["run", "-i"] 
    if self.multi_input == 0:
      arguments.append(self.input_filename)
    else:
      arguments.append(self.input_filename1)
      arguments.append(self.input_filename2)
    arguments.append("-p")
    arguments.append(protocol)
    arguments.append("-o")
    if self.multi_input == 0:
      inputpath = self.input_filename
    else:
      inputpath = self.input_filename1
    if self.output_line.text() != '':
      if str(Path(inputpath).parent) not in self.output_line.text():
        outputpath = str(Path(inputpath).parent) + "/" + self.output_line.text()
      else:
        outputpath = self.output_line.text()
    else: #set default output directory
      suffix = "_dmriprep-dev_output"
      if ".nrrd" in inputpath:
        outputpath = inputpath.replace(".nrrd", suffix)
      if ".nii.gz" in inputpath:
        outputpath = inputpath.replace(".nii.gz", suffix)
      if ".nii" in inputpath:
        outputpath = inputpath.replace(".nii", suffix)
      #check that directory does not already exist
      counter = 0
      new_outputpath = outputpath
      while os.path.exists(new_outputpath):
        new_outputpath = outputpath + "_" + str(counter)
        counter += 1
        outputpath = new_outputpath
      self.output_line.setText(outputpath)

    arguments.append(outputpath)
    if self.output_image_basename.text != '':
      arguments.append("--output-file-base")
      arguments.append(self.output_image_basename.text())
    if self.threads_line.text() != '':
      arguments.append("--num-threads")
      arguments.append(self.threads_line.text())

    if self.local_computation.isChecked():
      self.process.start("dmriprep-dev", arguments)
    if self.cluster_computation.isChecked():
      arguments[6] = arguments[6].split("/")[-1]
      arguments = ["longleaf.unc.edu", "'", "/proj/NIRAL/containers/dtiplaygroung/dmriprep_longleaf"] + arguments + ["'"]
      self.process.start("ssh", arguments)

  def UnsavedPopupClicked(self, i):
    if i.text() == "Save":
      self.communicate.CallSaveProtocol()

  def BrowseButton0(self):
    text = self.BrowseInputFile()
    self.input_line.setText(text)
    if text != "":
      self.input_filename = text
      self.UpdateOutputFilenameBase()

  def BrowseButton1(self):
    text = self.BrowseInputFile()
    self.input_line1.setText(text)
    if text != "":
      self.input_filename1 = text
      self.UpdateOutputFilenameBase()

  def BrowseButton2(self):
    text = self.BrowseInputFile()
    self.input_line2.setText(text)
    if text != "":
      self.input_filename2 = text

  def BrowseInputFile(self):
    #self.output_line.setText("")
    file_filter = "Image file (*.nrrd *.nii *.nii.gz)"
    file_name = QFileDialog.getOpenFileName(
      parent = self,
      caption = "Select an input file",
      filter = file_filter
      )
    return file_name[0]

  def DisplayOutput(self):
    stdout = self.process.readAllStandardOutput()
    stdout = stdout.data().decode("utf8")

    # colors
    stdout = re.sub(r"\\[95m", "<p style='color:lightpurple;'>", stdout)
    stdout = re.sub(r"\\[35m", "<p style='color:purple;'>", stdout)
    stdout = re.sub(r"\\[96m", "<p style='color:lightcyan;'>", stdout)
    stdout = re.sub(r"\\[36m", "<p style='color:cyan;'>", stdout)
    stdout = re.sub(r"\\[94m", "<p style='color:lightblue;'>", stdout)
    stdout = re.sub(r"\\[34m", "<p style='olor:blue;'>", stdout)
    stdout = re.sub(r"\\[92m", "<p style='color:lightgreen;'>", stdout)
    stdout = re.sub(r"\\[32m", "<p style='color:green;'>", stdout)
    stdout = re.sub(r"\\[93m", "<p style='color:lightyellow;'>", stdout)
    stdout = re.sub(r"\\[33m", "<p style='color:yellow;'>", stdout)
    stdout = re.sub(r"\\[91m", "<p style='color:lightred;'>", stdout)
    stdout = re.sub(r"\\[31m", "<p style='color:red;'>", stdout)    
    stdout = re.sub(r"\\[90m", "<p style='color:gray;'>", stdout)
    stdout = re.sub(r"\\[30m", "<p style='color:black;'>", stdout)
    # style
    stdout = re.sub(r"\\[1m", "<p style='font-weight: 900;'>", stdout)
    stdout = re.sub(r"\\[4m", "<p style='text-decoration: underline;'>", stdout)
    stdout = re.sub(r"\\[0m", "</span>", stdout)
    stdout = re.sub(r"\n", "</p><p>", stdout)
    stdout = re.sub(r"\t", "<span STYLE='padding:0 0 0 20px;'>", stdout)
    self.output_display.insertHtml(stdout)
    self.output_display.verticalScrollBar().setValue(self.output_display.verticalScrollBar().maximum())

  def DisplayError(self):
    stderr = self.process.readAllStandardError()
    stderr = bytes(stderr).decode("utf8")
    # colors
    stdout = re.sub(r"\\[95m", "<p style='color:lightpurple;'>", stderr)
    stdout = re.sub(r"\\[35m", "<p style='color:purple;'>", stderr)
    stdout = re.sub(r"\\[96m", "<p style='color:lightcyan;'>", stderr)
    stdout = re.sub(r"\\[36m", "<p style='color:cyan;'>", stderr)
    stdout = re.sub(r"\\[94m", "<p style='color:lightblue;'>", stderr)
    stdout = re.sub(r"\\[34m", "<p style='olor:blue;'>", stderr)
    stdout = re.sub(r"\\[92m", "<p style='color:lightgreen;'>", stderr)
    stdout = re.sub(r"\\[32m", "<p style='color:green;'>", stderr)
    stdout = re.sub(r"\\[93m", "<p style='color:lightyellow;'>", stderr)
    stdout = re.sub(r"\\[33m", "<p style='color:yellow;'>", stderr)
    stdout = re.sub(r"\\[91m", "<p style='color:lightred;'>", stderr)
    stdout = re.sub(r"\\[31m", "<p style='color:red;'>", stderr)    
    stdout = re.sub(r"\\[90m", "<p style='color:gray;'>", stderr)
    stdout = re.sub(r"\\[30m", "<p style='color:black;'>", stderr)
    # style
    stdout = re.sub(r"\\[1m", "<p style='font-weight: 900;'>", stderr)
    stdout = re.sub(r"\\[4m", "<p style='text-decoration: underline;'>", stderr)
    stdout = re.sub(r"\\[0m", "</p>", stderr)

    self.error_display.setHtml(stderr)