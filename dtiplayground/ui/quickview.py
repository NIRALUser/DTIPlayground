from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from PyQt5.QtGui import *
from PyQt5.QtCore import * 
from PIL import Image, ImageEnhance
from PIL.ImageQt import ImageQt
from functools import partial
import SimpleITK as sitk
import numpy
import os

from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSignal as Signal


class QuickViewCommunicate(QObject):

  execute_exclude_gradients = Signal(list)

  def __init__(self):
    super(QuickViewCommunicate, self).__init__()

  def Execution(self, list_of_gradients):
    self.execute_exclude_gradients.emit(list_of_gradients)


class QuickView(QMainWindow):
  signal_quickview = QuickViewCommunicate()

  def __init__(self, image_name):
    QMainWindow.__init__(self)

    self.setWindowTitle("QuickView")
    widget = QWidget()
    self.setCentralWidget(widget)

    quickview_layout = QHBoxLayout()
    widget.setLayout(quickview_layout)

    images_groupbox = QGroupBox()
    self.images_layout = QGridLayout()
    images_groupbox.setLayout(self.images_layout)

    options_groupbox = QGroupBox()
    self.options_layout = QVBoxLayout()
    options_groupbox.setLayout(self.options_layout)
    
    gradients_groupbox = QGroupBox()
    self.gradients_layout = QVBoxLayout()
    gradients_groupbox.setLayout(self.gradients_layout)

    self.menu_layout = QVBoxLayout()
    self.menu_layout.addWidget(options_groupbox)
    self.menu_layout.addWidget(gradients_groupbox)  
    
    self.image_name = image_name

    self.LoadImage()
    self.Menu()
    if ".nrrd" in self.image_name:
      self.CreateButtonsNRRD()
    else:
      self.CreateButtonsNIFTI()
    
    scroll = QScrollArea()
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
    scroll.setWidgetResizable(True)
    scroll.setWidget(images_groupbox)

    quickview_layout.addWidget(scroll, 80)
    quickview_layout.addLayout(self.menu_layout, 20)

    self.show()
    
  def Menu(self):   
    self.columns = 9 #default
    max_slice = self.size[0] #default
    self.zslice = self.size[0]//2 #default
    self.gradients_layout.addWidget(QLabel("Selected gradients:"))
    self.gradientsToExclude_list = []
    self.gradientsToExclude_label = QLabel(str(self.gradientsToExclude_list))
    self.gradientsToExclude_label.setWordWrap(True)
    self.gradients_layout.addWidget(self.gradientsToExclude_label)
    self.gradients_layout.addStretch(1)
    
    compute_button = QPushButton("Exclude Gradients")
    compute_button.clicked.connect(self.ComputeExcludeGradients)
    self.gradients_layout.addWidget(compute_button)
    
    self.options_layout.addWidget(QLabel("View:"))
    self.sagittal = QRadioButton("Sagittal View")
    self.sagittal.clicked.connect(self.ChangeView)
    self.sagittal.setChecked(True) #default
    self.options_layout.addWidget(self.sagittal)
    self.coronal = QRadioButton("Coronal View")
    self.coronal.clicked.connect(self.ChangeView)
    self.options_layout.addWidget(self.coronal)
    self.axial = QRadioButton("Axial View")
    self.axial.clicked.connect(self.ChangeView)
    self.options_layout.addWidget(self.axial)
    self.options_layout.addStretch(1)

    self.options_layout.addWidget(QLabel("Slice:"))
    self.slice_selector_slidebar = QSlider(Qt.Horizontal)
    self.slice_selector_slidebar.setSingleStep(1)
    self.slice_selector_slidebar.setMinimum(0)
    self.slice_selector_slidebar.setMaximum(max_slice) #default
    self.slice_selector_slidebar.setValue(self.zslice) #default
    self.slice_selector_slidebar.valueChanged.connect(lambda: self.slice_selector_spinbox.setValue(self.slice_selector_slidebar.value()))
    self.slice_selector_slidebar.sliderReleased.connect(self.ChangeSlice)
    self.options_layout.addWidget(self.slice_selector_slidebar)
    self.slice_selector_spinbox = QSpinBox()
    self.slice_selector_spinbox.setAlignment(Qt.AlignRight)
    self.slice_selector_spinbox.setSingleStep(1)
    self.slice_selector_spinbox.setMinimum(0)
    self.slice_selector_spinbox.setMaximum(max_slice) #default
    self.slice_selector_spinbox.setValue(self.zslice) #default
    self.slice_selector_spinbox.valueChanged.connect(lambda: self.slice_selector_slidebar.setValue(self.slice_selector_spinbox.value()))
    self.slice_selector_spinbox.valueChanged.connect(self.ChangeSlice)
    self.options_layout.addWidget(self.slice_selector_spinbox)
    self.options_layout.addStretch(1)

    self.options_layout.addWidget(QLabel("Number of columns:"))
    self.images_per_row = QSpinBox()
    self.images_per_row.setMinimum(1)
    if ".nrrd" in self.image_name:
      self.images_per_row.setMaximum(self.number_gradients)
    else:
      self.images_per_row.setMaximum(self.size[3])
    self.images_per_row.setAlignment(Qt.AlignRight)
    self.images_per_row.setValue(self.columns)
    self.images_per_row.valueChanged.connect(self.ChangeColumns)
    self.options_layout.addWidget(self.images_per_row)
    self.options_layout.addStretch(1)

    self.zoom_factor = 1
    self.options_layout.addWidget(QLabel("Zoom factor:"))
    self.zoom = QDoubleSpinBox()
    self.zoom.setValue(self.zoom_factor)
    self.zoom.valueChanged.connect(self.ChangeZoom)
    self.options_layout.addWidget(self.zoom)
    self.options_layout.addStretch(1)

    self.brightness_factor = 1
    self.options_layout.addWidget(QLabel("Brightness:"))
    self.brightness_slidebar = QSlider(Qt.Horizontal)
    self.brightness_slidebar.setMinimum(0)
    self.brightness_slidebar.setMaximum(100) 
    self.brightness_slidebar.setValue(self.brightness_factor*50) 
    self.brightness_slidebar.valueChanged.connect(self.ChangeBrightness)
    self.options_layout.addWidget(self.brightness_slidebar)
    self.options_layout.addStretch(1)

    self.contrast_factor = 1
    self.options_layout.addWidget(QLabel("Contrast:"))
    self.contrast_slidebar = QSlider(Qt.Horizontal)
    self.contrast_slidebar.setMinimum(0)
    self.contrast_slidebar.setMaximum(100) 
    self.contrast_slidebar.setValue(self.contrast_factor*50) 
    self.contrast_slidebar.valueChanged.connect(self.ChangeContrast)
    self.options_layout.addWidget(self.contrast_slidebar)
    self.options_layout.addStretch(1)

  def LoadImage(self):
    print("image", self.image_name)
    self.input_image = sitk.ReadImage(self.image_name)
    self.size = list(self.input_image.GetSize())
    self.spacing = list(self.input_image.GetSpacing())
    self.number_gradients = self.input_image.GetNumberOfComponentsPerPixel()

  def AxialViewNRRD(self):
    self.number_slices = self.size[2]
    index = [0, 0, self.zslice]
    spacing_matrix = QTransform()
    spacing_matrix.scale(self.spacing[0], self.spacing[1])
    slice_extractor = sitk.ExtractImageFilter()
    slice_extractor.SetSize([self.size[0], self.size[1], 0])
    slice_extractor.SetIndex(index)
    extracted_slice = slice_extractor.Execute(self.input_image)
    return extracted_slice, spacing_matrix

  def SagittalViewNRRD(self):
    self.number_slices = self.size[0]
    index = [self.zslice, 0, 0, ]
    spacing_matrix = QTransform()
    spacing_matrix.scale(self.spacing[1], self.spacing[2])
    slice_extractor = sitk.ExtractImageFilter()
    slice_extractor.SetSize([0, self.size[1], self.size[2]])
    slice_extractor.SetIndex(index)
    extracted_slice = slice_extractor.Execute(self.input_image)
    return extracted_slice, spacing_matrix

  def CoronalViewNRRD(self):
    self.number_slices = self.size[1]
    index = [0, self.zslice, 0]
    spacing_matrix = QTransform()
    spacing_matrix.scale(self.spacing[0], self.spacing[2])
    slice_extractor = sitk.ExtractImageFilter()    
    slice_extractor.SetSize([self.size[0], 0, self.size[2]])
    slice_extractor.SetIndex(index)
    extracted_slice = slice_extractor.Execute(self.input_image)
    return extracted_slice, spacing_matrix
    
  def CreateButtonsNRRD(self):

    self.dic = {}
    
    if self.axial.isChecked():
      extracted_slice, spacing_matrix = self.AxialViewNRRD()
    if self.sagittal.isChecked():
      extracted_slice, spacing_matrix = self.SagittalViewNRRD()
    if self.coronal.isChecked():
      extracted_slice, spacing_matrix = self.CoronalViewNRRD()

    for iter_gradients in range(self.number_gradients):
      self.button = QPushButton()
      self.dic[str(iter_gradients)] = self.button
      
      gradient_extractor = sitk.VectorIndexSelectionCastImageFilter()
      gradient_extractor.SetIndex(iter_gradients)
      gradient = gradient_extractor.Execute(extracted_slice)

      gradient_array = sitk.GetArrayFromImage(gradient)

      # min max scaling for brightness
      gradient_array_normalized = (gradient_array - numpy.min(gradient_array)) * round(255 / numpy.max(gradient_array), 3)
      if self.sagittal.isChecked() or self.coronal.isChecked():
        gradient_array_normalized = numpy.flipud(gradient_array_normalized) #if SAGITTAL or CORONAL
      gradient_image = Image.fromarray(gradient_array_normalized)
      gradient_image = gradient_image.convert("L")
      gradient_image2 = gradient_image.resize((int(self.zoom_factor*gradient_image.width), int(self.zoom_factor*gradient_image.height)))
      # brightness and contrast
      brightness_enhancer = ImageEnhance.Brightness(gradient_image2)
      gradient_image3 = brightness_enhancer.enhance(self.brightness_factor)
      contrast_enhancer = ImageEnhance.Contrast(gradient_image3)
      gradient_image4 = contrast_enhancer.enhance(self.contrast_factor)

      gradient_qimage = ImageQt(gradient_image4)
      gradient_qimage.transformed(spacing_matrix)
      gradient_qpixmap = QtGui.QPixmap.fromImage(gradient_qimage)  

      self.button.setIcon(QIcon(gradient_qpixmap))
      self.button.setIconSize(gradient_qpixmap.size())
      self.images_layout.addWidget(QLabel("DWI " + str(iter_gradients)), 2*(iter_gradients//self.columns), iter_gradients%self.columns, QtCore.Qt.AlignCenter)
      self.images_layout.addWidget(self.button, 2*(iter_gradients//self.columns)+1, iter_gradients%self.columns)
      self.button.clicked.connect(partial(self.ButtonClicked, dwi=iter_gradients)) 
      if iter_gradients in self.gradientsToExclude_list:
        self.button.setStyleSheet("background-color : red")
      else:
        self.button.setStyleSheet("background-color : black") 
    
  def SagittalViewNIFTI(self, iter_gradients):
    self.number_slices = self.size[0]
    index = [self.zslice, 0, 0, iter_gradients]
    spacing_matrix = QTransform()
    spacing_matrix.scale(self.spacing[1], self.spacing[2])
    slice_extractor = sitk.ExtractImageFilter()
    slice_extractor.SetSize([0, self.size[1], self.size[2], 0])
    slice_extractor.SetIndex(index)
    gradient = slice_extractor.Execute(self.input_image)
    return gradient, spacing_matrix

  def CoronalViewNIFTI(self, iter_gradients):
    self.number_slices = self.size[1]
    index = [0, self.zslice, 0, iter_gradients]
    spacing_matrix = QTransform()
    spacing_matrix.scale(self.spacing[0], self.spacing[2])
    slice_extractor = sitk.ExtractImageFilter()    
    slice_extractor.SetSize([self.size[0], 0, self.size[2], 0])
    slice_extractor.SetIndex(index)
    gradient = slice_extractor.Execute(self.input_image)
    return gradient, spacing_matrix

  def AxialViewNIFTI(self, iter_gradients):
    self.number_slices = self.size[2]
    index = [0, 0, self.zslice, iter_gradients]
    spacing_matrix = QTransform()
    spacing_matrix.scale(self.spacing[0], self.spacing[1])
    slice_extractor = sitk.ExtractImageFilter()
    slice_extractor.SetSize([self.size[0], self.size[1], 0, 0])
    slice_extractor.SetIndex(index)
    gradient = slice_extractor.Execute(self.input_image)
    return gradient, spacing_matrix

  def CreateButtonsNIFTI(self):
    
    self.dic = {}
    for iter_gradients in range(self.size[3]):
      self.button = QPushButton()
      self.dic[str(iter_gradients)] = self.button
      
      if self.sagittal.isChecked():
        gradient, spacing_matrix = self.SagittalViewNIFTI(iter_gradients)
      if self.coronal.isChecked():
        gradient, spacing_matrix = self.CoronalViewNIFTI(iter_gradients)
      if self.axial.isChecked():
        gradient, spacing_matrix = self.AxialViewNIFTI(iter_gradients)

      gradient_array = sitk.GetArrayFromImage(gradient)

      # min max scaling for brightness
      gradient_array_normalized = (gradient_array - numpy.min(gradient_array)) * round(255 / numpy.max(gradient_array), 3)
      if self.sagittal.isChecked() or self.coronal.isChecked():
        gradient_array_normalized = numpy.flipud(gradient_array_normalized) #if SAGITTAL or CORONAL
      gradient_image = Image.fromarray(gradient_array_normalized)
      gradient_image = gradient_image.convert("L")
      gradient_image2 = gradient_image.resize((int(self.zoom_factor*gradient_image.width), int(self.zoom_factor*gradient_image.height)))
      
      # brightness and contrast
      brightness_enhancer = ImageEnhance.Brightness(gradient_image2)
      gradient_image3 = brightness_enhancer.enhance(self.brightness_factor)
      contrast_enhancer = ImageEnhance.Contrast(gradient_image3)
      gradient_image4 = contrast_enhancer.enhance(self.contrast_factor)

      gradient_qimage = ImageQt(gradient_image4)
      gradient_qimage.transformed(spacing_matrix)
      gradient_qpixmap = QtGui.QPixmap.fromImage(gradient_qimage)  

      self.button.setIcon(QIcon(gradient_qpixmap))
      self.button.setIconSize(gradient_qpixmap.size())
      self.images_layout.addWidget(QLabel("DWI " + str(iter_gradients)), 2*(iter_gradients//self.columns), iter_gradients%self.columns, QtCore.Qt.AlignCenter)
      self.images_layout.addWidget(self.button, 2*(iter_gradients//self.columns)+1, iter_gradients%self.columns)
      self.button.clicked.connect(partial(self.ButtonClicked, dwi=iter_gradients)) 
      if iter_gradients in self.gradientsToExclude_list:
        self.button.setStyleSheet("background-color : red")
      else:
        self.button.setStyleSheet("background-color : black") 

  def ButtonClicked(self, dwi):
    if dwi not in self.gradientsToExclude_list:
      self.gradientsToExclude_list.append(dwi)
      self.dic[str(dwi)].setStyleSheet("background-color : red")
    else:
      self.gradientsToExclude_list.remove(dwi)
      self.dic[str(dwi)].setStyleSheet("background-color : black")

    self.gradientsToExclude_label.setText(str(self.gradientsToExclude_list))

  def ChangeView(self):
    self.RemoveImages()
    if self.axial.isChecked():
      self.slice_selector_spinbox.setMaximum(self.size[2])
      self.slice_selector_slidebar.setMaximum(self.size[2])
      if self.zslice >= self.size[2]:
        self.zslice = self.size[2]-1
        self.slice_selector_spinbox.setValue(self.zslice)
    if self.sagittal.isChecked():
      self.slice_selector_spinbox.setMaximum(self.size[0])
      self.slice_selector_slidebar.setMaximum(self.size[0])
      if self.zslice >= self.size[0]:
        self.zslice = self.size[0]-1
        self.slice_selector_spinbox.setValue(self.zslice)
    if self.coronal.isChecked():
      self.slice_selector_spinbox.setMaximum(self.size[1])
      self.slice_selector_slidebar.setMaximum(self.size[1])
      if self.zslice >= self.size[1]:
        self.zslice = self.size[1]-1
        self.slice_selector_spinbox.setValue(self.zslice)
    if ".nrrd" in self.image_name:
      self.CreateButtonsNRRD()
    else:
      self.CreateButtonsNIFTI()

  def ChangeSlice(self):
    self.RemoveImages()
    self.zslice = self.slice_selector_spinbox.value()
    if ".nrrd" in self.image_name:
      self.CreateButtonsNRRD()
    else:
      self.CreateButtonsNIFTI()
  
  def ChangeColumns(self):
    self.RemoveImages()
    self.columns = self.images_per_row.value()
    if ".nrrd" in self.image_name:
      self.CreateButtonsNRRD()
    else:
      self.CreateButtonsNIFTI()

  def ChangeZoom(self):
    self.RemoveImages()
    self.zoom_factor = self.zoom.value()
    if ".nrrd" in self.image_name:
      self.CreateButtonsNRRD()
    else:
      self.CreateButtonsNIFTI()

  def ChangeBrightness(self):
    self.RemoveImages()
    self.brightness_factor = round(self.brightness_slidebar.value()/50, 2)
    if ".nrrd" in self.image_name:
      self.CreateButtonsNRRD()
    else:
      self.CreateButtonsNIFTI()

  def ChangeContrast(self):
    self.RemoveImages()
    self.contrast_factor = round(self.contrast_slidebar.value()/50, 2)
    if ".nrrd" in self.image_name:
      self.CreateButtonsNRRD()
    else:
      self.CreateButtonsNIFTI()

  def RemoveImages(self):

    # remove everything from viewing window
    for i in reversed(range(self.images_layout.count())):
      widget_to_remove = self.images_layout.itemAt(i).widget()
      self.images_layout.removeWidget(widget_to_remove) #remove from layout list
      widget_to_remove.setParent(None) #remove from GUI

    self.zslice = self.slice_selector_spinbox.value()

    if self.axial.isChecked():
      self.slice_selector_spinbox.setMaximum(self.size[2])
      self.slice_selector_slidebar.setMaximum(self.size[2])
      if self.zslice >= self.size[2]:
        self.zslice = self.size[2]-1
        self.slice_selector_spinbox.setValue(self.zslice)
    if self.sagittal.isChecked():
      self.slice_selector_spinbox.setMaximum(self.size[0])
      self.slice_selector_slidebar.setMaximum(self.size[0])
      if self.zslice >= self.size[0]:
        self.zslice = self.size[0]-1
        self.slice_selector_spinbox.setValue(self.zslice)
    if self.coronal.isChecked():
      self.slice_selector_spinbox.setMaximum(self.size[1])
      self.slice_selector_slidebar.setMaximum(self.size[1])
      if self.zslice >= self.size[1]:
        self.zslice = self.size[1]-1
        self.slice_selector_spinbox.setValue(self.zslice)

    self.columns = self.images_per_row.value()

    self.zoom_factor = self.zoom.value()
    
    if ".nrrd" in self.image_name:
      self.CreateButtonsNRRD()
    else:
      self.CreateButtonsNIFTI()

  def ComputeExcludeGradients(self):
    self.signal_quickview.Execution(self.gradientsToExclude_list)
    
    self.close()


    
  
