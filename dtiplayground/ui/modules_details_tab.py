from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui
from pathlib import Path
import yaml
from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSignal as Signal

from dtiplayground.ui.modules_details.baselineaverage import BaselineAverage
from dtiplayground.ui.modules_details.brainmask import BrainMask
from dtiplayground.ui.modules_details.braintractography import BrainTractography
from dtiplayground.ui.modules_details.dtiestimate import DTIEstimate
from dtiplayground.ui.modules_details.dtiregister import DTIRegister
from dtiplayground.ui.modules_details.eddymotion import EddyMotion
from dtiplayground.ui.modules_details.exclude import ExcludeGradients
from dtiplayground.ui.modules_details.interlacecheck import InterlaceCheck
from dtiplayground.ui.modules_details.nomodule import NoModule
from dtiplayground.ui.modules_details.qcreport import QCReport
from dtiplayground.ui.modules_details.singletract import Singletract
from dtiplayground.ui.modules_details.slicecheck import SliceCheck
from dtiplayground.ui.modules_details.susceptibility import SusceptibilityCorrection
from dtiplayground.ui.modules_details.utilheader import UtilHeader
from dtiplayground.ui.modules_details.utilmerge import UtilMerge



class DetailsDisplayCommunicate(QObject):

  set_modules_details_tab = Signal()
  set_update_module_details = Signal(bool)
  call_OrderModulesInProtocolList = Signal()
  get_selected_item_data = Signal(list)
  get_dic_protocol_selected_item = Signal(list)

  def __init__(self):
    super(DetailsDisplayCommunicate, self).__init__()

  def ChangeTab(self):
    self.set_modules_details_tab.emit()

  def SetUpdateModuleDetailsBool(self, new_update_module_details):
    self.set_update_module_details.emit(new_update_module_details)

  def CallOrderModulesInProtocolList(self):
    self.call_OrderModulesInProtocolList.emit()

  def SendSelectedItemData(self, data):
    self.get_selected_item_data.emit(data)

  def SendDicProtocolSelectedItem(self, module):
    self.get_dic_protocol_selected_item.emit(module)

