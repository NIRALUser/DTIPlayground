
import os
import time
import sys
import json 
import argparse
import csv
import shutil
import threading
import traceback
from copy import deepcopy
from pathlib import Path 
import yaml 

import dmri.atlasbuilder.utils as utils 
import dmri.common

logger=dmri.common.logger.write


## builder class
class AtlasBuilder(object):
    def __init__(self,*args,**kwargs):
        self.configuration=None

    def configure(self,output_dir,config_path,hbuild_path,greedy_params_path,buildsequence_path=None,node=None):

        ### assertions
        assert(Path(config_path).exists())
        assert(Path(hbuild_path).exists())
        assert(Path(greedy_params_path).exists())

        ### init output directories
        projectPath=Path(output_dir).absolute().resolve(strict=False)
        scriptPath=projectPath.joinpath("scripts")
        commonPath=projectPath.joinpath('common')
        configPath=Path(config_path)
        hbuildPath=Path(hbuild_path)
        greedyParamsPath=Path(greedy_params_path)

        ### generate directories
        projectPath.mkdir(parents=True,exist_ok=True)
        commonPath.mkdir(parents=True,exist_ok=True)

        ### copy greedy params
        shutil.copy(greedyParamsPath, commonPath)

        ### generate build sequence
        buildSequence=[]
        hbuild={}
        deformSequence=[]
        numThreads=1
        if buildsequence_path is None:
            hbuild={}
            with open(hbuildPath,'r') as f:
                if hbuildPath.suffix == '.yml':
                    hbuild=yaml.safe_load(f)
                elif hbuildPath.suffix=='.json':
                    hbuild=json.load(f)
                else:
                    raise Exception("No supported file, .json or .yml can be accepted")
                hbuildPath=commonPath.joinpath('h-build.yml')
                yaml.dump(hbuild,open(hbuildPath,'w'))

            config={}
            with open(configPath,'r') as f:
                if configPath.suffix == '.yml':
                    config=yaml.safe_load(f)
                elif configPath.suffix == '.json':
                    config=json.load(f)
                else:
                    raise Exception("No supported file, .json or .yml can be accepted")
            configPath=commonPath.joinpath('config.yml')
            config['m_OutputPath']=str(projectPath)
            yaml.dump(config,open(configPath,'w'))

            numThreads=max(1,int(config["m_NbThreadsString"]))
            hbuild["config"]=config
            hbuild['config']['m_GreedyAtlasParametersTemplatePath']=str(commonPath.joinpath('GreedyAtlasParameters.xml'))

            initSequence=utils.parse_hbuild(hbuild,root_path=projectPath,root_node=node)
            buildSequence=utils.furnish_sequence(hbuild,initSequence)

            #save sequence 
            with open(commonPath.joinpath('build_sequence.yml'),'w') as f:
                yaml.dump(buildSequence,f)

            # generate scaffolding directories 
            utils.generate_directories(projectPath,buildSequence)
        else:
            with open(buildsequence,'r') as f:
                buildSequence=yaml.safe_load(f)
            numThreads=max(int(buildSequence[0]["m_NbThreadsString"]),1)

        with open(commonPath.joinpath('initial_sequence.yml'),'w') as f:
            yaml.dump(initSequence,f,indent=4)

        ## generate deformation field map
        deformInitSequence=utils.generate_deformation_track(initSequence,node=hbuild['project']['target_node'])
        deformSequence=utils.furnish_deformation_track(deformInitSequence,projectPath,buildSequence)
        inverseDeformSequence=utils.invert_deformation_track(deformSequence)

        with open(commonPath.joinpath('deformation_track.yml'),'w') as f:
            yaml.dump(deformSequence,f)
        with open(commonPath.joinpath('deformation_track_inverted.yml'),'w') as f:
            yaml.dump(inverseDeformSequence,f)   

        output={
            "buildSequence" : buildSequence,
            "hbuild":hbuild,
            "config":config,
            "deformInitSequence":deformInitSequence,
            "deformSequence":deformSequence,
            "inverseDeformSequence":inverseDeformSequence,
            "projectPath": projectPath,
            "node":node 
        }
        self.configuration=output
        return output

    @dmri.common.measure_time
    def build(self):
        assert(self.configuration is not None)
        configuration=self.configuration
        buildSequence=configuration['buildSequence']
        hbuild=configuration['hbuild']
        deformSequence=configuration['deformSequence']
        inverseDeformSequence=configuration['inverseDeformSequence']
        projectPath=configuration['projectPath']
        config=configuration['config']
        numThreads=max(1,int(config["m_NbThreadsString"]))
        node=configuration['node']

        ### atlas build begins (to be multiprocessed)
        logger("\n=============== Main Script ================")
        ## threading
        completedAtlases=[] #entry should be the node name 
        runningAtlases=[] # should have length less or equal than numTheads, entry is the node name

        def buildAtlas(conf,rt,ct): # rt : list of running threads, ct : list of completed threads, nt : number of thread (numThreads)
            prjName=conf["m_NodeName"]
            rt.append(prjName)
            self.preprocess(conf)
            self.build_atlas(conf)  
            rt.remove(prjName)
            ct.append(prjName)

        numNodes=len(buildSequence)
        while len(completedAtlases) < numNodes:
            if len(runningAtlases) < numThreads and len(buildSequence)>0:
                if utils.dependency_satisfied(hbuild,buildSequence[0]["m_NodeName"],completedAtlases):
                    cfg=buildSequence.pop(0)
                    utils.generate_results_csv(cfg)
                    threading.Thread(target=buildAtlas,args=(cfg,runningAtlases,completedAtlases)).start()
            time.sleep(1.0)

        ### copy final atals to 'final_atlas' directory
        if node is None:
            src=projectPath.joinpath("atlases/"+hbuild['project']['target_node'])
        else:
            src=projectPath.joinpath("atlases/"+node)
        dst=projectPath.joinpath("final_atlas")
        logger("Copying filed from %s to %s" %(src,dst))
        shutil.rmtree(dst)
        shutil.copytree(src,dst)

        logger("Final atlas copied into %s "% dst)
        ### Concatenate the displacement fields
        logger("\nConcatenating deformation fields")
        utils.ITKTransformTools_Concatenate(config,deformSequence)
        utils.ITKTransformTools_Concatenate_Inverse(config,inverseDeformSequence)
        utils.generate_results_csv_from_deformation_track(deformSequence,projectPath)

    @dmri.common.measure_time
    def preprocess(self,cfg):    
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
            if os.system(NameOfCmdVarToExec)!=0 : utils.DisplayErrorAndQuit('[' + allcasesIDs[case] + ']' + ErrorTxtToDisplay)
          else:
            if not utils.CheckFileExists(NameOfFileVarToTest,case, allcases[case]):
                if os.system(NameOfCmdVarToExec)!=0 : utils.DisplayErrorAndQuit('[' + allcasesIDs[case] + ']' + ErrorTxtToDisplay)
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
            if os.system(RescaleTempCommand)!=0 : utils.DisplayErrorAndQuit('ImageMath: Rescaling ' + config['m_ScalarMeasurement'] + ' template')
          else:
            if not utils.CheckFileExists(RescaleTemp, 0, "" ) :
              if os.system(RescaleTempCommand)!=0 : utils.DisplayErrorAndQuit('ImageMath: Rescaling ' + config['m_ScalarMeasurement'] + ' template')
            else : logger("=> The file \\'" + RescaleTemp + "\\' already exists so the command will not be executed")
          AtlasScalarMeasurementref= RescaleTemp

        else:
        # Filter case 1 DTI
          logger("")
          FilteredDTI= OutputPath + "/" + config['m_CasesIDs'][0] +"_filteredDTI.nrrd"
          FilterDTICommand=  config['m_SoftPath'][1] +" " + allcases[0] + " " + FilteredDTI + " --correction zero"
          logger("["+ config['m_CasesIDs'][0] +"] [Filter DTI] => $ " + FilterDTICommand)
          if config['m_Overwrite']==1 :
            if os.system(FilterDTICommand)!=0 : utils.DisplayErrorAndQuit('['+config['m_CasesIDs'][0]+'] ResampleDTIlogEuclidean: 1ow Filter DTI to remove negative values')
          else:
            if not utils.CheckFileExists(FilteredDTI, 0, "" + config["m_CasesIDs"][0] + "" ) :
              if os.system(FilterDTICommand)!=0 : utils.DisplayErrorAndQuit('['+config['m_CasesIDs'][0]+'] ResampleDTIlogEuclidean: 1 Filter DTI to remove negative values')
            else : logger("=> The file \'" + FilteredDTI + "\' already exists so the command will not be executed")

          # Cropping case 1 DTI
          if config['m_NeedToBeCropped']==1:
            croppedDTI = OutputPath + "/" + config['m_CasesIDs'][0] + "_croppedDTI.nrrd"
            CropCommand =  config['m_SoftPath'][2] + " " + FilteredDTI + " -o " + croppedDTI + " -size " + config['m_CropSize'][0] + "," + config['m_CropSize'][1] + "," + config['m_CropSize'][2] + " -v"
            logger("[" +config['m_CasesIDs'][0] + "] [Cropping DTI Image] => $ " + CropCommand)
            
            if config["m_Overwrite"]==1:
              if os.system(CropCommand)!=0 : utils.DisplayErrorAndQuit('[' + config["m_CasesIDs"][0] + '] CropDTI: Cropping DTI image')
            else:
              if not utils.CheckFileExists(croppedDTI, 0, "" + config['m_CasesIDs'][0] + "" ) :
                if os.system(CropCommand)!=0 : utils.DisplayErrorAndQuit('[' + config["m_CasesIDs"][0] + '] CropDTI: Cropping DTI image')
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
            if os.system(GeneScalarMeasurementCommand)!=0 : utils.DisplayErrorAndQuit('[ImageTest1] dtiprocess: Generating FA of DTI image')
          else : 
            if not utils.CheckFileExists(ScalarMeasurement, 0, config["m_CasesIDs"][0] ) :
              if os.system(GeneScalarMeasurementCommand)!=0 : utils.DisplayErrorAndQuit('[ImageTest1] dtiprocess: Generating FA of DTI image')
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
            if n==0 and utils.CheckFileExists( InitLinearTransMat, case, allcasesIDs[case] ) and utils.CheckFileExists( InitLinearTransTxt, case, allcasesIDs[case] ):
              logger("[WARNING] Both \'" + allcasesIDs[case] + "_InitLinearTrans.mat\' and \'" + allcasesIDs[case] + "_InitLinearTrans.txt\' have been found. The .mat file will be used.")
              AffineCommand= AffineCommand + " --initialTransform " + InitLinearTransMat
            elif n==0 and utils.CheckFileExists( InitLinearTransMat, case, allcasesIDs[case] ) : AffineCommand= AffineCommand + " --initialTransform " + InitLinearTransMat
            elif n==0 and utils.CheckFileExists( InitLinearTransTxt, case, allcasesIDs[case] ) : AffineCommand= AffineCommand + " --initialTransform " + InitLinearTransTxt
            else : AffineCommand= AffineCommand + " --initializeTransformMode "+ config["m_BFAffineTfmMode"] #useCenterOfHeadAlign"
            logger("[LOOP " + str(n) + "/"+str(config["m_nbLoops"])+"] [" + allcasesIDs[case] + "] [Affine registration with BrainsFit] => $ " + AffineCommand)
            utils.CheckFileExists( LinearTrans, case, allcasesIDs[case] ) 
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
                  if os.system(AverageCommand)!=0 : utils.DisplayErrorAndQuit('[Loop ' + str(n) + '] dtiaverage: Computing '  + config["m_ScalarMeasurement"] + " Average of registered images")
                AtlasScalarMeasurementref = ScalarMeasurementAverage # the average becomes the reference
              else:
                if not utils.CheckFileExists(ScalarMeasurementAverage, 0, "") :
                  if os.system(AverageCommand)!=0 : utils.DisplayErrorAndQuit('[Loop ' + str(n) + '] dtiaverage: Computing '  + config["m_ScalarMeasurement"] + " Average of registered images")
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
                  if os.system(AverageCommand)!=0 : utils.DisplayErrorAndQuit('[Loop ' + str(n) + '] dtiaverage: Computing '  + config["m_ScalarMeasurement"] + " Average of registered images")
                AtlasScalarMeasurementref = ScalarMeasurementAverage # the average becomes the reference
              else:
                if not utils.CheckFileExists(ScalarMeasurementAverage, 0, "") :
                  if os.system(AverageCommand)!=0 : utils.DisplayErrorAndQuit('[Loop ' + str(n) + '] dtiaverage: Computing '  + config["m_ScalarMeasurement"] + " Average of registered images")
      
                else:
                  logger("=> The file '" + ScalarMeasurementAverage + "' already exists so the command will not be executed")
                AtlasScalarMeasurementref = ScalarMeasurementAverage # the average becomes the reference

          logger("")
          n += 1 # indenting main loop

        logger("\n============ End of Pre processing =============")

    @dmri.common.measure_time
    def build_atlas(self,cfg):

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

        if not os.path.isdir(FinalResampPath + "/FinalTensors"):
          logger("\n=> Creation of the Final Tensors directory = " + FinalResampPath + "/FinalTensors")
          os.mkdir(FinalResampPath + "/FinalTensors")

        if not os.path.isdir(FinalResampPath + "/FinalDeformationFields"):
          logger("\n=> Creation of the Final Deformation Fields directory = " + FinalResampPath + "/FinalDeformationFields\n")
          os.mkdir(FinalResampPath + "/FinalDeformationFields")

        # Cases variables

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

        allcasesIDs=[]
        for i,c in enumerate(m_CasesIDs):
          allcasesIDs.append(m_CasesIDs[i])

        # GreedyAtlas Command
        utils.generateGreedyAtlasParametersFile(config)
        XMLFile= DeformPath + "/GreedyAtlasParameters.xml"
        ParsedFile= DeformPath + "/ParsedXML.xml"
        AtlasBCommand= m_SoftPath[5] + " -f " + XMLFile + " -o " + ParsedFile 
        logger("[Computing the Deformation Fields with GreedyAtlas] => $ " + AtlasBCommand)
        if m_Overwrite==1:
          if 1 :
            if os.system(AtlasBCommand)!=0 : utils.DisplayErrorAndQuit('GreedyAtlas: Computing non-linear atlas from affine registered images')

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
          if not utils.CheckFileExists(DeformPath + "/MeanImage.mhd", 0, "") :
            if os.system(AtlasBCommand)!=0 : utils.DisplayErrorAndQuit('GreedyAtlas: Computing non-linear atlas from affine registered images')
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
              utils.CheckFileExists(NewImage, case, allcasesIDs[case])
              NewHField=DeformPath + "/" + allcasesIDs[case] + "_HField.mhd"
              utils.CheckFileExists(NewHField, case, allcasesIDs[case])
              NewInvHField=DeformPath + "/" + allcasesIDs[case] + "_InverseHField.mhd"
              utils.CheckFileExists(NewInvHField, case, allcasesIDs[case])
              case += 1

        # Apply deformation fields 
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
              if os.system(FinalReSampCommand)!=0 : utils.DisplayErrorAndQuit('[' + allcasesIDs[case] + '] ResampleDTIlogEuclidean: Applying deformation fields to original DTIs')
              logger("[" + allcasesIDs[case] + "] => $ " + GeneDiffeomorphicCaseScalarMeasurementCommand)
              if os.system(GeneDiffeomorphicCaseScalarMeasurementCommand)!=0 : utils.DisplayErrorAndQuit('[' + allcasesIDs[case] + '] dtiprocess: Computing Diffeomorphic '+m_ScalarMeasurement)
              logger("[" + allcasesIDs[case] + "] => $ " + CaseDbleToFloatCommand + "\n")
              if os.system(CaseDbleToFloatCommand)!=0 : utils.DisplayErrorAndQuit('[' + allcasesIDs[case] + '] unu: Converting the final DTI images from double to float DTI')

          else:
            if not utils.CheckFileExists(FinalDTI, case, allcasesIDs[case]) :
              DiffeomorphicCaseScalarMeasurement = FinalPath + "/" + allcasesIDs[case] + "_Diffeomorphic"+m_ScalarMeasurement+".nrrd"
              if m_ScalarMeasurement=="FA":
                GeneDiffeomorphicCaseScalarMeasurementCommand=m_SoftPath[3]+" --scalar_float --dti_image " + FinalDTI + " -f " + DiffeomorphicCaseScalarMeasurement
              else:
                GeneDiffeomorphicCaseScalarMeasurementCommand=m_SoftPath[3]+" --scalar_float --dti_image " + FinalDTI + " -m " + DiffeomorphicCaseScalarMeasurement
              CaseDbleToFloatCommand=m_SoftPath[8] +" convert -t float -i " + FinalDTI + " | " + m_SoftPath[8] +" save -f nrrd -e gzip -o " + FinalPath + "/" + allcasesIDs[case] + "_DiffeomorphicDTI_float.nrrd"
              if os.system(FinalReSampCommand)!=0 : utils.DisplayErrorAndQuit('[' + allcasesIDs[case] + '] ResampleDTIlogEuclidean: Applying deformation fields to original DTIs')
              logger("[" + allcasesIDs[case] + "] => $ " + GeneDiffeomorphicCaseScalarMeasurementCommand)
              if os.system(GeneDiffeomorphicCaseScalarMeasurementCommand)!=0 : utils.DisplayErrorAndQuit('[' + allcasesIDs[case] + '] dtiprocess: Computing Diffeomorphic '+m_ScalarMeasurement)
              logger("[" + allcasesIDs[case] + "] => $ " + CaseDbleToFloatCommand + "\n")
              if os.system(CaseDbleToFloatCommand)!=0 : utils.DisplayErrorAndQuit('[' + allcasesIDs[case] + '] unu: Converting the final DTI images from double to float DTI')

            else : logger("=> The file \'" + FinalDTI + "\' already exists so the command will not be executed")
          case += 1

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

        if m_Overwrite==1 or not utils.CheckFileExists(DTIAverage, 0, "") : 
        # Computing some images from the final DTI with dtiprocess
          FA= FinalPath + "/DiffeomorphicAtlasFA.nrrd"
          cFA= FinalPath + "/DiffeomorphicAtlasColorFA.nrrd"
          RD= FinalPath + "/DiffeomorphicAtlasRD.nrrd"
          MD= FinalPath + "/DiffeomorphicAtlasMD.nrrd"
          AD= FinalPath + "/DiffeomorphicAtlasAD.nrrd"
          GeneScalarMeasurementCommand=m_SoftPath[3] + " --scalar_float --dti_image " + DTIAverage + " -f " + FA + " -m " + MD + " --color_fa_output " + cFA + " --RD_output " + RD + " --lambda1_output " + AD
          DbleToFloatCommand=m_SoftPath[8]+" convert -t float -i " + DTIAverage + " | " + m_SoftPath[8] + " save -f nrrd -e gzip -o " + FinalPath + "/DiffeomorphicAtlasDTI_float.nrrd"

          if os.system(AverageCommand)!=0 : utils.DisplayErrorAndQuit('dtiaverage: Computing the final DTI average')
          logger("[Computing some images from the final DTI with dtiprocess] => $ " + GeneScalarMeasurementCommand)
          if os.system(GeneScalarMeasurementCommand)!=0 : utils.DisplayErrorAndQuit('dtiprocess: Computing Diffeomorphic FA, color FA, MD, RD and AD')
          logger("[Computing some images from the final DTI with dtiprocess] => $ " + DbleToFloatCommand)
          if os.system(DbleToFloatCommand)!=0 : utils.DisplayErrorAndQuit('unu: Converting the final DTI atlas from double to float DTI')

        else: logger("=> The file '" + DTIAverage + "' already exists so the command will not be executed")


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


          if m_Overwrite==1 or not utils.CheckFileExists(FinalDef, case, allcasesIDs[case]) :
            GlobDbleToFloatCommand=m_SoftPath[8]+" convert -t float -i " + FinalDef + " | "+m_SoftPath[8]+" save -f nrrd -e gzip -o " + FinalResampPath + "/First_Resampling/" + allcasesIDs[case] + "_DeformedDTI_float.nrrd"

            if os.system(GlobalDefFieldCommand)!=0 : utils.DisplayErrorAndQuit('[' + allcasesIDs[case] + '] DTI-Reg: Computing global deformation fields')
            logger("\n[" + allcasesIDs[case] + "] [Converting the deformed images from double to float DTI] => $ " + GlobDbleToFloatCommand)
            if os.system(GlobDbleToFloatCommand)!=0 : utils.DisplayErrorAndQuit('[' + allcasesIDs[case] + '] unu: Converting the deformed images from double to float DTI')

          else:
            logger("=> The file '" + FinalDef + "' already exists so the command will not be executed")
          case += 1


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


          if m_Overwrite==1 or not utils.CheckFileExists(DTIAverage2, 0, ""): 
          # Computing some images from the final DTI with dtiprocess
            FA2= FinalResampPath + "/Second_Resampling/" +IterDir+ "/FinalAtlasFA.nrrd"
            cFA2= FinalResampPath +"/Second_Resampling/" +IterDir+ "/FinalAtlasColorFA.nrrd"
            RD2= FinalResampPath + "/Second_Resampling/" +IterDir+"/FinalAtlasRD.nrrd"
            MD2= FinalResampPath + "/Second_Resampling/" +IterDir+"/FinalAtlasMD.nrrd"
            AD2= FinalResampPath + "/Second_Resampling/" +IterDir+"/FinalAtlasAD.nrrd"
            GeneScalarMeasurementCommand2=m_SoftPath[3]+" --scalar_float --dti_image " + DTIAverage2 + " -f " + FA2 + " -m " + MD2 + " --color_fa_output " + cFA2 + " --RD_output " + RD2 + " --lambda1_output " + AD2
            DbleToFloatCommand2=m_SoftPath[8]+" convert -t float -i " + DTIAverage2 + " | "+m_SoftPath[8]+" save -f nrrd -e gzip -o " + FinalResampPath + "/Second_Resampling/" +IterDir+ "/FinalAtlasDTI_float.nrrd"

            if os.system(AverageCommand2)!=0 : utils.DisplayErrorAndQuit('dtiaverage: Recomputing the final DTI average')
            logger("[Computing some images from the final DTI with dtiprocess] => $ " + GeneScalarMeasurementCommand2)
            if os.system(GeneScalarMeasurementCommand2)!=0 : utils.DisplayErrorAndQuit('dtiprocess: Recomputing final FA, color FA, MD, RD and AD')
            logger("[Computing some images from the final DTI with dtiprocess] => $ " + DbleToFloatCommand2)
            if os.system(DbleToFloatCommand2)!=0 : utils.DisplayErrorAndQuit('unu: Converting the final resampled DTI atlas from double to float DTI')

          else:
            logger("=> The file '" + DTIAverage2 + "' already exists so the command will not be executed")

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

            if m_Overwrite==1 or not utils.CheckFileExists(FinalDef2, case, allcasesIDs[case])  :
              SecondResampRecomputed[case] = 1
              DTIRegCaseScalarMeasurement = FinalResampPath + "/Second_Resampling/" + IterDir + allcasesIDs[case] + "_FinalDeformed"+m_ScalarMeasurement+".nrrd"
              if m_ScalarMeasurement=="FA":
                GeneDTIRegCaseScalarMeasurementCommand=m_SoftPath[3]+" --scalar_float --dti_image " + FinalDef2 + " -f " + DTIRegCaseScalarMeasurement
              else:
                GeneDTIRegCaseScalarMeasurementCommand=m_SoftPath[3]+" --scalar_float --dti_image " + FinalDef2 + " -m " + DTIRegCaseScalarMeasurement

              GlobDbleToFloatCommand2=m_SoftPath[8]+" convert -t float -i " + FinalDef2 + " | "+m_SoftPath[8]+" save -f nrrd -e gzip -o " + FinalResampPath + "/Second_Resampling/" + IterDir +  allcasesIDs[case] + "_FinalDeformedDTI_float.nrrd"
              
              if os.system(GlobalDefFieldCommand2)!=0 : utils.DisplayErrorAndQuit('[' + allcasesIDs[case] + '] DTI-Reg: Computing global deformation fields')
              logger("\n[" + allcasesIDs[case] + "] [Converting the deformed images from double to float DTI] => $ " + GlobDbleToFloatCommand2)
              if os.system(GlobDbleToFloatCommand2)!=0 : utils.DisplayErrorAndQuit('[' + allcasesIDs[case] + '] unu: Converting the deformed images from double to float DTI')
              logger("\n[" + allcasesIDs[case] + "] [Computing DTIReg "+m_ScalarMeasurement+"] => $ " + GeneDTIRegCaseScalarMeasurementCommand)
              if os.system(GeneDTIRegCaseScalarMeasurementCommand)!=0 : utils.DisplayErrorAndQuit('[' + allcasesIDs[case] + '] dtiprocess: Computing DTIReg '+m_ScalarMeasurement)

            else:
              logger("=> The file '" + FinalDef2 + "' already exists so the command will not be executed")
            case += 1

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
            if utils.CheckFileExists(GlobalDefField2, case, allcasesIDs[case]) :
              shutil.copy(GlobalDefField2, NewGlobalDefField2)
            InverseGlobalDefField2 = FinalResampPath + "/Second_Resampling/" + LastIterDir + allcasesIDs[case] + "_InverseGlobalDisplacementField.nrrd"
            NewInverseGlobalDefField2 = FinalResampPath + "/FinalDeformationFields/" + allcasesIDs[case] + "_InverseGlobalDisplacementField.nrrd"
            if utils.CheckFileExists(InverseGlobalDefField2, case, allcasesIDs[case]) :
              shutil.copy(InverseGlobalDefField2, NewInverseGlobalDefField2)
            FinalDef2 = FinalResampPath + "/Second_Resampling/" + LastIterDir+allcasesIDs[case] + "_FinalDeformedDTI.nrrd"
            NewFinalDef2 = FinalResampPath + "/FinalTensors/" + allcasesIDs[case] + "_FinalDeformedDTI.nrrd"
            if utils.CheckFileExists(FinalDef2, case, allcasesIDs[case]) :
              shutil.copy(FinalDef2, NewFinalDef2)
            FinalDef2f = FinalResampPath + "/Second_Resampling/" + LastIterDir + allcasesIDs[case] + "_FinalDeformedDTI_float.nrrd"
            NewFinalDef2f = FinalResampPath + "/FinalTensors/" + allcasesIDs[case] + "_FinalDeformedDTI_float.nrrd"
            if utils.CheckFileExists(FinalDef2f, case, allcasesIDs[case]) :
              shutil.copy(FinalDef2f, NewFinalDef2f)
            DTIRegCaseScalarMeasurement = FinalResampPath + "/Second_Resampling/" + LastIterDir + allcasesIDs[case] + "_FinalDeformed"+m_ScalarMeasurement+".nrrd"
            NewDTIRegCaseScalarMeasurement = FinalResampPath + "/FinalTensors/" + allcasesIDs[case] + "_FinalDeformed"+m_ScalarMeasurement+".nrrd"
            if utils.CheckFileExists(DTIRegCaseScalarMeasurement, case, allcasesIDs[case]) :
              shutil.copy(DTIRegCaseScalarMeasurement, NewDTIRegCaseScalarMeasurement)
          case += 1

        # Copy final atlas components to FinalAtlasPath directory

        logger("Copying Final atlas components to " + FinalAtlasPath)
        shutil.rmtree(FinalAtlasPath)
        shutil.copytree(FinalResampPath+"/"+"/Second_Resampling/"+LastIterDir,FinalAtlasPath)
        shutil.copytree(FinalResampPath+"/FinalDeformationFields",FinalAtlasPath+"/FinalDeformationFields")
        shutil.copytree(FinalResampPath+"/FinalTensors",FinalAtlasPath+"/FinalTensors")

        logger("\n============ End of Atlas Building =============")







