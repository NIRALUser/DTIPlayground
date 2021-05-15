#!/usr/bin/python

#
#   atlas.py 
#   2021-05-10
#   Written by SK Park, NIRAL, UNC
#
#   Atlasbuilding scripts
#

import os # To run a shell command : os.system("[shell command]") >> will
import sys # to return an exit code
import shutil # to remove a non empty directory and copy files
import time 
import xml.etree.cElementTree as ET 

import dmri.atlasbuilder as ab 
import dmri.common.tools as tools

logger=ab.logger.write

def generateGreedyAtlasParametersFile(cfg):
    xmlfile=cfg["m_GreedyAtlasParametersTemplatePath"]
    x=ET.parse(xmlfile)
    r=x.getroot()

    ## remove all dummy dataset files
    wis=r.find('WeightedImageSet')
    wi_list=wis.findall('WeightedImage')
    for w in wi_list:
        wis.remove(w)

    ## insert new dataset
    for cid in cfg["m_CasesIDs"]:
        wi=ET.Element('WeightedImage',{})
        lastLoop=str(cfg['m_nbLoops'])
        p=os.path.join(cfg['m_OutputPath'],"1_Affine_Registration/Loop"+lastLoop+"/"+cid+"_Loop"+lastLoop+"_Final"+cfg["m_ScalarMeasurement"]+".nrrd")
        wiFilename=ET.Element('Filename',{'val':str(p)})
        wiItkTransform=ET.Element('ItkTransform',{'val':'1'})
        wi.insert(0,wiFilename)
        wi.insert(1,wiItkTransform)
        wis.insert(-1,wi)  ## insert to the last

    ## change output path 
    for neighbor in r.iter('OutputPrefix'):
        logger("{} {}".format(neighbor.tag,neighbor.attrib))
        neighbor.set('val',cfg["m_OutputPath"]+"/2_NonLinear_Registration/")

    outputfile=cfg["m_OutputPath"]+"/2_NonLinear_Registration/GreedyAtlasParameters.xml"
    x.write(outputfile)

def DisplayErrorAndQuit ( Error ):
    msg='\n\nERROR DETECTED IN WORKFLOW:'+Error
    logger(msg)
    logger('ABORT')
    raise Exception(msg)


# Function that checks if file exist and replace old names by new names if needed
def CheckFileExists ( File, case, caseID ) : # returns 1 if file exists or has been renamed and 0 if not
    if os.path.isfile( File ) : # file exists
      return 1
    else : # file does not exist: check if older version of file can exist (if file name has been changed)
      NamesThatHaveChanged = ["MeanImage", "DiffeomorphicDTI", "DiffeomorphicAtlasDTI", "HField", "GlobalDisplacementField"] # latest versions of the names
      if any( changedname in File for changedname in NamesThatHaveChanged ) : # if name has been changed, check if older version files exist
        if "MeanImage" in File :
          OldFile = File.replace("Mean", "Average")
          if os.path.isfile( OldFile ) : # old file exists: rename and return 1
            os.rename(OldFile, File)
            return 1
          else:
            return 0
        if "DiffeomorphicDTI" in File :
          OldFile = File.replace( caseID, "Case" + str(case+1) ).replace("DiffeomorphicDTI", "AWDTI")
          if os.path.isfile( OldFile ) : # old file exists: rename and return 1
            os.rename(OldFile, File)
            os.rename(OldFile.replace("AWDTI","AW"+config['m_ScalarMeasurement']), File.replace("DiffeomorphicDTI","Diffeomorphic"+config['m_ScalarMeasurement']))
            os.rename(OldFile.replace("AWDTI","AWDTI_float"), File.replace("DiffeomorphicDTI","DiffeomorphicDTI_float"))
            return 1
          else : # test other old name
            OldFile = File.replace( caseID, "Case" + str(case+1) )
            if os.path.isfile( OldFile ) : # old file exists: rename and return 1
              os.rename(OldFile, File)
              os.rename(OldFile.replace("DiffeomorphicDTI","Diffeomorphic"+config['m_ScalarMeasurement']), File.replace("DiffeomorphicDTI","Diffeomorphic"+config['m_ScalarMeasurement']))
              os.rename(OldFile.replace("DiffeomorphicDTI","DiffeomorphicDTI_float"), File.replace("DiffeomorphicDTI","DiffeomorphicDTI_float"))
              return 1
            else:
              return 0
        if "DiffeomorphicAtlasDTI" in File :
          OldFile = File.replace("DiffeomorphicAtlasDTI", "AWAtlasDTI")
          if os.path.isfile( OldFile ) : # old file exists: rename and return 1
            os.rename(OldFile, File)
            os.rename(OldFile.replace("AWAtlasDTI","AWAtlas"+config['m_ScalarMeasurement']), File.replace("DiffeomorphicAtlasDTI","DiffeomorphicAtlas"+config['m_ScalarMeasurement']))
            os.rename(OldFile.replace("AWAtlasDTI","AWAtlasDTI_float"), File.replace("DiffeomorphicAtlasDTI","DiffeomorphicAtlasDTI_float"))
            return 1
          else:
            return 0
        if "HField" in File :
          OldFile = File.replace( caseID, "Case" + str(case+1) ).replace("H", "Deformation")
          if os.path.isfile( OldFile ) : # old file exists: rename and return 1
            os.rename(OldFile, File)
            return 1
          else : # test other old name
            OldFile = File.replace( caseID, "Case" + str(case+1) )
            if os.path.isfile( OldFile ) : # old file exists: rename and return 1
              os.rename(OldFile, File)
              return 1
            else:
              return 0
        if "GlobalDisplacementField" in File :
          OldFile = File.replace( caseID, "Case" + str(case+1) ).replace("Displacement", "Deformation")
          if os.path.isfile( OldFile ) : # old file exists: rename and return 1
            os.rename(OldFile, File)
            return 1
          else : # test other old name
            OldFile = File.replace( caseID, "Case" + str(case+1) )
            if os.path.isfile( OldFile ) : # old file exists: rename and return 1
              os.rename(OldFile, File)
              return 1
            else:
              return 0
      else: # file does not exist and name has not been changed: check if the caseX version exists
        if caseID : # CaseID is empty for averages
          OldFile = File.replace( caseID, "Case" + str(case+1) )
          if os.path.isfile( OldFile ) : # old file exists: rename and return 1
            os.rename(OldFile, File)
            return 1
          else:
            return 0
        else: # for averages
          return 0