class ModuleDetails(QWidget):
  communicate = DetailsDisplayCommunicate()

  def __init__(self, protocol_template, preferences_yml):
    QWidget.__init__(self)
    self.protocol_template = protocol_template
    self.tab = QWidget()
    self.LoadModulesYMLFiles()
    self.ModuleDetails(protocol_template, preferences_yml)
    self.communicate.get_dic_protocol_selected_item.connect(self.DetailsDisplay)

     
  def ModuleDetails(self, protocol_template, preferences_yml):
    # instanciation of module classes
    self.baselineaverage = BaselineAverage(protocol_template, self.baselineaverage_yml)
    self.brainmask = BrainMask(protocol_template, self.brainmask_yml)
    self.braintractography = BrainTractography(protocol_template, self.braintractography_yml)
    self.dtiestimate = DTIEstimate(protocol_template, self.dtiestimate_yml)
    self.dtiregister = DTIRegister(protocol_template, self.dtiregister_yml)
    self.eddymotion = EddyMotion(protocol_template, self.eddymotion_yml)
    self.exclude = ExcludeGradients(protocol_template, self.exclude_yml)
    self.interlacecheck = InterlaceCheck(protocol_template, self.interlacecheck_yml)
    self.no_module = NoModule()
    self.qcreport = QCReport(protocol_template, self.qcreport_yml)
    self.singletract = Singletract(protocol_template, self.singletract_yml)
    self.slicecheck = SliceCheck(protocol_template, self.slicecheck_yml)
    self.susceptibility = SusceptibilityCorrection(protocol_template, self.susceptibility_yml, preferences_yml)
    self.utilheader = UtilHeader(protocol_template, self.utilheader_yml)    
    self.utilmerge = UtilMerge(protocol_template, self.utilmerge_yml)

    # add modules to stack
    self.details_stack = QStackedWidget()
    self.details_stack.addWidget(self.no_module.stack)
    self.details_stack.addWidget(self.slicecheck.stack)
    self.details_stack.addWidget(self.interlacecheck.stack)    
    self.details_stack.addWidget(self.baselineaverage.stack)    
    self.details_stack.addWidget(self.susceptibility.stack)
    self.details_stack.addWidget(self.eddymotion.stack)
    self.details_stack.addWidget(self.brainmask.stack)
    self.details_stack.addWidget(self.dtiestimate.stack)
    self.details_stack.addWidget(self.exclude.stack)
    self.details_stack.addWidget(self.utilheader.stack)
    self.details_stack.addWidget(self.utilmerge.stack)
    self.details_stack.addWidget(self.qcreport.stack)
    self.details_stack.addWidget(self.dtiregister.stack)
    self.details_stack.addWidget(self.singletract.stack)
    self.details_stack.addWidget(self.braintractography.stack)

    # layout
    layout_v = QVBoxLayout()
    layout_v.addWidget(self.details_stack)
    self.tab.setLayout(layout_v)

  def ModuleDetailsClicked(self, index_tab):
    if index_tab == 1:
      self.details_stack.setCurrentIndex(0)

  def LoadModulesYMLFiles(self):
    import dtiplayground.dmri.preprocessing.modules
    module_dir = Path(dtiplayground.dmri.preprocessing.modules.__file__).parent

    filepath = module_dir.joinpath("SLICE_Check/SLICE_Check.yml")
    self.slicecheck_yml = yaml.safe_load(open(filepath,'r'))

    filepath = module_dir.joinpath("INTERLACE_Check/INTERLACE_Check.yml")
    self.interlacecheck_yml = yaml.safe_load(open(filepath,'r'))

    filepath = module_dir.joinpath("BASELINE_Average/BASELINE_Average.yml")
    self.baselineaverage_yml = yaml.safe_load(open(filepath,'r'))

    filepath = module_dir.joinpath("SUSCEPTIBILITY_Correct/SUSCEPTIBILITY_Correct.yml")
    self.susceptibility_yml = yaml.safe_load(open(filepath,'r'))

    filepath = module_dir.joinpath("EDDYMOTION_Correct/EDDYMOTION_Correct.yml")
    self.eddymotion_yml = yaml.safe_load(open(filepath,'r'))

    filepath = module_dir.joinpath("BRAIN_Mask/BRAIN_Mask.yml")
    self.brainmask_yml = yaml.safe_load(open(filepath,'r'))

    filepath = module_dir.joinpath("DTI_Estimate/DTI_Estimate.yml")
    self.dtiestimate_yml = yaml.safe_load(open(filepath,'r'))

    filepath = module_dir.joinpath("MANUAL_Exclude/MANUAL_Exclude.yml")
    self.exclude_yml = yaml.safe_load(open(filepath,'r'))

    filepath = module_dir.joinpath("UTIL_Header/UTIL_Header.yml")
    self.utilheader_yml = yaml.safe_load(open(filepath, 'r'))

    filepath = module_dir.joinpath("UTIL_Merge/UTIL_Merge.yml")
    self.utilmerge_yml = yaml.safe_load(open(filepath, 'r'))

    filepath = module_dir.joinpath("QC_Report/QC_Report.yml")
    self.qcreport_yml = yaml.safe_load(open(filepath, 'r'))

    filepath = module_dir.joinpath("DTI_Register/DTI_Register.yml")
    self.dtiregister_yml = yaml.safe_load(open(filepath, 'r'))

    filepath = module_dir.joinpath("SINGLETRACT_Process/SINGLETRACT_Process.yml")
    self.singletract_yml = yaml.safe_load(open(filepath, 'r'))

    filepath = module_dir.joinpath("BRAIN_Tractography/BRAIN_Tractography.yml")
    self.braintractography_yml = yaml.safe_load(open(filepath, 'r'))

    self.modules_yml_list = [self.slicecheck_yml, self.interlacecheck_yml, self.baselineaverage_yml,
      self.susceptibility_yml, self.eddymotion_yml, self.brainmask_yml, self.dtiestimate_yml, self.exclude_yml,
      self.utilheader_yml, self.utilmerge_yml, self.qcreport_yml, self.dtiregister_yml, self.singletract_yml,
      self.braintractography_yml]

  def DetailsDisplay(self, data):
    module = data[0]
    index = data[1]

    self.communicate.ChangeTab() #select details tab
    
    self.communicate.SetUpdateModuleDetailsBool(False)
    self.communicate.CallOrderModulesInProtocolList()

    if module[0] == "Slicewise Check":
      self.slicecheck.tab_name.setText(str(index) + " - " + module[0])
      if module[2]["options"]["overwrite"] == True:
        self.slicecheck.overwrite.setChecked(True)
      else:
        self.slicecheck.overwrite.setChecked(False)
      if module[2]["options"]["skip"] == True:
        self.slicecheck.skip.setChecked(True)
      else:
        self.slicecheck.skip.setChecked(False)
      if module[2]["options"]["write_image"] == True:
        self.slicecheck.writeimage.setChecked(True)
      else:
        self.slicecheck.writeimage.setChecked(False)
      if module[2]["protocol"]["bSubregionalCheck"] == True:
        self.slicecheck.bSubregionalCheck_true.setChecked(True)
      else:
        self.slicecheck.bSubregionalCheck_false.setChecked(True)
      self.slicecheck.subregionalCheckRelaxationFactor.setValue(module[2]["protocol"]["subregionalCheckRelaxationFactor"])
      self.slicecheck.checkTimes.setValue(module[2]["protocol"]["checkTimes"])
      self.slicecheck.headSkipSlicePercentage.setValue(module[2]["protocol"]["headSkipSlicePercentage"])
      self.slicecheck.tailSkipSlicePercentage.setValue(module[2]["protocol"]["tailSkipSlicePercentage"])
      self.slicecheck.correlationDeviationThresholdbaseline.setValue(module[2]["protocol"]["correlationDeviationThresholdbaseline"])
      self.slicecheck.correlationDeviationThresholdgradient.setValue(module[2]["protocol"]["correlationDeviationThresholdgradient"])
      if module[2]["protocol"]["quadFit"] == True:
        self.slicecheck.quadFit_true.setChecked(True)
      else:
        self.slicecheck.quadFit_false.setChecked(True)
      self.details_stack.setCurrentIndex(1)

    if module[0] == "Interlace Correlation Check":
      self.interlacecheck.tab_name.setText(str(index) + " - " + module[0])
      if module[2]["options"]["overwrite"] == True:
        self.interlacecheck.overwrite.setChecked(True)
      else:
        self.interlacecheck.overwrite.setChecked(False)
      if module[2]["options"]["skip"] == True:
        self.interlacecheck.skip.setChecked(True)
      else:
        self.interlacecheck.skip.setChecked(False)
      if module[2]["options"]["write_image"] == True:
        self.interlacecheck.writeimage.setChecked(True)
      else:
        self.interlacecheck.writeimage.setChecked(False)
      self.interlacecheck.correlationThresholdBaseline.setValue(module[2]["protocol"]["correlationThresholdBaseline"])
      self.interlacecheck.correlationThresholdGradient.setValue(module[2]["protocol"]["correlationThresholdGradient"])
      self.interlacecheck.correlationDeviationBaseline.setValue(module[2]["protocol"]["correlationDeviationBaseline"])
      self.interlacecheck.correlationDeviationGradient.setValue(module[2]["protocol"]["correlationDeviationGradient"])
      self.interlacecheck.translationThreshold.setValue(module[2]["protocol"]["translationThreshold"])
      self.interlacecheck.rotationThreshold.setValue(module[2]["protocol"]["rotationThreshold"])
      self.details_stack.setCurrentIndex(2)

    if module[0] == "Baseline Average":
      self.baselineaverage.tab_name.setText(str(index) + " - " + module[0])
      if module[2]["options"]["overwrite"] == True:
        self.baselineaverage.overwrite.setChecked(True)
      else:
        self.baselineaverage.overwrite.setChecked(False)
      if module[2]["options"]["skip"] == True:
        self.baselineaverage.skip.setChecked(True)
      else:
        self.baselineaverage.skip.setChecked(False)
      if module[2]["options"]["write_image"] == True:
        self.baselineaverage.writeimage.setChecked(True)
      else:
        self.baselineaverage.writeimage.setChecked(False)
      method = module[2]["protocol"]["averageMethod"]
      for ite1 in self.baselineaverage_yml["protocol"]["averageMethod"]["candidates"]:
        if ite1["value"] == method:
          self.baselineaverage.averageMethod.setCurrentText(ite1["caption"])
          self.baselineaverage.GetAvgMethodIt(ite1["caption"])
      method = module[2]["protocol"]["averageInterpolationMethod"]
      for ite1 in self.baselineaverage_yml["protocol"]["averageInterpolationMethod"]["candidates"]:
        if ite1["value"] == method:
          self.baselineaverage.averageInterpolationMethod.setCurrentText(ite1["caption"])
          self.baselineaverage.GetAvgInterpolMethodIt(ite1["caption"])
      self.baselineaverage.stopThreshold.setValue(module[2]["protocol"]["stopThreshold"])
      self.baselineaverage.maxIterations.setValue(module[2]["protocol"]["maxIterations"])
      self.baselineaverage.outputDWIFileNameSuffix.setText(module[2]["protocol"]["outputDWIFileNameSuffix"])
      self.details_stack.setCurrentIndex(3)

    if module[0] == "Susceptibility correction":
      self.susceptibility.tab_name.setText(str(index) + " - " + module[0])
      if module[2]["options"]["overwrite"] == True:
        self.susceptibility.overwrite.setChecked(True)
      else:
        self.susceptibility.overwrite.setChecked(False)
      if module[2]["options"]["skip"] == True:
        self.susceptibility.skip.setChecked(True)
      else:
        self.susceptibility.skip.setChecked(False)
      if module[2]["options"]["write_image"] == True:
        self.susceptibility.writeimage.setChecked(True)
      else:
        self.susceptibility.writeimage.setChecked(False)
      for ite1 in module[2]["protocol"]["phaseEncodingAxis"]:
        if ite1 == 0:
          self.susceptibility.phaseEncodingAxis_p0.setChecked(True)
        if ite1 == 1:
          self.susceptibility.phaseEncodingAxis_p1.setChecked(True)
        if ite1 == 2:
          self.susceptibility.phaseEncodingAxis_p2.setChecked(True)
      self.susceptibility.phaseEncodingValue.setValue(module[2]["protocol"]["phaseEncodingValue"])
      self.susceptibility.configurationFilePath.setText(module[2]["protocol"]["configurationFilePath"])
      self.details_stack.setCurrentIndex(4)

    if module[0] == "Eddy motion Correction":
      self.eddymotion.tab_name.setText(str(index) + " - " + module[0])
      if module[2]["options"]["overwrite"] == True:
        self.eddymotion.overwrite.setChecked(True)
      else:
        self.eddymotion.overwrite.setChecked(False)
      if module[2]["options"]["skip"] == True:
        self.eddymotion.skip.setChecked(True)
      else:
        self.eddymotion.skip.setChecked(False)
      if module[2]["options"]["write_image"] == True:
        self.eddymotion.writeimage.setChecked(True)
      else:
        self.eddymotion.writeimage.setChecked(False)
      if module[2]["protocol"]["estimateMoveBySusceptibility"] == True:
        self.eddymotion.estimateMoveBySusceptibility_true.setChecked(True)
      else:
        self.eddymotion.estimateMoveBySusceptibility_false.setChecked(True)
      if module[2]["protocol"]["interpolateBadData"] == True:
        self.eddymotion.interpolateBadData_true.setChecked(True)
      else:
        self.eddymotion.interpolateBadData_false.setChecked(True)
      if module[2]["protocol"]["dataIsShelled"] == True:
        self.eddymotion.dataIsShelled_true.setChecked(True)
      else:
        self.eddymotion.dataIsShelled_false.setChecked(True)
      if module[2]["protocol"]["qcReport"] == True:
        self.eddymotion.qcReport_true.setChecked(True)
      else:
        self.eddymotion.qcReport_false.setChecked(True)
      self.details_stack.setCurrentIndex(5)

    if module[0] == "Brain Masking":
      self.brainmask.tab_name.setText(str(index) + " - " + module[0])
      if module[2]["options"]["overwrite"] == True:
        self.brainmask.overwrite.setChecked(True)
      else:
        self.brainmask.overwrite.setChecked(False)
      if module[2]["options"]["skip"] == True:
        self.brainmask.skip.setChecked(True)
      else:
        self.brainmask.skip.setChecked(False)
      method = module[2]["protocol"]["method"]
      for ite1 in self.brainmask_yml["protocol"]["method"]["candidates"]:
        if ite1["value"] == method:
          self.brainmask.method.setCurrentText(ite1["caption"])
          self.brainmask.GetMethodIt(ite1["caption"])
      averagingmethod = module[2]["protocol"]["averagingMethod"]
      for ite1 in self.brainmask_yml["protocol"]["averagingMethod"]["candidates"]:
        if ite1["value"] == averagingmethod:
          self.brainmask.averagingmethod.setCurrentText(ite1["caption"])
          self.brainmask.GetAveragingMethodIt(ite1["caption"])
      #if module[2]["protocol"]["modality"] == "t2":
      #  self.brainmask.modality_t2.setChecked(True)
      #if module[2]["protocol"]["modality"] == "fa":
      #  self.brainmask.modality_fa.setChecked(True)
      self.details_stack.setCurrentIndex(6)

    if module[0] == "Estimate DTI":
      self.dtiestimate.tab_name.setText(str(index) + " - " + module[0])
      if module[2]["options"]["overwrite"] == True:
        self.dtiestimate.overwrite.setChecked(True)
      else:
        self.dtiestimate.overwrite.setChecked(False)
      if module[2]["options"]["skip"] == True:
        self.dtiestimate.skip.setChecked(True)
      else:
        self.dtiestimate.skip.setChecked(False)
      if module[2]["options"]["write_image"] == True:
        self.dtiestimate.writeimage.setChecked(True)
      else:
        self.dtiestimate.writeimage.setChecked(False)
      method = module[2]["protocol"]["correctionMethod"]
      for ite1 in self.dtiestimate_yml["protocol"]["correctionMethod"]["candidates"]:
        if ite1["value"] == method:
          self.dtiestimate.correctionMethod.setCurrentText(ite1["caption"])
          self.dtiestimate.GetCorrectionMethodIt(ite1["caption"])
      method = module[2]["protocol"]["method"]
      for ite1 in self.dtiestimate_yml["protocol"]["method"]["candidates"]:
        if ite1["value"] == method:
          self.dtiestimate.method.setCurrentText(ite1["caption"])
          self.dtiestimate.GetMethodIt(ite1["caption"])
      method = module[2]["protocol"]["optimizationMethod"]
      for ite1 in self.dtiestimate_yml["protocol"]["optimizationMethod"]["candidates"]:
        if ite1["value"] == method:
          self.dtiestimate.optimizationMethod.setCurrentText(ite1["caption"])
          self.dtiestimate.GetOptimizationMethodIt(ite1["caption"])
      self.details_stack.setCurrentIndex(7)

    if module[0] == "Exclude Gradients":
      self.exclude.tab_name.setText(str(index) + " - " + module[0])
      if module[2]["options"]["overwrite"] == True:
        self.exclude.overwrite.setChecked(True)
      else:
        self.exclude.overwrite.setChecked(False)
      if module[2]["options"]["skip"] == True:
        self.exclude.skip.setChecked(True)
      else:
        self.exclude.skip.setChecked(False)
      if module[2]["options"]["write_image"] == True:
        self.exclude.writeimage.setChecked(True)
      else:
        self.exclude.writeimage.setChecked(False)
      gradients_list = module[2]["protocol"]["gradientsToExclude"]
      gradients_string = ", ".join(str(gradient) for gradient in gradients_list)
      self.exclude.gradients2exclude.insertPlainText(gradients_string)
      self.details_stack.setCurrentIndex(8)

    if module[0] == "View Header":
      self.utilheader.tab_name.setText(str(index) + " - " + module[0])
      if module[2]["options"]["overwrite"] == True:
        self.utilheader.overwrite.setChecked(True)
      else:
        self.utilheader.overwrite.setChecked(False)
      if module[2]["options"]["skip"] == True:
        self.utilheader.skip.setChecked(True)
      else:
        self.utilheader.skip.setChecked(False)
      if module[2]["options"]["write_image"] == True:
        self.utilheader.writeimage.setChecked(True)
      else:
        self.utilheader.writeimage.setChecked(False)
      self.utilheader.options.setText(module[2]["protocol"]["options"])
      self.details_stack.setCurrentIndex(9)

    if module[0] == "Merge Images":
      self.utilmerge.tab_name.setText(str(index) + " - " + module[0])
      if module[2]["options"]["overwrite"] == True:
        self.utilmerge.overwrite.setChecked(True)
      else:
        self.utilmerge.overwrite.setChecked(False)
      if module[2]["options"]["skip"] == True:
        self.utilmerge.skip.setChecked(True)
      else:
        self.utilmerge.skip.setChecked(False)
      if module[2]["options"]["write_image"] == True:
        self.utilmerge.writeimage.setChecked(True)
      else:
        self.utilmerge.writeimage.setChecked(False)
      self.utilmerge.testparam.setText(module[2]["protocol"]["TestParam"])
      self.details_stack.setCurrentIndex(10)

    if module[0] == "QC Report":
      self.qcreport.tab_name.setText(str(index) + " - " + module[0])
      if module[2]["options"]["overwrite"] == True:
        self.qcreport.overwrite.setChecked(True)
      else:
        self.qcreport.overwrite.setChecked(False)
      if module[2]["options"]["skip"] == True:
        self.qcreport.skip.setChecked(True)
      else:
        self.qcreport.skip.setChecked(False)
      if module[2]["protocol"]["generatePDF"] == True:
        self.qcreport.generatePDF_true.setChecked(True)
      else: 
        self.qcreport.generatePDF_false.setChecked(True)
      if module[2]["protocol"]["generateCSV"] == True:
        self.qcreport.generateCSV_true.setChecked(True)
      else:
        self.qcreport.generateCSV_false.setChecked(False)
      self.details_stack.setCurrentIndex(11)

    if module[0] == "Register DTI (ANTs)":
      self.dtiregister.tab_name.setText(str(index) + " - " + module[0])
      if module[2]["options"]["overwrite"] == True:
        self.dtiregister.overwrite.setChecked(True)
      else:
        self.dtiregister.overwrite.setChecked(False)
      if module[2]["options"]["skip"] == True:
        self.dtiregister.skip.setChecked(True)
      else:
        self.dtiregister.skip.setChecked(False)
      if module[2]["options"]["write_image"] == True:
        self.dtiregister.writeimage.setChecked(True)
      else:
        self.dtiregister.writeimage.setChecked(False)
      method = module[2]["protocol"]["method"]
      for ite1 in self.dtiregister_yml["protocol"]["method"]["candidates"]:
        if ite1["value"] == method:
          self.dtiregister.method.setCurrentText(ite1["caption"])
          self.dtiregister.GetMethodIt(ite1["caption"])
      self.dtiregister.referenceImage.setText(module[2]['protocol']['referenceImage'])
      self.dtiregister.ANTsPath.setText(module[2]['protocol']['ANTsPath'])
      self.dtiregister.ANTsMethod.setText(module[2]['protocol']['ANTsMethod'])
      registrationType = module[2]["protocol"]["registrationType"]
      for ite1 in self.dtiregister_yml["protocol"]["registrationType"]["candidates"]:
        if ite1["value"] == registrationType:
          self.dtiregister.registrationType.setCurrentText(ite1["caption"])
          self.dtiregister.GetRegistrationTypeIt(ite1["caption"])
      similarityMetric = module[2]["protocol"]["similarityMetric"]
      for ite1 in self.dtiregister_yml["protocol"]["similarityMetric"]["candidates"]:
        if ite1["value"] == similarityMetric:
          self.dtiregister.similarityMetric.setCurrentText(ite1["caption"])
          self.dtiregister.GetSimilarityMetricIt(ite1["caption"])      
      self.dtiregister.similarityParameter.setValue(module[2]["protocol"]["similarityParameter"])
      self.dtiregister.ANTsIterations.setText(module[2]['protocol']['ANTsIterations'])
      self.dtiregister.gaussianSigma.setValue(module[2]["protocol"]["gaussianSigma"])
      self.details_stack.setCurrentIndex(12)

    if module[0] == "SINGLETRACT_Process DTI":
      self.singletract.tab_name.setText(str(index) + " - " + module[0])
      if module[2]["options"]["overwrite"] == True:
        self.singletract.overwrite.setChecked(True)
      else:
        self.singletract.overwrite.setChecked(False)
      if module[2]["options"]["skip"] == True:
        self.singletract.skip.setChecked(True)
      else:
        self.singletract.skip.setChecked(False)
      if module[2]["options"]["write_image"] == True:
        self.singletract.writeimage.setChecked(True)
      else:
        self.singletract.writeimage.setChecked(False)
      method = module[2]["protocol"]["method"]
      for ite1 in self.singletract_yml["protocol"]["method"]["candidates"]:
        if ite1["value"] == method:
          self.singletract.method.setCurrentText(ite1["caption"])
          self.singletract.GetMethodIt(ite1["caption"])
      scalar = module[2]["protocol"]["scalar"]
      for ite1 in self.singletract_yml["protocol"]["scalar"]["candidates"]:
        if ite1["value"] == scalar:
          self.singletract.scalar.setCurrentText(ite1["caption"])
          self.singletract.GetScalarIt(ite1["caption"])
      self.singletract.NIRALUtilitiesPath.setText(module[2]['protocol']['NIRALUtilitiesPath'])
      self.singletract.referenceTractFile.setText(module[2]['protocol']['referenceTractFile'])
      self.singletract.dilationRadius.setValue(module[2]['protocol']['dilationRadius'])
      self.details_stack.setCurrentIndex(13)
    
    if module[0] == "Brain Tractography":
      self.singletract.tab_name.setText(str(index) + " - " + module[0])
      if module[2]["options"]["overwrite"] == True:
        self.braintractography.overwrite.setChecked(True)
      else:
        self.braintractography.overwrite.setChecked(False)
      if module[2]["options"]["skip"] == True:
        self.braintractography.skip.setChecked(True)
      else:
        self.braintractography.skip.setChecked(False)
      whiteMatterMaskThreshold = module[2]["protocol"]["whiteMatterMaskThreshold"]
      for ite1 in self.braintractography_yml["protocol"]["whiteMatterMaskThreshold"]["candidates"]:
        if ite1["value"] == whiteMatterMaskThreshold:
          self.braintractography.whiteMatterMaskThreshold.setCurrentText(ite1["caption"])
          self.braintractography.GetWhiteMatterMaskThresholdIt(ite1["caption"])
      self.braintractography.thresholdLow.setValue(module[2]['protocol']['thresholdLow'])
      self.braintractography.thresholdUp.setValue(module[2]['protocol']['thresholdUp'])
      method = module[2]["protocol"]["method"]
      for ite1 in self.braintractography_yml["protocol"]["method"]["candidates"]:
        if ite1["value"] == method:
          self.braintractography.method.setCurrentText(ite1["caption"])
          self.braintractography.GetMethodIt(ite1["caption"])
      self.braintractography.shOrder.setValue(module[2]['protocol']['shOrder'])
      self.braintractography.relativePeakThreshold.setValue(module[2]['protocol']['relativePeakThreshold'])
      self.braintractography.minPeakSeparationAngle.setValue(module[2]['protocol']['minPeakSeparationAngle'])
      self.braintractography.stoppingCriterionThreshold.setValue(module[2]['protocol']['stoppingCriterionThreshold'])
      if module[2]["protocol"]["vtk42"] == True:
        self.braintractography.vtk42_true.setChecked(True)
      else:
        self.braintractography.vtk42_false.setChecked(True)
      if module[2]["protocol"]["removeShortTracts"] == True:
        self.braintractography.removeShortTracts.setChecked(True)
      else:
        self.braintractography.removeShortTracts.setChecked(False)
      self.braintractography.shortTractsThreshold.setValue(module[2]['protocol']['shortTractsThreshold'])
      if module[2]["protocol"]["removeLongTracts"] == True:
        self.braintractography.removeLongTracts.setChecked(True)
      else:
        self.braintractography.removeLongTracts.setChecked(False)
      self.braintractography.longTractsThreshold.setValue(module[2]['protocol']['longTractsThreshold'])
      self.details_stack.setCurrentIndex(14)

    self.communicate.SetUpdateModuleDetailsBool(True)


