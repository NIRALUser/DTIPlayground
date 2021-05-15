#
#   preprocess.py 
#   2021-05-10
#   Written by SK Park, NIRAL, UNC
#
#   Atlasbuilder preprocessing scripts
#


import os # To run a shell command : os.system("[shell command]") >> will be replaced to subprocess
import sys # to return an exit code
import shutil # to remove a non empty directory

import dmri.atlasbuilder as ab 
import dmri.common.tools as tools

logger=ab.logger.write

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

    logger("\n============ Pre processing =============")

    # Files Paths
    allcases = config['m_CasesPath']
    allcasesIDs = config['m_CasesIDs'] 
    OutputPath= config['m_OutputPath']+ "/1_Affine_Registration"
    AtlasScalarMeasurementref=None 


    if config['m_RegType']==1:
      AtlasScalarMeasurementref= OutputPath + '/' + config['m_CasesIDs'][0] + '_'+ config['m_ScalarMeasurement'] + ".nrrd" #"/ImageTest1_FA.nrrd" #the reference will be the first case for the first loop
    else:
      AtlasScalarMeasurementref= config['m_TemplatePath'] 

    def pyExecuteCommandPreprocessCase(NameOfFileVarToTest, NameOfCmdVarToExec, ErrorTxtToDisplay,case=0):
      if config["m_Overwrite"]==1:
        if os.system(NameOfCmdVarToExec)!=0 : DisplayErrorAndQuit('[' + allcasesIDs[case] + ']' + ErrorTxtToDisplay)
      else:
        if not CheckFileExists(NameOfFileVarToTest,case, allcases[case]):
            if os.system(NameOfCmdVarToExec)!=0 : DisplayErrorAndQuit('[' + allcasesIDs[case] + ']' + ErrorTxtToDisplay)
        else:
          logger("=> The file '" + NameOfFileVarToTest + "' already exists so the command will not be executed")




    # Create directory for temporary files
    if not os.path.isdir(OutputPath):
      os.mkdir(OutputPath)
      logger("\n=> Creation of the affine directory = " + OutputPath)

    # Creating template by processing Case 1 DTI
    ScalarMeasurement=config['m_ScalarMeasurement']

    if config['m_RegType']==0:
      # Rescaling template
      RescaleTemp= OutputPath + "/" + config['m_ScalarMeasurement'] + "Template_Rescaled.nrrd"
      RescaleTempCommand= "" + config['m_SoftPath'][0] + " " + AtlasScalarMeasurementref + " -outfile " + RescaleTemp + " -rescale 0,10000"  
      logger("\n[Rescaling " + config['m_ScalarMeasurement'] + " template] => $ " + RescaleTempCommand)
      if config['m_Overwrite']==1:
        if os.system(RescaleTempCommand)!=0 : DisplayErrorAndQuit('ImageMath: Rescaling ' + config['m_ScalarMeasurement'] + ' template')
      else:
        if not CheckFileExists(RescaleTemp, 0, "" ) :
          if os.system(RescaleTempCommand)!=0 : DisplayErrorAndQuit('ImageMath: Rescaling ' + config['m_ScalarMeasurement'] + ' template')
        else : logger("=> The file \\'" + RescaleTemp + "\\' already exists so the command will not be executed")
      AtlasScalarMeasurementref= RescaleTemp

    else:
    # Filter case 1 DTI
      logger("")
      FilteredDTI= OutputPath + "/" + config['m_CasesIDs'][0] +"_filteredDTI.nrrd"
      FilterDTICommand=  config['m_SoftPath'][1] +" " + allcases[0] + " " + FilteredDTI + " --correction zero"
      logger("["+ config['m_CasesIDs'][0] +"] [Filter DTI] => $ " + FilterDTICommand)
      if config['m_Overwrite']==1 :
        if os.system(FilterDTICommand)!=0 : DisplayErrorAndQuit('['+config['m_CasesIDs'][0]+'] ResampleDTIlogEuclidean: 1ow Filter DTI to remove negative values')
      else:
        if not CheckFileExists(FilteredDTI, 0, "" + config["m_CasesIDs"][0] + "" ) :
          if os.system(FilterDTICommand)!=0 : DisplayErrorAndQuit('['+config['m_CasesIDs'][0]+'] ResampleDTIlogEuclidean: 1 Filter DTI to remove negative values')
        else : logger("=> The file \'" + FilteredDTI + "\' already exists so the command will not be executed")

      # Cropping case 1 DTI
      if config['m_NeedToBeCropped']==1:
        croppedDTI = OutputPath + "/" + config['m_CasesIDs'][0] + "_croppedDTI.nrrd"
        CropCommand =  config['m_SoftPath'][2] + " " + FilteredDTI + " -o " + croppedDTI + " -size " + config['m_CropSize'][0] + "," + config['m_CropSize'][1] + "," + config['m_CropSize'][2] + " -v"
        logger("[" +config['m_CasesIDs'][0] + "] [Cropping DTI Image] => $ " + CropCommand)
        
        if config["m_Overwrite"]==1:
          if os.system(CropCommand)!=0 : DisplayErrorAndQuit('[' + config["m_CasesIDs"][0] + '] CropDTI: Cropping DTI image')
        else:
          if not CheckFileExists(croppedDTI, 0, "" + config['m_CasesIDs'][0] + "" ) :
            if os.system(CropCommand)!=0 : DisplayErrorAndQuit('[' + config["m_CasesIDs"][0] + '] CropDTI: Cropping DTI image')
          else:
            logger("=> The file '" + croppedDTI + "' already exists so the command will not be executed")



      # Generating case 
      if config['m_NeedToBeCropped']==1:
        DTI= OutputPath + "/" + config['m_CasesIDs'][0]+"_croppedDTI.nrrd"
      else:
        DTI= allcases[0]

      ScalarMeasurement= OutputPath + "/" + config['m_CasesIDs'][0] + "_" + config['m_ScalarMeasurement']+".nrrd"
      if config['m_ScalarMeasurement']=="FA" :
        GeneScalarMeasurementCommand= config['m_SoftPath'][3] + " --dti_image " + DTI + " -f " + ScalarMeasurement
      else:
        GeneScalarMeasurementCommand= config['m_SoftPath'][3] + " --dti_image " + DTI + " -m " + ScalarMeasurement

      logger( ("[%s]"%config['m_CasesIDs'][0])+" [Generating FA] => $ " + GeneScalarMeasurementCommand)

      if config['m_Overwrite']==1 :
        if os.system(GeneScalarMeasurementCommand)!=0 : DisplayErrorAndQuit('[ImageTest1] dtiprocess: Generating FA of DTI image')
      else : 
        if not CheckFileExists(ScalarMeasurement, 0, config["m_CasesIDs"][0] ) :
          if os.system(GeneScalarMeasurementCommand)!=0 : DisplayErrorAndQuit('[ImageTest1] dtiprocess: Generating FA of DTI image')
          logger("=> The file \'" + ScalarMeasurement + "\' already exists so the command will not be executed")


    logger("")

    # Affine Registration and Normalization Loop
    n = 0
    while n <= config['m_nbLoops'] : 
      if not os.path.isdir(OutputPath + "/Loop" + str(n)):
        logger("\n=> Creation of the Output directory for Loop " + str(n) + " = " + OutputPath + "/Loop" + str(n) + "\n")
        os.mkdir(OutputPath + "/Loop" + str(n))

      # Cases Loop
      case= 0
      if config["m_RegType"]==1: 
        case = (n==0) # (n==0) -> bool: =1(true) =0(false) : the first case is the reference for the first loop so it will not be normalized or registered (it is cropped and FAed before the loop)

      while case < len(allcases):
        if n==0: # Filtering and Cropping DTI and Generating FA are only part of the first loop
           # Filter DTI
          # ResampleDTIlogEuclidean does by default a correction of tensor values by setting the negative values to zero
          FilteredDTI= OutputPath + "/" + allcasesIDs[case] + "_filteredDTI.nrrd"
          FilterDTICommand= config["m_SoftPath"][1] + " " + allcases[case] + " " + FilteredDTI + " --correction zero"
          logger("[" + allcasesIDs[case] + "] [Filter DTI] => $ " + FilterDTICommand)

          pyExecuteCommandPreprocessCase(FilteredDTI,FilterDTICommand,"ResampleDTIlogEuclidean: 2 Filter DTI to remove negative values",case)
          if config["m_NeedToBeCropped"]==1:
            croppedDTI=OutputPath + "/" + allcasesIDs[case] + "_croppedDTI.nrrd"
            CropCommand= "" + config["m_SoftPath"][2] + " " + FilteredDTI + " -o " + croppedDTI + " -size " + config["m_CropSize"][0] + "," + config["m_CropSize"][1] + "," + config["m_CropSize"][2] + " -v"
            logger("[" + allcasesIDs[case] + "] [Cropping DTI Image] => $ " + CropCommand)
            pyExecuteCommandPreprocessCase(croppedDTI,CropCommand,"CropDTI: Cropping DTI image" , case)


          # Generating FA/MD.
          if config["m_NeedToBeCropped"]==1:
            DTI=OutputPath + "/" + allcasesIDs[case] + "_croppedDTI.nrrd"
          else:
            DTI= allcases[case]
          ScalarMeasurement= OutputPath + "/" + allcasesIDs[case] + "_" + config["m_ScalarMeasurement"] + ".nrrd"
          if config["m_ScalarMeasurement"]=="FA":
            GeneScalarMeasurementCommand= config["m_SoftPath"][3] + " --dti_image " + DTI + " -f " + ScalarMeasurement
          else:
            GeneScalarMeasurementCommand= config["m_SoftPath"][3] + " --dti_image " + DTI + " -m " + ScalarMeasurement
          logger("[" + allcasesIDs[case] + "] [Generating "+config["m_ScalarMeasurement"]+"] => $ " + GeneScalarMeasurementCommand)
          pyExecuteCommandPreprocessCase(ScalarMeasurement,GeneScalarMeasurementCommand,"dtiprocess: Generating " + config["m_ScalarMeasurement"] + " of DTI image",case)

        # Normalization
        ScalarMeasurement= OutputPath + "/" + allcasesIDs[case] + "_"+config["m_ScalarMeasurement"]+".nrrd"
        NormScalarMeasurement= OutputPath + "/Loop" + str(n) + "/" + allcasesIDs[case] + "_Loop" + str(n) + "_Norm"+config["m_ScalarMeasurement"]+".nrrd"
        NormScalarMeasurementCommand= config["m_SoftPath"][0]+" " + ScalarMeasurement + " -outfile " + NormScalarMeasurement + " -matchHistogram " + AtlasScalarMeasurementref
        logger("[LOOP " + str(n) + "/"+ str(config["m_nbLoops"])+ "] [" + allcasesIDs[case] + "] [Normalization] => $ " + NormScalarMeasurementCommand)

        pyExecuteCommandPreprocessCase(NormScalarMeasurement,NormScalarMeasurementCommand, "ImageMath: Normalizing " + config["m_ScalarMeasurement"] + " image",case)
        # Affine registration with BrainsFit
        NormScalarMeasurement= OutputPath + "/Loop" + str(n) + "/" + allcasesIDs[case] + "_Loop" + str(n) + "_Norm"+config["m_ScalarMeasurement"]+".nrrd"
        LinearTranstfm= OutputPath + "/Loop" + str(n) + "/" + allcasesIDs[case] + "_Loop" + str(n) + "_LinearTrans.txt"
        LinearTrans= OutputPath + "/Loop" + str(n) + "/" + allcasesIDs[case] + "_Loop" + str(n) + "_LinearTrans_"+config["m_ScalarMeasurement"]+".nrrd"
        AffineCommand= config["m_SoftPath"][4]+" --fixedVolume " + AtlasScalarMeasurementref + " --movingVolume " + NormScalarMeasurement + " --useAffine --outputVolume " + LinearTrans + " --outputTransform " + LinearTranstfm
        InitLinearTransTxt= OutputPath + "/" + allcasesIDs[case] + "_InitLinearTrans.txt"
        InitLinearTransMat= OutputPath + "/" + allcasesIDs[case] + "_InitLinearTrans.mat"
        if n==0 and CheckFileExists( InitLinearTransMat, case, allcasesIDs[case] ) and CheckFileExists( InitLinearTransTxt, case, allcasesIDs[case] ):
          logger("[WARNING] Both \'" + allcasesIDs[case] + "_InitLinearTrans.mat\' and \'" + allcasesIDs[case] + "_InitLinearTrans.txt\' have been found. The .mat file will be used.")
          AffineCommand= AffineCommand + " --initialTransform " + InitLinearTransMat
        elif n==0 and CheckFileExists( InitLinearTransMat, case, allcasesIDs[case] ) : AffineCommand= AffineCommand + " --initialTransform " + InitLinearTransMat
        elif n==0 and CheckFileExists( InitLinearTransTxt, case, allcasesIDs[case] ) : AffineCommand= AffineCommand + " --initialTransform " + InitLinearTransTxt
        else : AffineCommand= AffineCommand + " --initializeTransformMode "+ config["m_BFAffineTfmMode"] #useCenterOfHeadAlign"
        logger("[LOOP " + str(n) + "/"+str(config["m_nbLoops"])+"] [" + allcasesIDs[case] + "] [Affine registration with BrainsFit] => $ " + AffineCommand)
        CheckFileExists( LinearTrans, case, allcasesIDs[case] ) 
        pyExecuteCommandPreprocessCase(LinearTranstfm,AffineCommand,"BRAINSFit: Affine Registration of " + config["m_ScalarMeasurement"] + " image",case)

        # Implementing the affine registration
        LinearTranstfm= OutputPath + "/Loop" + str(n) + "/" + allcasesIDs[case] + "_Loop" + str(n) + "_LinearTrans.txt"
        LinearTransDTI= OutputPath + "/Loop" + str(n) + "/" + allcasesIDs[case] + "_Loop" + str(n) + "_LinearTrans_DTI.nrrd"
        originalDTI= allcases[case]
        if config["m_NeedToBeCropped"]==1:
          originalDTI= OutputPath + "/" + allcasesIDs[case] + "_croppedDTI.nrrd"
        ImplementCommand= config["m_SoftPath"][1]+" " + originalDTI + " " + LinearTransDTI + " -f " + LinearTranstfm + " -R " + AtlasScalarMeasurementref
        logger("[LOOP " + str(n) + "/"+str(config["m_nbLoops"])+"] [" + allcasesIDs[case] + "] [Implementing the Affine registration] => $ " + ImplementCommand)
        pyExecuteCommandPreprocessCase(LinearTransDTI,ImplementCommand,  "ResampleDTIlogEuclidean: Implementing the Affine Registration on " +config["m_ScalarMeasurement"] + " image" ,case)

        # Generating FA/MA of registered images
        LinearTransDTI= OutputPath + "/Loop" + str(n) + "/" + allcasesIDs[case] + "_Loop" + str(n) + "_LinearTrans_DTI.nrrd"
        if n == config["m_nbLoops"] : LoopScalarMeasurement= OutputPath + "/Loop"+str(n)+"/" + allcasesIDs[case] + "_Loop"+ str(n)+"_Final"+config["m_ScalarMeasurement"]+".nrrd" # the last FA will be the Final output
        else : LoopScalarMeasurement= OutputPath + "/Loop" + str(n) + "/" + allcasesIDs[case] + "_Loop" + str(n) + "_"+config["m_ScalarMeasurement"]+".nrrd"
        
        GeneLoopScalarMeasurementCommand= config["m_SoftPath"][3]+" --dti_image " + LinearTransDTI + " -m " + LoopScalarMeasurement
        if config["m_ScalarMeasurement"]=="FA":
          GeneLoopScalarMeasurementCommand= config["m_SoftPath"][3]+" --dti_image " + LinearTransDTI + " -f " + LoopScalarMeasurement
        logger("[LOOP " + str(n) + "/"+str(config["m_nbLoops"])+"] [" + allcasesIDs[case] + "] [Generating "+config["m_ScalarMeasurement"]+" of registered images] => $ " + GeneLoopScalarMeasurementCommand)
        pyExecuteCommandPreprocessCase(LoopScalarMeasurement,GeneLoopScalarMeasurementCommand,"dtiprocess: Generating " + config["m_ScalarMeasurement"] + " of affine registered images" ,case)
        logger("")
        case += 1 # indenting cases loop

      # FA/MA Average of registered images with ImageMath
      if config["m_nbLoops"]!=0:
        if n != int(config["m_nbLoops"]) : # this will not be done for the last lap
          ScalarMeasurementAverage = OutputPath + "/Loop" + str(n) + "/Loop" + str(n) + "_"+config["m_ScalarMeasurement"]+"Average.nrrd"
          ScalarMeasurementforAVG= OutputPath + "/Loop" + str(n) + "/" + config["m_CasesIDs"][0] + "_Loop" + str(n) + "_" + config["m_ScalarMeasurement"] + ".nrrd"
          if config["m_RegType"]==1:
            if n == 0 : ScalarMeasurementforAVG= OutputPath + "/"+config["m_CasesIDs"][0]+"_"+config["m_ScalarMeasurement"]+".nrrd"
            else : ScalarMeasurementforAVG= OutputPath + "/Loop" + str(n) + "/"+config["m_CasesIDs"][0]+"_Loop" + str(n) + "_"+config["m_ScalarMeasurement"]+".nrrd"
          else:
            ScalarMeasurementforAVG= OutputPath + "/Loop" + str(n) + "/" + config["m_CasesIDs"][0] + "_Loop" + str(n) + "_" + config["m_ScalarMeasurement"] + ".nrrd"
          AverageCommand = config["m_SoftPath"][0]+" " + ScalarMeasurementforAVG + " -outfile " + ScalarMeasurementAverage + " -avg "
          case = 1

          while case < len(allcases):
            ScalarMeasurementforAVG= OutputPath + "/Loop" + str(n) + "/" + allcasesIDs[case] + "_Loop" + str(n) + "_"+config["m_ScalarMeasurement"]+".nrrd "
            AverageCommand= AverageCommand + ScalarMeasurementforAVG
            case += 1
         
          logger("[LOOP " + str(n) + "/"+str(config["m_nbLoops"])+"] [Computing "+config["m_ScalarMeasurement"]+" Average of registered images] => $ " + AverageCommand)
          if config["m_Overwrite"]==1:
            if 1:
              if os.system(AverageCommand)!=0 : DisplayErrorAndQuit('[Loop ' + str(n) + '] dtiaverage: Computing '  + config["m_ScalarMeasurement"] + " Average of registered images")
            AtlasScalarMeasurementref = ScalarMeasurementAverage # the average becomes the reference
          else:
            if not CheckFileExists(ScalarMeasurementAverage, 0, "") :
              if os.system(AverageCommand)!=0 : DisplayErrorAndQuit('[Loop ' + str(n) + '] dtiaverage: Computing '  + config["m_ScalarMeasurement"] + " Average of registered images")
            else:
              logger("=> The file '" + ScalarMeasurementAverage + "' already exists so the command will not be executed")
            AtlasScalarMeasurementref = ScalarMeasurementAverage # the average becomes the reference
      else:
        if 1:
          ScalarMeasurementAverage = OutputPath + "/Loop" + str(n) + "/Loop" + str(n) + "_"+config["m_ScalarMeasurement"]+"Average.nrrd"
          ScalarMeasurementforAVG= OutputPath + "/Loop" + str(n) + "/" + config["m_CasesIDs"][0] + "_Loop" + str(n) + "_" + config["m_ScalarMeasurement"] + ".nrrd"
          if config["m_RegType"]==1:
            if n == 0 : ScalarMeasurementforAVG= OutputPath + "/"+config["m_CasesIDs"][0]+"_"+config["m_ScalarMeasurement"]+".nrrd"
            else : ScalarMeasurementforAVG= OutputPath + "/Loop" + str(n) + "/"+config["m_CasesIDs"][0]+"_Loop" + str(n) + "_"+config["m_ScalarMeasurement"]+".nrrd"
          else:
            ScalarMeasurementforAVG= OutputPath + "/Loop" + str(n) + "/" + config["m_CasesIDs"][0] + "_Loop" + str(n) + "_" + config["m_ScalarMeasurement"] + ".nrrd"
          AverageCommand = config["m_SoftPath"][0]+" " + ScalarMeasurementforAVG + " -outfile " + ScalarMeasurementAverage + " -avg "
          case = 1
          while case < len(allcases):
            ScalarMeasurementforAVG= OutputPath + "/Loop" + str(n) + "/" + allcasesIDs[case] + "_Loop" + str(n) + "_"+config["m_ScalarMeasurement"]+".nrrd "
            AverageCommand= AverageCommand + ScalarMeasurementforAVG
            case += 1
          logger("[LOOP " + str(n) + "/"+str(config["m_nbLoops"])+"] [Computing "+config["m_ScalarMeasurement"]+" Average of registered images] => $ " + AverageCommand) 
          if config["m_Overwrite"]==1:
            if 1:
              if os.system(AverageCommand)!=0 : DisplayErrorAndQuit('[Loop ' + str(n) + '] dtiaverage: Computing '  + config["m_ScalarMeasurement"] + " Average of registered images")
            AtlasScalarMeasurementref = ScalarMeasurementAverage # the average becomes the reference
          else:
            if not CheckFileExists(ScalarMeasurementAverage, 0, "") :
              if os.system(AverageCommand)!=0 : DisplayErrorAndQuit('[Loop ' + str(n) + '] dtiaverage: Computing '  + config["m_ScalarMeasurement"] + " Average of registered images")
  
            else:
              logger("=> The file '" + ScalarMeasurementAverage + "' already exists so the command will not be executed")
            AtlasScalarMeasurementref = ScalarMeasurementAverage # the average becomes the reference

      logger("")
      n += 1 # indenting main loop

    logger("\n============ End of Pre processing =============")