def run(cfg):

    config=cfg
    PIDlogFile = config['m_OutputPath']+"/PID.log"
    PIDfile = open( PIDlogFile, 'a') # open in Append mode
    PIDfile.write( str(os.getpid()) + "\n" )
    PIDfile.close()

    m_OutputPath=config["m_OutputPath"]
    m_ScalarMeasurement=config["m_ScalarMeasurement"]
    m_GridAtlasCommand=config["m_GridAtlasCommand"]
    m_RegType=config["m_RegType"]
    m_Overwrite=config["m_Overwrite"]
    m_useGridProcess=config["m_useGridProcess"]
    m_SoftPath=config["m_SoftPath"]
    m_nbLoops=config["m_nbLoops"]
    m_TensTfm=config["m_TensTfm"]
    m_TemplatePath=config["m_TemplatePath"]
    m_BFAffineTfmMode=config["m_BFAffineTfmMode"]
    m_CasesIDs=config["m_CasesIDs"]
    m_CasesPath=config["m_CasesPath"]
    m_CropSize=config["m_CropSize"]
    m_DTIRegExtraPath=config["m_DTIRegExtraPath"]
    m_DTIRegOptions=config["m_DTIRegOptions"]
    m_GridAtlasCommand=config["m_GridAtlasCommand"]
    m_GridGeneralCommand=config["m_GridGeneralCommand"]
    m_InterpolLogOption=config["m_InterpolLogOption"]
    m_InterpolOption=config["m_InterpolOption"]
    m_InterpolType=config["m_InterpolType"]
    m_NbThreadsString=config["m_NbThreadsString"]
    m_NeedToBeCropped=config["m_NeedToBeCropped"]
    m_PythonPath=config["m_PythonPath"]
    m_TensInterpol=config["m_TensInterpol"]
    m_nbLoopsDTIReg=config["m_nbLoopsDTIReg"]

    ### To be removed
    if m_nbLoopsDTIReg is None: m_nbLoopsDTIReg=1

    logger("\n============ Atlas Building =============")

    # Files Paths
    DeformPath= m_OutputPath+"/2_NonLinear_Registration"
    AffinePath= m_OutputPath+"/1_Affine_Registration"
    FinalPath= m_OutputPath+"/3_Diffeomorphic_Atlas"
    FinalResampPath= m_OutputPath+"/4_Final_Resampling"
    FinalAtlasPath= m_OutputPath+"/5_Final_Atlas"



    def TestGridProcess ( FilesFolder, NbCases , NoCase1=None):
      if NoCase1 is not None:
        if NbCases>0 : logger("\n| Waiting for all batches (" + str(NbCases-NoCase1) + ") to be processed on grid...")
        else : logger("\n| Waiting for 1 batch to be processed on grid...")
        filesOK = 0
        OldNbFilesOK = 0
        while not filesOK :
          filesOK = 1
          if NbCases>0 :
            NbfilesOK = 0
            case = int(NoCase1) # NoCase1 is 0 or 1 (bool)
            while case < NbCases:
              if not os.path.isfile( FilesFolder + "/Case" + str(case+1) ) : filesOK = 0
              else : NbfilesOK = NbfilesOK + 1
              case += 1
            if NbfilesOK != OldNbFilesOK : logger("| [" + str(NbfilesOK) + "\t / " + str(NbCases-NoCase1) + " ] cases processed")
            OldNbFilesOK=NbfilesOK  
          elif not os.path.isfile( FilesFolder + "/file" ) : filesOK = 0
          time.sleep(60) # Test only every minute\n"
        logger("\n=> All files processed\n")
        shutil.rmtree(FilesFolder) # clear directory and recreate it\n"
        os.mkdir(FilesFolder)

      else:
        if NbCases>0 : logger("\n| Waiting for all batches (" + str(NbCases) + ") to be processed on grid...")
        else : logger("\n| Waiting for 1 batch to be processed on grid...")
        filesOK = 0
        OldNbFilesOK = 0
        while not filesOK :
          filesOK = 1
          if NbCases>0 :
            NbfilesOK = 0
            case = 0
            while case < NbCases:
              if not os.path.isfile( FilesFolder + "/Case" + str(case+1) ) : filesOK = 0
              else : NbfilesOK = NbfilesOK + 1
              case += 1

            if NbfilesOK != OldNbFilesOK : logger("| [" + str(NbfilesOK) + "\t / " + str(NbCases) + " ] cases processed")
            OldNbFilesOK=NbfilesOK
          elif not os.path.isfile( FilesFolder + "/file" ) : filesOK = 0
          time.sleep(60) # Test only every minute\n"
        logger("\n=> All files processed\n")
        shutil.rmtree(FilesFolder) # clear directory and recreate it\n"
        os.mkdir(FilesFolder)



    GridApostrophe=""
    GridProcessCmd=""
    GridProcessFileExistCmd1 = ""
    GridProcessCmdNoCase = ""
    GridProcessCmdAverage = ""
    GridProcessFileExistCmdNoCase = ""
    GridProcessFileExistIndent = ""
    GridProcessFileExistIndent1 = ""

    #<<<<<< CURRENT
    FilesFolder=""
    if config["m_useGridProcess"]:
      FilesFolder= m_OutputPath + '/GridProcessingFiles'
      GridApostrophe="'"
      File=FilesFolder + "/Case" + str(case+1)
      GridProcessCmd = m_GridGeneralCommand + " " + m_PythonPath + " " + m_OutputPath + "/Script/RunCommandOnServer.py " +  " " + File  + " " + GridApostrophe 
      
      GridProcessFileExistCmd1 = "    f = open( " + File + ", 'w')\n    f.close()\n" ### This is problematic 

      FileNoCase = FilesFolder + "/file"
      GridProcessCmdNoCase = m_GridGeneralCommand + " " + m_PythonPath + " " + m_OutputPath + "/Script/RunCommandOnServer.py " + " " + FileNoCase + " " + GridApostrophe 
      
      GridProcessFileExistCmdNoCase = "  f = open( " + FileNoCase + ", 'w')\n  f.close()\n" ### This is problematic 
      
      GridProcessCmdAverage = m_GridAtlasCommand + " " + m_PythonPath + " " + m_OutputPath + "/Script/RunCommandOnServer.py " + " " + FileNoCase + " "  + GridApostrophe 
      GridProcessFileExistIndent = "\n  "
      GridProcessFileExistIndent1 = "\n    "

    # Create directory for temporary files and final
    if not os.path.isdir(DeformPath):
      OldDeformPath= m_OutputPath + "/2_NonLinear_Registration_AW"
      if os.path.isdir(OldDeformPath):
        os.rename(OldDeformPath,DeformPath)
      else:
        logger("\n=> Creation of the Deformation transform directory = " + DeformPath)
        os.mkdir(DeformPath)

    if not os.path.isdir(FinalPath):
      OldFinalPath= m_OutputPath+"/3_AW_Atlas"
      if os.path.isdir(OldFinalPath):
        os.rename(OldFinalPath,FinalPath)
      else:
        logger("\n=> Creation of the Final Atlas directory = " + FinalPath)
        os.mkdir(FinalPath)

    if not os.path.isdir(FinalResampPath):
      logger("\n=> Creation of the Final Resampling directory = " + FinalResampPath)
      os.mkdir(FinalResampPath)

    if not os.path.isdir(FinalResampPath + "/First_Resampling"):
      logger("\n=> Creation of the First Final Resampling directory = " + FinalResampPath + "/First_Resampling")
      os.mkdir(FinalResampPath + "/First_Resampling")

    if not os.path.isdir(FinalResampPath + "/Second_Resampling"):
      logger("\n=> Creation of the Second Final Resampling directory = " + FinalResampPath + "/Second_Resampling")
      os.mkdir(FinalResampPath + "/Second_Resampling")

    if not os.path.isdir(FinalAtlasPath):
      logger("\n=> Creation of the Final Atlas directory = " + FinalAtlasPath)
      os.mkdir(FinalAtlasPath)

    # for i in range(m_nbLoopsDTIReg):
    #   if not os.path.isdir(FinalResampPath+"/Second_Resampling"+"/Loop_"+str(i)):
    #     logger("\n=> Creation of the Second Final Resampling loop directory  = " + FinalResampPath + "/Second_Resampling" +"/Loop_"+str(i))
    #     os.mkdir(FinalResampPath + "/Second_Resampling" + "/Loop_"+str(i))

    if not os.path.isdir(FinalResampPath + "/FinalTensors"):
      logger("\n=> Creation of the Final Tensors directory = " + FinalResampPath + "/FinalTensors")
      os.mkdir(FinalResampPath + "/FinalTensors")

    if not os.path.isdir(FinalResampPath + "/FinalDeformationFields"):
      logger("\n=> Creation of the Final Deformation Fields directory = " + FinalResampPath + "/FinalDeformationFields\n")
      os.mkdir(FinalResampPath + "/FinalDeformationFields")

    # Cases variables
    #alltfms = [AffinePath + "/Loop"+ m_nbLoops +"/ImageTest1_Loop1_LinearTrans.txt", AffinePath + "/Loop1/ImageTest2_Loop1_LinearTrans.txt", AffinePath + "/Loop1/ImageTest3_Loop1_LinearTrans.txt"]
    alltfms=[]
    for i,c in enumerate(m_CasesPath):
      alltfms.append(AffinePath+"/Loop"+str(m_nbLoops)+"/" +m_CasesIDs[i] + "_Loop" + str(m_nbLoops) +"_LinearTrans.txt")

    allcases=[]
    if m_NeedToBeCropped==1:
      for i,c in enumerate(m_CasesPath):
        allcases.append(AffinePath + "/" + m_CasesIDs[i] + "_croppedDTI.nrrd")
    else:
      for i,c in enumerate(m_CasesPath):
        allcases.append(m_CasesPath[i])
    #allcases = ["/work/dtiatlasbuilder/Data/Testing/ImageTest1.nrrd", "/work/dtiatlasbuilder/Data/Testing/ImageTest2.nrrd", "/work/dtiatlasbuilder/Data/Testing/ImageTest3.nrrd"]
    allcasesIDs=[]
    for i,c in enumerate(m_CasesIDs):
      allcasesIDs.append(m_CasesIDs[i])
    #allcasesIDs = ["ImageTest1", "ImageTest2", "ImageTest3"]


    #### <<<< CURRENT POSITION

    # GreedyAtlas Command
    generateGreedyAtlasParametersFile(config)
    XMLFile= DeformPath + "/GreedyAtlasParameters.xml"
    ParsedFile= DeformPath + "/ParsedXML.xml"
    AtlasBCommand= GridProcessCmdAverage + " "+ m_SoftPath[5] + " -f " + XMLFile + " -o " + ParsedFile + GridApostrophe
    logger("[Computing the Deformation Fields with GreedyAtlas] => $ " + AtlasBCommand)
    if m_Overwrite==1:
      if 1 :
        if os.system(AtlasBCommand)!=0 : DisplayErrorAndQuit('GreedyAtlas: Computing non-linear atlas from affine registered images')
        if m_useGridProcess:
          TestGridProcess( FilesFolder, 0) # stays in the function until all process is done : 0 makes the function look for 'file\'
        case = 0
        while case < len(allcases): # Renaming
          originalImage=DeformPath + "/" + allcasesIDs[case] + "_Loop"+str(m_nbLoops)+"_Final"+m_ScalarMeasurement+"DefToMean.mhd"
          originalHField=DeformPath + "/" + allcasesIDs[case] + "_Loop"+str(m_nbLoops)+"_Final"+m_ScalarMeasurement+"DefFieldImToMean.mhd"
          originalInvHField=DeformPath + "/" + allcasesIDs[case] + "_Loop"+str(m_nbLoops)+"_Final"+m_ScalarMeasurement+"DefFieldMeanToIm.mhd"
          NewImage= DeformPath + "/" + allcasesIDs[case] + "_NonLinearTrans_FA.mhd"
          NewHField=DeformPath + "/" + allcasesIDs[case] + "_HField.mhd"
          NewInvHField=DeformPath + "/" + allcasesIDs[case] + "_InverseHField.mhd"
          logger("[" + allcasesIDs[case] + "] => Renaming \'" + originalImage + "\' to \'" + NewImage + "\'")
          os.rename(originalImage,NewImage)
          logger("[" + allcasesIDs[case] + "] => Renaming \'" + originalHField + "\' to \'" + NewHField + "\'")
          os.rename(originalHField,NewHField)
          logger("[" + allcasesIDs[case] + "] => Renaming \'" + originalInvHField + "\' to \'" + NewInvHField + "\'")
          os.rename(originalInvHField,NewInvHField)
          case += 1
    else:
      if not CheckFileExists(DeformPath + "/MeanImage.mhd", 0, "") :
        if os.system(AtlasBCommand)!=0 : DisplayErrorAndQuit('GreedyAtlas: Computing non-linear atlas from affine registered images')
        if m_useGridProcess:
          TestGridProcess( FilesFolder, 0) # stays in the function until all process is done : 0 makes the function look for 'file\'
        case = 0
        while case < len(allcases): # Renaming
          originalImage=DeformPath + "/" + allcasesIDs[case] + "_Loop"+str(m_nbLoops)+"_Final"+m_ScalarMeasurement+"DefToMean.mhd"
          originalHField=DeformPath + "/" + allcasesIDs[case] + "_Loop"+str(m_nbLoops)+"_Final"+m_ScalarMeasurement+"DefFieldImToMean.mhd"
          originalInvHField=DeformPath + "/" + allcasesIDs[case] + "_Loop"+str(m_nbLoops)+"_Final"+m_ScalarMeasurement+"DefFieldMeanToIm.mhd"
          NewImage= DeformPath + "/" + allcasesIDs[case] + "_NonLinearTrans_FA.mhd"
          NewHField=DeformPath + "/" + allcasesIDs[case] + "_HField.mhd"
          NewInvHField=DeformPath + "/" + allcasesIDs[case] + "_InverseHField.mhd"
          logger("[" + allcasesIDs[case] + "] => Renaming \'" + originalImage + "\' to \'" + NewImage + "\'")
          os.rename(originalImage,NewImage)
          logger("[" + allcasesIDs[case] + "] => Renaming \'" + originalHField + "\' to \'" + NewHField + "\'")
          os.rename(originalHField,NewHField)
          logger("[" + allcasesIDs[case] + "] => Renaming \'" + originalInvHField + "\' to \'" + NewInvHField + "\'")
          os.rename(originalInvHField,NewInvHField)
          case += 1
      else:
        logger("=> The file '" + DeformPath + "/MeanImage.mhd' already exists so the command will not be executed")
        # Renaming possible existing old named files from GreedyAtlas\n";
        case = 0
        while case < len(allcases): # Updating old names if needed\n";
          NewImage= DeformPath + "/" + allcasesIDs[case] + "_NonLinearTrans_" + m_ScalarMeasurement + ".mhd"
          CheckFileExists(NewImage, case, allcasesIDs[case])
          NewHField=DeformPath + "/" + allcasesIDs[case] + "_HField.mhd"
          CheckFileExists(NewHField, case, allcasesIDs[case])
          NewInvHField=DeformPath + "/" + allcasesIDs[case] + "_InverseHField.mhd"
          CheckFileExists(NewInvHField, case, allcasesIDs[case])
          case += 1

    # Apply deformation fields 
    if m_useGridProcess:
      GridProcessCommandArray=[]
      NbGridCommandsRan=0
    case = 0
    while case < len(allcases):
      FinalDTI= FinalPath + "/" + allcasesIDs[case] + "_DiffeomorphicDTI.nrrd"
      if m_NeedToBeCropped==1:
        originalDTI= AffinePath + "/" + allcasesIDs[case] + "_croppedDTI.nrrd"
      else:
        originalDTI= allcases[case]
      if m_nbLoops==0:
        Ref = AffinePath + "/Loop0/Loop0_"+m_ScalarMeasurement+"Average.nrrd"
      else:
        Ref = AffinePath + "/Loop" + str(m_nbLoops-1) + "/Loop" + str(m_nbLoops-1) + "_" + m_ScalarMeasurement + "Average.nrrd"

      HField= DeformPath + "/" + allcasesIDs[case] + "_HField.mhd"
      FinalReSampCommand= m_SoftPath[1] +" -R " + Ref + " -H " + HField + " -f " + alltfms[case] + " " + originalDTI + " " + FinalDTI

      ### options
      if m_InterpolType=="Linear" : FinalReSampCommand = FinalReSampCommand + " -i linear"
      if m_InterpolType=="Nearest Neighborhood" : FinalReSampCommand = FinalReSampCommand + " -i nn"
      if m_InterpolType=="Windowed Sinc":
        if m_InterpolOption=="Hamming": FinalReSampCommand = FinalReSampCommand + " -i ws -W h"
        if m_InterpolOption=="Cosine" : FinalReSampCommand = FinalReSampCommand + " -i ws -W c"
        if m_InterpolOption=="Welch"  : FinalReSampCommand = FinalReSampCommand + " -i ws -W w"
        if m_InterpolOption=="Lanczos": FinalReSampCommand = FinalReSampCommand + " -i ws -W l"
        if m_InterpolOption=="Blackman":FinalReSampCommand = FinalReSampCommand + " -i ws -W b"
      if m_InterpolType=="BSpline":
        FinalReSampCommand = FinalReSampCommand + " -i bs -o " + m_InterpolOption + ""
      if m_TensInterpol=="Non Log Euclidean":
        if m_InterpolLogOption=="Zero" :  FinalReSampCommand = FinalReSampCommand + " --nolog --correction zero"
        if m_InterpolLogOption=="None" :  FinalReSampCommand = FinalReSampCommand + " --nolog --correction none"
        if m_InterpolLogOption=="Absolute Value" : FinalReSampCommand = FinalReSampCommand + " --nolog --correction abs"
        if m_InterpolLogOption=="Nearest" : FinalReSampCommand = FinalReSampCommand + " --nolog --correction nearest"
      if m_TensTfm=="Preservation of the Principal Direction (PPD)": FinalReSampCommand = FinalReSampCommand + " -T PPD"
      if m_TensTfm=="Finite Strain (FS)" : FinalReSampCommand = FinalReSampCommand + " -T FS"
      logger("\n[" + allcasesIDs[case] + "] [Applying deformation fields to original DTIs] => $ " + FinalReSampCommand)

      if m_Overwrite==1:
        if 1 :
          DiffeomorphicCaseScalarMeasurement = FinalPath + "/" + allcasesIDs[case] + "_Diffeomorphic"+m_ScalarMeasurement+".nrrd"
          if m_ScalarMeasurement=="FA":
            GeneDiffeomorphicCaseScalarMeasurementCommand=m_SoftPath[3]+" --scalar_float --dti_image " + FinalDTI + " -f " + DiffeomorphicCaseScalarMeasurement
          else:
            GeneDiffeomorphicCaseScalarMeasurementCommand=m_SoftPath[3]+" --scalar_float --dti_image " + FinalDTI + " -m " + DiffeomorphicCaseScalarMeasurement
          CaseDbleToFloatCommand=m_SoftPath[8] +" convert -t float -i " + FinalDTI + " | " + m_SoftPath[8] +" save -f nrrd -e gzip -o " + FinalPath + "/" + allcasesIDs[case] + "_DiffeomorphicDTI_float.nrrd"

          if not m_useGridProcess:
            if os.system(FinalReSampCommand)!=0 : DisplayErrorAndQuit('[' + allcasesIDs[case] + '] ResampleDTIlogEuclidean: Applying deformation fields to original DTIs')
            logger("[" + allcasesIDs[case] + "] => $ " + GeneDiffeomorphicCaseScalarMeasurementCommand)
            if os.system(GeneDiffeomorphicCaseScalarMeasurementCommand)!=0 : DisplayErrorAndQuit('[' + allcasesIDs[case] + '] dtiprocess: Computing Diffeomorphic '+m_ScalarMeasurement)
            logger("[" + allcasesIDs[case] + "] => $ " + CaseDbleToFloatCommand + "\n")
            if os.system(CaseDbleToFloatCommand)!=0 : DisplayErrorAndQuit('[' + allcasesIDs[case] + '] unu: Converting the final DTI images from double to float DTI')
          else:
            GridProcessCommandsArray.append(FinalReSampCommand)
            GridProcessCommandsArray.append(GeneDiffeomorphicCaseScalarMeasurementCommand)
            GridProcessCommandsArray.append(CaseDbleToFloatCommand)
            if len(GridProcessCommandsArray)>=50 or case==len(allcases)-1 : # launch a script if more than 50 operations or if last case\n";
              GridProcessCmd= "" + m_GridGeneralCommand + " " + m_PythonPath + " " + m_OutputPath + "/Script/RunCommandOnServer.py " + FilesFolder + "/Case" + str(NbGridCommandsRan+1)
              GridCmd = 0
              while GridCmd < len(GridProcessCommandsArray):
                GridProcessCmd = GridProcessCmd + " '" + GridProcessCommandsArray[GridCmd] + "'"
                GridCmd += 1
              GridProcessCommandsArray=[] # Empty the cmds array\n";
              NbGridCommandsRan += 1
              if os.system(GridProcessCmd)!=0 : # Run script and collect error if so\n";
                DisplayErrorAndQuit('[] Applying deformation fields to original DTIs')
      else:
        if not CheckFileExists(FinalDTI, case, allcasesIDs[case]) :
          DiffeomorphicCaseScalarMeasurement = FinalPath + "/" + allcasesIDs[case] + "_Diffeomorphic"+m_ScalarMeasurement+".nrrd"
          if m_ScalarMeasurement=="FA":
            GeneDiffeomorphicCaseScalarMeasurementCommand=m_SoftPath[3]+" --scalar_float --dti_image " + FinalDTI + " -f " + DiffeomorphicCaseScalarMeasurement
          else:
            GeneDiffeomorphicCaseScalarMeasurementCommand=m_SoftPath[3]+" --scalar_float --dti_image " + FinalDTI + " -m " + DiffeomorphicCaseScalarMeasurement
          CaseDbleToFloatCommand=m_SoftPath[8] +" convert -t float -i " + FinalDTI + " | " + m_SoftPath[8] +" save -f nrrd -e gzip -o " + FinalPath + "/" + allcasesIDs[case] + "_DiffeomorphicDTI_float.nrrd"

          if not m_useGridProcess:
            if os.system(FinalReSampCommand)!=0 : DisplayErrorAndQuit('[' + allcasesIDs[case] + '] ResampleDTIlogEuclidean: Applying deformation fields to original DTIs')
            logger("[" + allcasesIDs[case] + "] => $ " + GeneDiffeomorphicCaseScalarMeasurementCommand)
            if os.system(GeneDiffeomorphicCaseScalarMeasurementCommand)!=0 : DisplayErrorAndQuit('[' + allcasesIDs[case] + '] dtiprocess: Computing Diffeomorphic '+m_ScalarMeasurement)
            logger("[" + allcasesIDs[case] + "] => $ " + CaseDbleToFloatCommand + "\n")
            if os.system(CaseDbleToFloatCommand)!=0 : DisplayErrorAndQuit('[' + allcasesIDs[case] + '] unu: Converting the final DTI images from double to float DTI')
          else:
            GridProcessCommandsArray.append(FinalReSampCommand)
            GridProcessCommandsArray.append(GeneDiffeomorphicCaseScalarMeasurementCommand)
            GridProcessCommandsArray.append(CaseDbleToFloatCommand)
            if len(GridProcessCommandsArray)>=50 or case==len(allcases)-1 : # launch a script if more than 50 operations or if last case\n";
              GridProcessCmd= "" + m_GridGeneralCommand + " " + m_PythonPath + " " + m_OutputPath + "/Script/RunCommandOnServer.py " + FilesFolder + "/Case" + str(NbGridCommandsRan+1)
              GridCmd = 0
              while GridCmd < len(GridProcessCommandsArray):
                GridProcessCmd = GridProcessCmd + " '" + GridProcessCommandsArray[GridCmd] + "'"
                GridCmd += 1
              GridProcessCommandsArray=[] # Empty the cmds array\n";
              NbGridCommandsRan += 1
              if os.system(GridProcessCmd)!=0 : # Run script and collect error if so\n";
                DisplayErrorAndQuit('[] Applying deformation fields to original DTIs')      
        else : logger("=> The file \'" + FinalDTI + "\' already exists so the command will not be executed")
      case += 1

    if m_useGridProcess:
      if NbGridCommandsRan!=0 : TestGridProcess( FilesFolder, NbGridCommandsRan ) # stays in the function until all process is done : 0 cmds makes the function look for 'file'

    # DTIaverage computing
    DTIAverage = FinalPath + "/DiffeomorphicAtlasDTI.nrrd"
    AverageCommand = m_SoftPath[6] + " " # e.g. "/work/dtiatlasbuilder-build/DTIProcess-install/bin/dtiaverage "
    case = 0
    while case < len(allcases):
      DTIforAVG= "--inputs " + FinalPath + "/" + allcasesIDs[case] + "_DiffeomorphicDTI.nrrd "
      AverageCommand = AverageCommand + DTIforAVG
      case += 1
    AverageCommand = AverageCommand + "--tensor_output " + DTIAverage
    logger("\n[Computing the Diffeomorphic DTI average] => $ " + AverageCommand)


    #### 3_Diffeomophic_Atlas

    if m_Overwrite==1 or not CheckFileExists(DTIAverage, 0, "") : 
    # Computing some images from the final DTI with dtiprocess
      FA= FinalPath + "/DiffeomorphicAtlasFA.nrrd"
      cFA= FinalPath + "/DiffeomorphicAtlasColorFA.nrrd"
      RD= FinalPath + "/DiffeomorphicAtlasRD.nrrd"
      MD= FinalPath + "/DiffeomorphicAtlasMD.nrrd"
      AD= FinalPath + "/DiffeomorphicAtlasAD.nrrd"
      GeneScalarMeasurementCommand=m_SoftPath[3] + " --scalar_float --dti_image " + DTIAverage + " -f " + FA + " -m " + MD + " --color_fa_output " + cFA + " --RD_output " + RD + " --lambda1_output " + AD
      DbleToFloatCommand=m_SoftPath[8]+" convert -t float -i " + DTIAverage + " | " + m_SoftPath[8] + " save -f nrrd -e gzip -o " + FinalPath + "/DiffeomorphicAtlasDTI_float.nrrd"
      if not m_useGridProcess:
        if os.system(AverageCommand)!=0 : DisplayErrorAndQuit('dtiaverage: Computing the final DTI average')
        logger("[Computing some images from the final DTI with dtiprocess] => $ " + GeneScalarMeasurementCommand)
        if os.system(GeneScalarMeasurementCommand)!=0 : DisplayErrorAndQuit('dtiprocess: Computing Diffeomorphic FA, color FA, MD, RD and AD')
        logger("[Computing some images from the final DTI with dtiprocess] => $ " + DbleToFloatCommand)
        if os.system(DbleToFloatCommand)!=0 : DisplayErrorAndQuit('unu: Converting the final DTI atlas from double to float DTI')
      else:
        AverageGridCommand=AverageCommand + "' " + "'" + GeneScalarMeasurementCommand + "' " + "'" + DbleToFloatCommand + "'"
        if os.system(AverageGridCommand)!=0 : DisplayErrorAndQuit('Computing the final DTI average')
    else: logger("=> The file '" + DTIAverage + "' already exists so the command will not be executed")
    if m_useGridProcess:
      TestGridProcess( FilesFolder, 0 ) # stays in the function until all process is done : 0 makes the function look for \'file\'


    # Computing global deformation fields
    case = 0
    while case < len(allcases):
      if m_NeedToBeCropped==1:
        origDTI= AffinePath + "/" + allcasesIDs[case] + "_croppedDTI.nrrd"
      else:
        origDTI= allcases[case]
      GlobalDefField = FinalResampPath + "/First_Resampling/" + allcasesIDs[case] + "_GlobalDisplacementField.nrrd"
      InverseGlobalDefField = FinalResampPath + "/First_Resampling/" + allcasesIDs[case] + "_GlobalDisplacementField_Inverse.nrrd"
      FinalDef = FinalResampPath + "/First_Resampling/" + allcasesIDs[case] + "_DeformedDTI.nrrd"
      GlobalDefFieldCommand=m_SoftPath[7]+" --fixedVolume " + DTIAverage + " --movingVolume " + origDTI + " --scalarMeasurement "+m_ScalarMeasurement +" --outputDisplacementField " + GlobalDefField + " --outputInverseDeformationFieldVolume " +InverseGlobalDefField  + " --outputVolume " + FinalDef
      
      BRAINSExecDir = os.path.dirname(m_SoftPath[4])
      dtiprocessExecDir = os.path.dirname(m_SoftPath[3])
      ResampExecDir = os.path.dirname(m_SoftPath[1])

      GlobalDefFieldCommand = GlobalDefFieldCommand + " --ProgramsPathsVector "+m_DTIRegExtraPath+","+BRAINSExecDir+","+dtiprocessExecDir+","+ResampExecDir
      
      if m_DTIRegOptions[0]=="BRAINS":
        GlobalDefFieldCommand= GlobalDefFieldCommand + " --method useScalar-BRAINS"
        if m_DTIRegOptions[1]=="GreedyDiffeo (SyN)":
          GlobalDefFieldCommand= GlobalDefFieldCommand + " --BRAINSRegistrationType GreedyDiffeo"
        elif m_DTIRegOptions[1]=="SpatioTempDiffeo":
          GlobalDefFieldCommand= GlobalDefFieldCommand + " --BRAINSRegistrationType SpatioTempDiffeo"
        else:
          GlobalDefFieldCommand= GlobalDefFieldCommand + " --BRAINSRegistrationType " + m_DTIRegOptions[1] + ""
        GlobalDefFieldCommand= GlobalDefFieldCommand + " --BRAINSnumberOfPyramidLevels " + m_DTIRegOptions[3] + ""
        GlobalDefFieldCommand= GlobalDefFieldCommand + " --BRAINSarrayOfPyramidLevelIterations " + m_DTIRegOptions[4] + ""
        if m_DTIRegOptions[2]=="Use computed affine transform":
          GlobalDefFieldCommand= GlobalDefFieldCommand + " --initialAffine " + alltfms[case]
        else:
          GlobalDefFieldCommand= GlobalDefFieldCommand + " --BRAINSinitializeTransformMode " + m_DTIRegOptions[2] + ""
        BRAINSTempTfm = FinalResampPath + "/First_Resampling/" + allcasesIDs[case] + "_" + m_ScalarMeasurement + "_AffReg.txt"
        GlobalDefFieldCommand= GlobalDefFieldCommand + " --outputTransform " + BRAINSTempTfm

      if m_DTIRegOptions[0]=="ANTS":
        GlobalDefFieldCommand= GlobalDefFieldCommand + " --method useScalar-ANTS"
        if m_DTIRegOptions[1]=="GreedyDiffeo (SyN)":
          GlobalDefFieldCommand= GlobalDefFieldCommand + " --ANTSRegistrationType GreedyDiffeo"
        elif m_DTIRegOptions[1]=="SpatioTempDiffeo (SyN)":
          GlobalDefFieldCommand= GlobalDefFieldCommand + " --ANTSRegistrationType SpatioTempDiffeo"
        else:
          GlobalDefFieldCommand= GlobalDefFieldCommand + " --ANTSRegistrationType " + m_DTIRegOptions[1] + ""
        GlobalDefFieldCommand= GlobalDefFieldCommand + " --ANTSTransformationStep " + m_DTIRegOptions[2] + ""
        GlobalDefFieldCommand= GlobalDefFieldCommand + " --ANTSIterations " + m_DTIRegOptions[3] + ""
        if m_DTIRegOptions[4]=="Cross-Correlation (CC)" :
          GlobalDefFieldCommand= GlobalDefFieldCommand + " --ANTSSimilarityMetric CC"
        elif m_DTIRegOptions[4]=="Mutual Information (MI)" :
          GlobalDefFieldCommand= GlobalDefFieldCommand + " --ANTSSimilarityMetric MI"
        elif m_DTIRegOptions[4]=="Mean Square Difference (MSQ)":
          GlobalDefFieldCommand= GlobalDefFieldCommand + " --ANTSSimilarityMetric MSQ"
        GlobalDefFieldCommand= GlobalDefFieldCommand + " --ANTSSimilarityParameter " + m_DTIRegOptions[5] + ""
        GlobalDefFieldCommand= GlobalDefFieldCommand + " --ANTSGaussianSigma " + m_DTIRegOptions[6] + ""
        if m_DTIRegOptions[7]=="1":
          GlobalDefFieldCommand= GlobalDefFieldCommand + " --ANTSGaussianSmoothingOff"
        GlobalDefFieldCommand= GlobalDefFieldCommand + " --initialAffine " + alltfms[case]
        GlobalDefFieldCommand= GlobalDefFieldCommand + " --ANTSUseHistogramMatching "
        ANTSTempFileBase = FinalResampPath + "/First_Resampling/" + allcasesIDs[case] + "_" + m_ScalarMeasurement + "_"
        GlobalDefFieldCommand= GlobalDefFieldCommand + " --ANTSOutbase " + ANTSTempFileBase

      logger("\n[" + allcasesIDs[case] + "] [Computing global deformation fields] => $ " + GlobalDefFieldCommand)


      if m_Overwrite==1 or not CheckFileExists(FinalDef, case, allcasesIDs[case]) :
        GlobDbleToFloatCommand=m_SoftPath[8]+" convert -t float -i " + FinalDef + " | "+m_SoftPath[8]+" save -f nrrd -e gzip -o " + FinalResampPath + "/First_Resampling/" + allcasesIDs[case] + "_DeformedDTI_float.nrrd"

        if not m_useGridProcess:
          if os.system(GlobalDefFieldCommand)!=0 : DisplayErrorAndQuit('[' + allcasesIDs[case] + '] DTI-Reg: Computing global deformation fields')
          logger("\n[" + allcasesIDs[case] + "] [Converting the deformed images from double to float DTI] => $ " + GlobDbleToFloatCommand)
          if os.system(GlobDbleToFloatCommand)!=0 : DisplayErrorAndQuit('[' + allcasesIDs[case] + '] unu: Converting the deformed images from double to float DTI')
        else:
          GlobDefFieldGridCommand=GridProcessCmd +" " + GlobalDefFieldCommand + "' " + "'" + GlobDbleToFloatCommand + "'"
          if os.system(GlobDefFieldGridCommand)!=0 : DisplayErrorAndQuit('[' + allcasesIDs[case] + '] Computing global deformation fields')

      else:
        logger("=> The file '" + FinalDef + "' already exists so the command will not be executed")
      case += 1

    if m_useGridProcess:
      TestGridProcess( FilesFolder, len(allcases) ) # stays in the function until all process is done : 0 makes the function look for \'file\'

    # for i in range(m_nbLoopsDTIReg):
    #   if not os.path.isdir(FinalResampPath+"/Second_Resampling"+"/Loop_"+str(i)):
    #     logger("\n=> Creation of the Second Final Resampling loop directory  = " + FinalResampPath + "/Second_Resampling" +"/Loop_"+str(i))
    #     os.mkdir(FinalResampPath + "/Second_Resampling" + "/Loop_"+str(i))

    #### 4_Second_Resampling

    ### looping begins
    cnt=0
    if m_Overwrite==0:
      for i in range(m_nbLoopsDTIReg):
        if os.path.isdir(FinalResampPath+"/Second_Resampling"+"/Loop_"+str(i)):
          cnt=i 
      cnt=max(cnt,0)

    while cnt < m_nbLoopsDTIReg:
      logger("-----------------------------------------------------------")
      logger("Iterative Registration cycle %d / %d" % (cnt+1,m_nbLoopsDTIReg) )
      logger("------------------------------------------------------------")

      if not os.path.isdir(FinalResampPath+"/Second_Resampling"+"/Loop_"+str(cnt)):
        logger("\n=> Creation of the Second Final Resampling loop directory  = " + FinalResampPath + "/Second_Resampling" +"/Loop_"+str(cnt))
        os.mkdir(FinalResampPath + "/Second_Resampling" + "/Loop_"+str(cnt))
      # dtiaverage recomputing
      IterDir="Loop_"+str(cnt)+"/"
      PrevIterDir="Loop_"+str(cnt-1)+"/"
      DTIAverage2 = FinalResampPath + "/Second_Resampling/" + IterDir+ "/FinalAtlasDTI.nrrd"
      AverageCommand2 = m_SoftPath[6]+" "  #dtiaverage
      
      if cnt==0:
        case = 0
        while case < len(allcases):
          DTIforAVG2= "--inputs " + FinalResampPath + "/First_Resampling/" + allcasesIDs[case] + "_DeformedDTI.nrrd "
          AverageCommand2 = AverageCommand2 + DTIforAVG2
          case += 1
        AverageCommand2 = AverageCommand2 + "--tensor_output " + DTIAverage2
        logger("\n[Recomputing the final DTI average] => $ " + AverageCommand2)
      else: ### when iterative registration is activated
        case=0
        while case < len(allcases):
          DTIforAVG2= "--inputs " + FinalResampPath + "/Second_Resampling/" + PrevIterDir+ allcasesIDs[case] + "_FinalDeformedDTI.nrrd "
          AverageCommand2 = AverageCommand2 + DTIforAVG2
          case += 1
        AverageCommand2 = AverageCommand2 + "--tensor_output " + DTIAverage2
        logger("\n[Recomputing the final DTI average] => $ " + AverageCommand2)   


      if m_Overwrite==1 or not CheckFileExists(DTIAverage2, 0, ""): 
      # Computing some images from the final DTI with dtiprocess
        FA2= FinalResampPath + "/Second_Resampling/" +IterDir+ "/FinalAtlasFA.nrrd"
        cFA2= FinalResampPath +"/Second_Resampling/" +IterDir+ "/FinalAtlasColorFA.nrrd"
        RD2= FinalResampPath + "/Second_Resampling/" +IterDir+"/FinalAtlasRD.nrrd"
        MD2= FinalResampPath + "/Second_Resampling/" +IterDir+"/FinalAtlasMD.nrrd"
        AD2= FinalResampPath + "/Second_Resampling/" +IterDir+"/FinalAtlasAD.nrrd"
        GeneScalarMeasurementCommand2=m_SoftPath[3]+" --scalar_float --dti_image " + DTIAverage2 + " -f " + FA2 + " -m " + MD2 + " --color_fa_output " + cFA2 + " --RD_output " + RD2 + " --lambda1_output " + AD2
        DbleToFloatCommand2=m_SoftPath[8]+" convert -t float -i " + DTIAverage2 + " | "+m_SoftPath[8]+" save -f nrrd -e gzip -o " + FinalResampPath + "/Second_Resampling/" +IterDir+ "/FinalAtlasDTI_float.nrrd"
        if not m_useGridProcess:
          if os.system(AverageCommand2)!=0 : DisplayErrorAndQuit('dtiaverage: Recomputing the final DTI average')
          logger("[Computing some images from the final DTI with dtiprocess] => $ " + GeneScalarMeasurementCommand2)
          if os.system(GeneScalarMeasurementCommand2)!=0 : DisplayErrorAndQuit('dtiprocess: Recomputing final FA, color FA, MD, RD and AD')
          logger("[Computing some images from the final DTI with dtiprocess] => $ " + DbleToFloatCommand2)
          if os.system(DbleToFloatCommand2)!=0 : DisplayErrorAndQuit('unu: Converting the final resampled DTI atlas from double to float DTI')
        else:
          Average2GridCommand=GridProcessCmdNoCase + " "+AverageCommand2 + "' " + "'" + GeneScalarMeasurementCommand2 + "' " + "'" + DbleToFloatCommand2 + "'"
          if os.system(Average2GridCommand)!=0 : DisplayErrorAndQuit('Recomputing the final DTI average')
      else:
        logger("=> The file '" + DTIAverage2 + "' already exists so the command will not be executed")

      if m_useGridProcess:
        TestGridProcess( FilesFolder, 0 ) # stays in the function until all process is done : 0 makes the function look for \'file\'

      # Recomputing global deformation fields
      SecondResampRecomputed = [0] * len(allcases) # array of 1s and 0s to know what has been recomputed to know what to copy to final folders
      case = 0
      while case < len(allcases):
        if m_NeedToBeCropped==1:
          origDTI2= AffinePath + "/" + allcasesIDs[case] + "_croppedDTI.nrrd"
        else:
          origDTI2= allcases[case]
        GlobalDefField2 = FinalResampPath + "/Second_Resampling/" + IterDir+ allcasesIDs[case] + "_GlobalDisplacementField.nrrd"
        InverseGlobalDefField2 = FinalResampPath + "/Second_Resampling/" + IterDir+ allcasesIDs[case] + "_InverseGlobalDisplacementField.nrrd"
        FinalDef2 = FinalResampPath + "/Second_Resampling/" + IterDir + allcasesIDs[case] + "_FinalDeformedDTI.nrrd"
        GlobalDefFieldCommand2=m_SoftPath[7]+" --fixedVolume " + DTIAverage2 + " --movingVolume " + origDTI2 + " --scalarMeasurement "+m_ScalarMeasurement+" --outputDisplacementField " + GlobalDefField2 + " --outputVolume " + FinalDef2 + " --outputInverseDeformationFieldVolume " + InverseGlobalDefField2
        GlobalDefFieldCommand2 = GlobalDefFieldCommand2 + " --ProgramsPathsVector " + m_DTIRegExtraPath + "," + BRAINSExecDir + "," + dtiprocessExecDir + "," + ResampExecDir + ""

        if m_DTIRegOptions[0]=="BRAINS":
          GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --method useScalar-BRAINS"
          if m_DTIRegOptions[1]=="GreedyDiffeo (SyN)":
            GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --BRAINSRegistrationType GreedyDiffeo"
          elif m_DTIRegOptions[1]=="SpatioTempDiffeo":
            GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --BRAINSRegistrationType SpatioTempDiffeo"
          else:
            GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --BRAINSRegistrationType " + m_DTIRegOptions[1] + ""
          GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --BRAINSnumberOfPyramidLevels " + m_DTIRegOptions[3] + ""
          GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --BRAINSarrayOfPyramidLevelIterations " + m_DTIRegOptions[4] + ""
          if m_DTIRegOptions[2]=="Use computed affine transform":
            GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --initialAffine " + alltfms[case]
          else:
            GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --BRAINSinitializeTransformMode " + m_DTIRegOptions[2] + ""
          BRAINSTempTfm = FinalResampPath + "/First_Resampling/" + allcasesIDs[case] + "_" + m_ScalarMeasurement + "_AffReg.txt"
          GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --outputTransform " + BRAINSTempTfm

        if m_DTIRegOptions[0]=="ANTS":
          GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --method useScalar-ANTS"
          if m_DTIRegOptions[1]=="GreedyDiffeo (SyN)":
            GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --ANTSRegistrationType GreedyDiffeo"
          elif m_DTIRegOptions[1]=="SpatioTempDiffeo (SyN)":
            GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --ANTSRegistrationType SpatioTempDiffeo"
          else:
            GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --ANTSRegistrationType " + m_DTIRegOptions[1] + ""
          GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --ANTSTransformationStep " + m_DTIRegOptions[2] + ""
          GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --ANTSIterations " + m_DTIRegOptions[3] + ""
          if m_DTIRegOptions[4]=="Cross-Correlation (CC)" :
            GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --ANTSSimilarityMetric CC"
          elif m_DTIRegOptions[4]=="Mutual Information (MI)" :
            GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --ANTSSimilarityMetric MI"
          elif m_DTIRegOptions[4]=="Mean Square Difference (MSQ)":
            GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --ANTSSimilarityMetric MSQ"
          GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --ANTSSimilarityParameter " + m_DTIRegOptions[5] + ""
          GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --ANTSGaussianSigma " + m_DTIRegOptions[6] + ""
          if m_DTIRegOptions[7]=="1":
            GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --ANTSGaussianSmoothingOff"
          GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --initialAffine " + alltfms[case]
          GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --ANTSUseHistogramMatching "
          ANTSTempFileBase2 = FinalResampPath + "/First_Resampling/" + allcasesIDs[case] + "_" + m_ScalarMeasurement + "_"
          GlobalDefFieldCommand2= GlobalDefFieldCommand2 + " --ANTSOutbase " + ANTSTempFileBase2

        logger("\n[" + allcasesIDs[case] + "] [Recomputing global deformation fields] => $ " + GlobalDefFieldCommand2)

        if m_Overwrite==1 or not CheckFileExists(FinalDef2, case, allcasesIDs[case])  :
          SecondResampRecomputed[case] = 1
          DTIRegCaseScalarMeasurement = FinalResampPath + "/Second_Resampling/" + IterDir + allcasesIDs[case] + "_FinalDeformed"+m_ScalarMeasurement+".nrrd"
          if m_ScalarMeasurement=="FA":
            GeneDTIRegCaseScalarMeasurementCommand=m_SoftPath[3]+" --scalar_float --dti_image " + FinalDef2 + " -f " + DTIRegCaseScalarMeasurement
          else:
            GeneDTIRegCaseScalarMeasurementCommand=m_SoftPath[3]+" --scalar_float --dti_image " + FinalDef2 + " -m " + DTIRegCaseScalarMeasurement

          GlobDbleToFloatCommand2=m_SoftPath[8]+" convert -t float -i " + FinalDef2 + " | "+m_SoftPath[8]+" save -f nrrd -e gzip -o " + FinalResampPath + "/Second_Resampling/" + IterDir +  allcasesIDs[case] + "_FinalDeformedDTI_float.nrrd"
          
          if not m_useGridProcess:
            if os.system(GlobalDefFieldCommand2)!=0 : DisplayErrorAndQuit('[' + allcasesIDs[case] + '] DTI-Reg: Computing global deformation fields')
            logger("\n[" + allcasesIDs[case] + "] [Converting the deformed images from double to float DTI] => $ " + GlobDbleToFloatCommand2)
            if os.system(GlobDbleToFloatCommand2)!=0 : DisplayErrorAndQuit('[' + allcasesIDs[case] + '] unu: Converting the deformed images from double to float DTI')
            logger("\n[" + allcasesIDs[case] + "] [Computing DTIReg "+m_ScalarMeasurement+"] => $ " + GeneDTIRegCaseScalarMeasurementCommand)
            if os.system(GeneDTIRegCaseScalarMeasurementCommand)!=0 : DisplayErrorAndQuit('[' + allcasesIDs[case] + '] dtiprocess: Computing DTIReg '+m_ScalarMeasurement)
          else:
            GlobDefField2GridCommand=GridProcessCmd +" " + GlobalDefFieldCommand2 + "' " + "'" + GlobDbleToFloatCommand2 + "' " + "'" + GeneDTIRegCaseScalarMeasurementCommand + "'"
            if os.system(GlobDefField2GridCommand)!=0 : DisplayErrorAndQuit('[' + allcasesIDs[case] + '] Recomputing global deformation fields')
        else:
          logger("=> The file '" + FinalDef2 + "' already exists so the command will not be executed")
        case += 1

      if m_useGridProcess:
        TestGridProcess( FilesFolder, len(allcases) ) # stays in the function until all process is done : 0 makes the function look for \'file\'
      ### Cleanup - delete PrevIterDir
      if cnt > 1:
        PrevPrevIterDir="Loop_"+str(cnt-2)+"/"
        DirToRemove = FinalResampPath + "/Second_Resampling/" + PrevPrevIterDir
        if os.path.exists(DirToRemove):
          shutil.rmtree(DirToRemove)

      cnt+=1


    # End while cnt < m_nbLoopDTIReg

    # Moving final images to final folders
    logger("\n=> Moving final images to final folders")
    case = 0
    LastIterDir="Loop_"+str(m_nbLoopsDTIReg-1)+"/"

    while case < len(allcases):
      if SecondResampRecomputed[case] :
        GlobalDefField2 = FinalResampPath + "/Second_Resampling/" + LastIterDir + allcasesIDs[case] + "_GlobalDisplacementField.nrrd"
        NewGlobalDefField2 = FinalResampPath + "/FinalDeformationFields/" + allcasesIDs[case] + "_GlobalDisplacementField.nrrd"
        if CheckFileExists(GlobalDefField2, case, allcasesIDs[case]) :
          shutil.copy(GlobalDefField2, NewGlobalDefField2)
        InverseGlobalDefField2 = FinalResampPath + "/Second_Resampling/" + LastIterDir + allcasesIDs[case] + "_InverseGlobalDisplacementField.nrrd"
        NewInverseGlobalDefField2 = FinalResampPath + "/FinalDeformationFields/" + allcasesIDs[case] + "_InverseGlobalDisplacementField.nrrd"
        if CheckFileExists(InverseGlobalDefField2, case, allcasesIDs[case]) :
          shutil.copy(InverseGlobalDefField2, NewInverseGlobalDefField2)
        FinalDef2 = FinalResampPath + "/Second_Resampling/" + LastIterDir+allcasesIDs[case] + "_FinalDeformedDTI.nrrd"
        NewFinalDef2 = FinalResampPath + "/FinalTensors/" + allcasesIDs[case] + "_FinalDeformedDTI.nrrd"
        if CheckFileExists(FinalDef2, case, allcasesIDs[case]) :
          shutil.copy(FinalDef2, NewFinalDef2)
        FinalDef2f = FinalResampPath + "/Second_Resampling/" + LastIterDir + allcasesIDs[case] + "_FinalDeformedDTI_float.nrrd"
        NewFinalDef2f = FinalResampPath + "/FinalTensors/" + allcasesIDs[case] + "_FinalDeformedDTI_float.nrrd"
        if CheckFileExists(FinalDef2f, case, allcasesIDs[case]) :
          shutil.copy(FinalDef2f, NewFinalDef2f)
        DTIRegCaseScalarMeasurement = FinalResampPath + "/Second_Resampling/" + LastIterDir + allcasesIDs[case] + "_FinalDeformed"+m_ScalarMeasurement+".nrrd"
        NewDTIRegCaseScalarMeasurement = FinalResampPath + "/FinalTensors/" + allcasesIDs[case] + "_FinalDeformed"+m_ScalarMeasurement+".nrrd"
        if CheckFileExists(DTIRegCaseScalarMeasurement, case, allcasesIDs[case]) :
          shutil.copy(DTIRegCaseScalarMeasurement, NewDTIRegCaseScalarMeasurement)
      case += 1

    # Copy final atlas components to FinalAtlasPath directory

    logger("Copying Final atlas components to " + FinalAtlasPath)
    shutil.rmtree(FinalAtlasPath)
    shutil.copytree(FinalResampPath+"/"+"/Second_Resampling/"+LastIterDir,FinalAtlasPath)
    shutil.copytree(FinalResampPath+"/FinalDeformationFields",FinalAtlasPath+"/FinalDeformationFields")
    shutil.copytree(FinalResampPath+"/FinalTensors",FinalAtlasPath+"/FinalTensors")

    logger("\n============ End of Atlas Building =============")






