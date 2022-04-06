
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

import dtiplayground.dmri.atlasbuilder.utils as utils 
import dtiplayground.dmri.common
import dtiplayground.dmri.common.tools as ext_tools 

logger=dtiplayground.dmri.common.logger.write


## builder class
class AtlasBuilder(object):
    def __init__(self,*args,**kwargs):
        self.configuration=None  ## configuration (build, params, ...)
        self.tools={}  #external tools

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

            hbuild["config"]=config
            hbuild['config']['m_GreedyAtlasParametersTemplatePath']=str(commonPath.joinpath('GreedyAtlasParameters.xml'))

            initSequence=utils.parse_hbuild(hbuild,root_path=projectPath,root_node=node)
            buildSequence=utils.furnish_sequence(hbuild,initSequence)

            #save sequence 
            with open(commonPath.joinpath('build_sequence.yml'),'w') as f:
                yaml.dump(buildSequence,f)
        else:
            with open(buildsequence,'r') as f:
                buildSequence=yaml.safe_load(f)
        
        numThreads=max(int(buildSequence[0]["m_NbThreadsString"]),1)
        logger("Loading external tool settings",dtiplayground.dmri.common.Color.INFO)
        ### init external toolset
        tool_list=['ImageMath','ResampleDTIlogEuclidean','CropDTI','DTIProcess','BRAINSFit','GreedyAtlas','DTIAverage','DTIReg','UNU','ITKTransformTools']
        tool_pairs=list(zip(tool_list,config['m_SoftPath']))
        tool_instances=list(map(lambda x: getattr(ext_tools,x[0])(x[1]),tool_pairs))
        self.tools=dict(zip(tool_list,tool_instances))
        # generate scaffolding directories 
        utils.generate_directories(projectPath,buildSequence)

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

    @dtiplayground.dmri.common.measure_time
    def build(self):
        assert(self.configuration is not None)
        configuration=self.configuration
        buildSequence=configuration['buildSequence']
        hbuild=configuration['hbuild']
        projectPath=configuration['projectPath']
        config=configuration['config']
        numThreads=max(1,int(config["m_NbThreadsString"]))

        ### atlas build begins (to be multiprocessed)
        logger("\n=============== Main Script ================")
        ## threading
        completedAtlases=[] #entry should be the node name 
        runningAtlases=[] # should have length less or equal than numTheads, entry is the node name
        failedAtlases=[]

        def buildAtlas(conf,rt,ct,ft): # rt : list of running threads, ct : list of completed threads, ft: failed threads
            try:
              prjName=conf["m_NodeName"]
              rt.append(prjName)
              self.preprocess(conf)
              self.build_atlas(conf)  
              rt.remove(prjName)
              ct.append(prjName)
            except Exception as e:
              logger("Exception at {}".format(str(e)))
              msg=traceback.format_exc()
              logger("{}".format(msg))
              rt.remove(prjName)
              ft.append(prjName)
              

        numNodes=len(buildSequence)
        threads=[]
        while len(completedAtlases) < numNodes:
            if len(runningAtlases) < numThreads and len(buildSequence)>0:
                if utils.dependency_satisfied(hbuild,buildSequence[0]["m_NodeName"],completedAtlases):
                    cfg=buildSequence.pop(0)
                    utils.generate_results_csv(cfg)
                    th=threading.Thread(target=buildAtlas,args=(cfg,runningAtlases,completedAtlases,failedAtlases))
                    threads.append(th)
                    th.start()
            if len(failedAtlases)>0:
              logger("There is a failed thread.Exiting...",dtiplayground.dmri.common.Color.ERROR)
              raise Exception("Error occurred in one of the threads")
            time.sleep(1.0)

        ## Postprocess
        self.postprocess()
        return True

    @dtiplayground.dmri.common.measure_time
    def preprocess(self,cfg):    
        config=cfg 
        ext_tools=deepcopy(self.tools) ### for thread safe

        logger("\n============ Pre processing =============")
        
        # Files Paths
        allcases = config['m_CasesPath']
        allcasesIDs = config['m_CasesIDs'] 
        OutputPath= Path(config['m_OutputPath']).joinpath("1_Affine_Registration")
        AtlasScalarMeasurementref=None 
        overwrite= config['m_Overwrite']==1
        needToCrop= config['m_NeedToBeCropped']==1

        AtlasScalarMeasurementref= config['m_TemplatePath'] 
        if config['m_RegType']==1:
          AtlasScalarMeasurementref= OutputPath.joinpath(config['m_CasesIDs'][0] + '_'+ config['m_ScalarMeasurement'] + ".nrrd").__str__() #"/ImageTest1_FA.nrrd" #the reference will be the first case for the first loop
        
        # Create directory for temporary files
        OutputPath.mkdir(parents=True,exist_ok=True)
        logger("\n=> Creation of the affine directory = " + OutputPath.__str__())

        # Creating template by processing Case 1 DTI
        ScalarMeasurement=config['m_ScalarMeasurement']

        if config['m_RegType']==0:
          # Rescaling template
          RescaleTemp= OutputPath.joinpath(config['m_ScalarMeasurement'] + "Template_Rescaled.nrrd").__str__()
          if overwrite or (not utils.CheckFileExists(RescaleTemp,0,"")):
            sp_out=ext_tools['ImageMath'].rescale(AtlasScalarMeasurementref,RescaleTemp,rescale=[0,10000])
          else : logger("=> The file \\'" + RescaleTemp + "\\' already exists so the command will not be executed")
          AtlasScalarMeasurementref= RescaleTemp
        else:
        # Filter case 1 DTI
          FilteredDTI= OutputPath.joinpath(config['m_CasesIDs'][0] +"_filteredDTI.nrrd").__str__()
          if overwrite or (not utils.CheckFileExists(FilteredDTI, 0, "" + config["m_CasesIDs"][0] + "" ) ):
            sp_out=ext_tools['ResampleDTIlogEuclidean'].filter_dti(allcases[0],FilteredDTI,'zero')
          else : logger("=> The file \'" + FilteredDTI + "\' already exists so the command will not be executed")

          # Cropping case 1 DTI
          if needToCrop:
            croppedDTI = OutputPath.joinpath(config['m_CasesIDs'][0] + "_croppedDTI.nrrd").__str__()
            if overwrite or (not utils.CheckFileExists(croppedDTI, 0, "" + config['m_CasesIDs'][0] + "" )):
              sp_out=ext_tools['CropDTI'].crop(FilteredDTI,croppedDTI,size=config['m_CropSize'])
            else: logger("=> The file '" + croppedDTI + "' already exists so the command will not be executed")

          # Generating case 
          DTI= allcases[0]
          if needToCrop:
            DTI= OutputPath.joinpath(config['m_CasesIDs'][0]+"_croppedDTI.nrrd").__str__()

          ScalarMeasurement= OutputPath.joinpath(config['m_CasesIDs'][0] + "_" + config['m_ScalarMeasurement']+".nrrd").__str__()
          if overwrite or (not utils.CheckFileExists(ScalarMeasurement, 0, config["m_CasesIDs"][0] )) :
            sp_out=ext_tools['DTIProcess'].measure_scalars(DTI,ScalarMeasurement,scalar_type=config['m_ScalarMeasurement'])
          else : logger("=> The file \'" + ScalarMeasurement + "\' already exists so the command will not be executed")
            
        # Affine Registration and Normalization Loop
        n = 0
        while n <= config['m_nbLoops'] : 
          # if not os.path.isdir(OutputPath.joinpath("Loop" + str(n)).__str__()):
          OutputPath.joinpath("Loop"+str(n)).mkdir(exist_ok=True)
          # Cases Loop
          case= 0
          if config["m_RegType"]==1: 
            case = (n==0) # (n==0) -> bool: =1(true) =0(false) : the first case is the reference for the first loop so it will not be normalized or registered (it is cropped and FAed before the loop)

          while case < len(allcases):
            if n==0: # Filtering and Cropping DTI and Generating FA are only part of the first loop
               # Filter DTI
              # ResampleDTIlogEuclidean does by default a correction of tensor values by setting the negative values to zero
              FilteredDTI= OutputPath.joinpath(allcasesIDs[case] + "_filteredDTI.nrrd").__str__()
              if overwrite or (not Path(FilteredDTI).exists()):
                sp_out=ext_tools['ResampleDTIlogEuclidean'].filter_dti(allcases[case],FilteredDTI,correction='zero')
              else: logger("=> The file \'" + FilteredDTI + "\' already exists so the command will not be executed")
              if needToCrop:
                croppedDTI=OutputPath.joinpath(allcasesIDs[case] + "_croppedDTI.nrrd").__str__()
                if overwrite or (not Path(croppedDTI).exists()):
                  sp_out=ext_tools['CropDTI'].crop(FilteredDTI,croppedDTI,size=config['m_CropSize'])
                else: logger("=> The file \'" + croppedDTI + "\' already exists so the command will not be executed")
              # Generating FA/MD.
              DTI= allcases[case]
              if needToCrop:
                DTI=OutputPath.joinpath(allcasesIDs[case] + "_croppedDTI.nrrd").__str__()

              ScalarMeasurement= OutputPath.joinpath(allcasesIDs[case] + "_" + config["m_ScalarMeasurement"] + ".nrrd").__str__()
              if overwrite or (not Path(ScalarMeasurement).exists()):
                sp_out=ext_tools['DTIProcess'].measure_scalars(DTI,ScalarMeasurement,scalar_type=config['m_ScalarMeasurement'])
              else: logger("=> The file \'" + ScalarMeasurement + "\' already exists so the command will not be executed")
            # Normalization
            ScalarMeasurement= OutputPath.joinpath(allcasesIDs[case] + "_"+config["m_ScalarMeasurement"]+".nrrd").__str__()
            NormScalarMeasurement= OutputPath.joinpath("Loop" + str(n)).joinpath(allcasesIDs[case] + "_Loop" + str(n) + "_Norm"+config["m_ScalarMeasurement"]+".nrrd").__str__()
            if overwrite or (not Path(NormScalarMeasurement).exists()):
              sp_out=ext_tools['ImageMath'].normalize(ScalarMeasurement,NormScalarMeasurement,AtlasScalarMeasurementref)
            else: logger("=> The file \'" + NormScalarMeasurement + "\' already exists so the command will not be executed")

            # Affine registration with BrainsFit
            NormScalarMeasurement= OutputPath.joinpath("Loop" + str(n)).joinpath(allcasesIDs[case] + "_Loop" + str(n) + "_Norm"+config["m_ScalarMeasurement"]+".nrrd").__str__()
            LinearTranstfm= OutputPath.joinpath("Loop" + str(n)).joinpath(allcasesIDs[case] + "_Loop" + str(n) + "_LinearTrans.txt").__str__()
            LinearTrans= OutputPath.joinpath("Loop" + str(n)).joinpath(allcasesIDs[case] + "_Loop" + str(n) + "_LinearTrans_"+config["m_ScalarMeasurement"]+".nrrd").__str__()
            InitLinearTransTxt= OutputPath.joinpath(allcasesIDs[case] + "_InitLinearTrans.txt").__str__()
            InitLinearTransMat= OutputPath.joinpath(allcasesIDs[case] + "_InitLinearTrans.mat").__str__()
            InitTrans=InitLinearTransMat
            if n==0 and utils.CheckFileExists( InitLinearTransMat, case, allcasesIDs[case] ) and utils.CheckFileExists( InitLinearTransTxt, case, allcasesIDs[case] ):
              logger("[WARNING] Both \'" + allcasesIDs[case] + "_InitLinearTrans.mat\' and \'" + allcasesIDs[case] + "_InitLinearTrans.txt\' have been found. The .mat file will be used.")              
            elif n==0 and utils.CheckFileExists( InitLinearTransMat, case, allcasesIDs[case] ) : 
              pass 
            elif n==0 and utils.CheckFileExists( InitLinearTransTxt, case, allcasesIDs[case] ) : 
              InitTrans=InitLinearTransTxt
            else : 
              InitTrans=None
            if overwrite or (not Path(LinearTranstfm).exists()) or (not Path(LinearTrans).exists()):
              sp_out=ext_tools['BRAINSFit'].affine_registration(fixed_path=AtlasScalarMeasurementref,
                                                                 moving_path=NormScalarMeasurement,
                                                                 output_path=LinearTrans ,
                                                                 output_transform_path=LinearTranstfm,
                                                                 initial_transform_path=InitTrans,
                                                                 transform_mode=config['m_BFAffineTfmMode']
                                                                 )
            else: logger("=> The file \'" + LinearTranstfm + "\' already exists so the command will not be executed")

            # Implementing the affine registration
            LinearTranstfm= OutputPath.joinpath("Loop" + str(n)).joinpath(allcasesIDs[case] + "_Loop" + str(n) + "_LinearTrans.txt").__str__()
            LinearTransDTI= OutputPath.joinpath("Loop" + str(n)).joinpath(allcasesIDs[case] + "_Loop" + str(n) + "_LinearTrans_DTI.nrrd").__str__()
            originalDTI= allcases[case]
            if needToCrop:
              originalDTI= OutputPath.joinpath(allcasesIDs[case] + "_croppedDTI.nrrd").__str__()
            if overwrite or (not Path(LinearTransDTI).exists()):
              sp_out=ext_tools['ResampleDTIlogEuclidean'].implement_affine_registration(originalDTI,LinearTransDTI,LinearTranstfm,AtlasScalarMeasurementref)
            else: logger("=> The file \'" + LinearTransDTI + "\' already exists so the command will not be executed")
            # Generating FA/MA of registered images
            LinearTransDTI= OutputPath.joinpath("Loop" + str(n)).joinpath(allcasesIDs[case] + "_Loop" + str(n) + "_LinearTrans_DTI.nrrd").__str__()
            if n == config["m_nbLoops"] : LoopScalarMeasurement= OutputPath.joinpath("Loop"+str(n)).joinpath(allcasesIDs[case] + "_Loop"+ str(n)+"_Final"+config["m_ScalarMeasurement"]+".nrrd").__str__() # the last FA will be the Final output
            else : LoopScalarMeasurement= OutputPath.joinpath("Loop" + str(n)).joinpath(allcasesIDs[case] + "_Loop" + str(n) + "_"+config["m_ScalarMeasurement"]+".nrrd").__str__()
            
            if overwrite or (not Path(LoopScalarMeasurement).exists()):
                sp_out=ext_tools['DTIProcess'].measure_scalars(LinearTransDTI,LoopScalarMeasurement,scalar_type=config['m_ScalarMeasurement'])
            else: logger("=> The file \'" + LoopScalarMeasurement + "\' already exists so the command will not be executed")
            case += 1 # indenting cases loop

          # FA/MA Average of registered images with ImageMath
          # if config["m_nbLoops"]!=0:
          if n != int(config["m_nbLoops"]) : # this will not be done for the last lap
            ScalarMeasurementAverage = OutputPath.joinpath("Loop" + str(n)).joinpath("Loop" + str(n) + "_"+config["m_ScalarMeasurement"]+"Average.nrrd").__str__()
            ScalarMeasurementforAVG= OutputPath.joinpath("Loop" + str(n)).joinpath(config["m_CasesIDs"][0] + "_Loop" + str(n) + "_" + config["m_ScalarMeasurement"] + ".nrrd").__str__()
            if config["m_RegType"]==1:
              if n == 0 : ScalarMeasurementforAVG= OutputPath.joinpath(config["m_CasesIDs"][0]+"_"+config["m_ScalarMeasurement"]+".nrrd").__str__()
              else : ScalarMeasurementforAVG= OutputPath.joinpath("Loop" + str(n)).joinpath(config["m_CasesIDs"][0]+"_Loop" + str(n) + "_"+config["m_ScalarMeasurement"]+".nrrd").__str__()
            else:
              ScalarMeasurementforAVG= OutputPath.joinpath("Loop" + str(n)).joinpath(config["m_CasesIDs"][0] + "_Loop" + str(n) + "_" + config["m_ScalarMeasurement"] + ".nrrd").__str__()
          
            case = 1
            ScalarMeasurementList=[]
            ScalarMeasurementList.append(ScalarMeasurementforAVG)
            while case < len(allcases):
              ScalarMeasurementforAVG= OutputPath.joinpath("Loop" + str(n)).joinpath(allcasesIDs[case] + "_Loop" + str(n) + "_"+config["m_ScalarMeasurement"]+".nrrd").__str__()                
              ScalarMeasurementList.append(ScalarMeasurementforAVG)
              case += 1             
            if overwrite or (not utils.CheckFileExists(ScalarMeasurementAverage, 0, "")):
              sp_out=ext_tools['ImageMath'].average(ScalarMeasurementList[0],ScalarMeasurementAverage,ScalarMeasurementList[1:])
              AtlasScalarMeasurementref = ScalarMeasurementAverage # the average becomes the reference
            else:
              logger("=> The file '" + ScalarMeasurementAverage + "' already exists so the command will not be executed")
              AtlasScalarMeasurementref = ScalarMeasurementAverage # the average becomes the reference
          n += 1 # indenting main loop

        logger("\n============ End of Pre processing =============")

    @dtiplayground.dmri.common.measure_time
    def build_atlas(self,cfg):
        ext_tools=deepcopy(self.tools) ### for thread safe
        config=cfg

        m_OutputPath=config["m_OutputPath"]
        m_ScalarMeasurement=config["m_ScalarMeasurement"]
        # m_GridAtlasCommand=config["m_GridAtlasCommand"]
        #m_RegType=config["m_RegType"]
        m_Overwrite=config["m_Overwrite"]
        #m_useGridProcess=config["m_useGridProcess"]
        m_SoftPath=config["m_SoftPath"]
        m_nbLoops=config["m_nbLoops"]
        m_TensTfm=config["m_TensTfm"]
        #m_TemplatePath=config["m_TemplatePath"]
        #m_BFAffineTfmMode=config["m_BFAffineTfmMode"]
        m_CasesIDs=config["m_CasesIDs"]
        m_CasesPath=config["m_CasesPath"]
        #m_CropSize=config["m_CropSize"]
        #m_DTIRegExtraPath=config["m_DTIRegExtraPath"]
        m_DTIRegOptions=config["m_DTIRegOptions"]
        # m_GridAtlasCommand=config["m_GridAtlasCommand"]
        # m_GridGeneralCommand=config["m_GridGeneralCommand"]
        m_InterpolLogOption=config["m_InterpolLogOption"]
        m_InterpolOption=config["m_InterpolOption"]
        m_InterpolType=config["m_InterpolType"]
        #m_NbThreadsString=config["m_NbThreadsString"]
        m_NeedToBeCropped=config["m_NeedToBeCropped"]
        m_PythonPath=config["m_PythonPath"]
        m_TensInterpol=config["m_TensInterpol"]
        m_nbLoopsDTIReg=config["m_nbLoopsDTIReg"]

        ### To be removed
        if m_nbLoopsDTIReg is None: m_nbLoopsDTIReg=1

        logger("\n============ Atlas Building =============")

        # Files Paths
        AffinePath=Path(m_OutputPath).joinpath("1_Affine_Registration")
        DeformPath=Path(m_OutputPath).joinpath("2_NonLinear_Registration")
        FinalPath= Path(m_OutputPath).joinpath("3_Diffeomorphic_Atlas")
        FinalResampPath= Path(m_OutputPath).joinpath("4_Final_Resampling")
        FinalAtlasPath= Path(m_OutputPath).joinpath("5_Final_Atlas")

        DeformPath.mkdir(exist_ok=True)
        FinalPath.mkdir(exist_ok=True)
        FinalResampPath.mkdir(exist_ok=True)
        FinalResampPath.joinpath("First_Resampling").mkdir(exist_ok=True)
        FinalResampPath.joinpath("Second_Resampling").mkdir(exist_ok=True)
        FinalResampPath.joinpath("FinalTensors").mkdir(exist_ok=True)
        FinalResampPath.joinpath("FinalDeformationFields").mkdir(exist_ok=True)
        FinalAtlasPath.mkdir(exist_ok=True)
        

# 1 Get Affine information from AffinePath
        # Cases variables
        alltfms=[]
        for i,c in enumerate(m_CasesPath):
          alltfms.append(AffinePath.joinpath("Loop"+str(m_nbLoops)).joinpath(m_CasesIDs[i] + "_Loop" + str(m_nbLoops) +"_LinearTrans.txt").__str__())
        allcases=[]
        if m_NeedToBeCropped==1:
          for i,c in enumerate(m_CasesPath):
            allcases.append(AffinePath.joinpath(m_CasesIDs[i] + "_croppedDTI.nrrd").__str__())
        else:
          for i,c in enumerate(m_CasesPath):
            allcases.append(m_CasesPath[i])
        allcasesIDs=[]
        for i,c in enumerate(m_CasesIDs):
          allcasesIDs.append(m_CasesIDs[i])

# 2 NonLinear_Registration (DeformPath)
        # GreedyAtlas Command
        utils.generateGreedyAtlasParametersFile(config)
        XMLFile= DeformPath.joinpath("GreedyAtlasParameters.xml").__str__()
        ParsedFile= DeformPath.joinpath("ParsedXML.xml").__str__()
        if m_Overwrite==1 or (not utils.CheckFileExists(DeformPath.joinpath("MeanImage.mhd").__str__(), 0, "")):
          sp_out=ext_tools['GreedyAtlas'].compute_deformation_fields(XMLFile,ParsedFile)
          case = 0
          while case < len(allcases): # Renaming
            originalImage=DeformPath.joinpath(allcasesIDs[case] + "_Loop"+str(m_nbLoops)+"_Final"+m_ScalarMeasurement+"DefToMean.mhd").__str__()
            originalHField=DeformPath.joinpath(allcasesIDs[case] + "_Loop"+str(m_nbLoops)+"_Final"+m_ScalarMeasurement+"DefFieldImToMean.mhd").__str__()
            originalInvHField=DeformPath.joinpath(allcasesIDs[case] + "_Loop"+str(m_nbLoops)+"_Final"+m_ScalarMeasurement+"DefFieldMeanToIm.mhd").__str__()
            NewImage= DeformPath.joinpath(allcasesIDs[case] + "_NonLinearTrans_FA.mhd").__str__()
            NewHField=DeformPath.joinpath(allcasesIDs[case] + "_HField.mhd").__str__()
            NewInvHField=DeformPath.joinpath(allcasesIDs[case] + "_InverseHField.mhd").__str__()
            logger("[" + allcasesIDs[case] + "] => Renaming \'" + originalImage + "\' to \'" + NewImage + "\'")
            os.rename(originalImage,NewImage)
            logger("[" + allcasesIDs[case] + "] => Renaming \'" + originalHField + "\' to \'" + NewHField + "\'")
            os.rename(originalHField,NewHField)
            logger("[" + allcasesIDs[case] + "] => Renaming \'" + originalInvHField + "\' to \'" + NewInvHField + "\'")
            os.rename(originalInvHField,NewInvHField)
            case += 1
        else:
          logger("=> The file '" + str(DeformPath.joinpath('MeanImage.mhd')) + " already exists so the command will not be executed")
          # Renaming possible existing old named files from GreedyAtlas\n";
          case = 0
          while case < len(allcases): # Updating old names if needed\n";
            NewImage= DeformPath.joinpath(allcasesIDs[case] + "_NonLinearTrans_" + m_ScalarMeasurement + ".mhd").__str__()
            utils.CheckFileExists(NewImage, case, allcasesIDs[case])
            NewHField=DeformPath.joinpath(allcasesIDs[case] + "_HField.mhd").__str__()
            utils.CheckFileExists(NewHField, case, allcasesIDs[case])
            NewInvHField=DeformPath.joinpath(allcasesIDs[case] + "_InverseHField.mhd").__str__()
            utils.CheckFileExists(NewInvHField, case, allcasesIDs[case])
            case += 1

# 3 Diffeomorphic Atlas (FinalPath)
        # Apply deformation fields 
        case = 0
        while case < len(allcases):
          FinalDTI= FinalPath.joinpath(allcasesIDs[case] + "_DiffeomorphicDTI.nrrd").__str__()
          if m_NeedToBeCropped==1:
            originalDTI= AffinePath.joinpath(allcasesIDs[case] + "_croppedDTI.nrrd").__str__()
          else:
            originalDTI= allcases[case]
          if m_nbLoops==0:
            Ref = AffinePath.joinpath("Loop0").joinpath("Loop0_"+m_ScalarMeasurement+"Average.nrrd").__str__()
          else:
            Ref = AffinePath.joinpath("Loop" + str(m_nbLoops-1)).joinpath("Loop" + str(m_nbLoops-1) + "_" + m_ScalarMeasurement + "Average.nrrd").__str__()

          HField= DeformPath.joinpath(allcasesIDs[case] + "_HField.mhd").__str__()

          if m_Overwrite==1 or (not utils.CheckFileExists(FinalDTI, case, allcasesIDs[case])):
            DiffeomorphicCaseScalarMeasurement = FinalPath.joinpath(allcasesIDs[case] + "_Diffeomorphic"+m_ScalarMeasurement+".nrrd").__str__()
            
            sp_out=ext_tools['ResampleDTIlogEuclidean'].resample(reference_file=Ref,
                                                                   deform_field_file=HField,
                                                                   transformation_file=alltfms[case],
                                                                   moving_file=originalDTI,
                                                                   output_file=FinalDTI,
                                                                   interpolation_type=m_InterpolType,
                                                                   interpolation_option=m_InterpolOption,
                                                                   tensor_interpolation_type=m_TensInterpol,
                                                                   tensor_interpolation_option=m_InterpolLogOption,
                                                                   tensor_transform=m_TensTfm
                                                                   )

            sp_out=ext_tools['DTIProcess'].measure_scalars(inputfile=FinalDTI,
                                                            outputfile=DiffeomorphicCaseScalarMeasurement,
                                                            scalar_type=m_ScalarMeasurement,
                                                            options=['--scalar_float'])

            out_file=FinalPath.joinpath(allcasesIDs[case] + "_DiffeomorphicDTI_float.nrrd").__str__()
            sp_out=ext_tools['UNU'].convert_to_float(FinalDTI,out_file)

          else : logger("=> The file \'" + FinalDTI + "\' already exists so the command will not be executed")
          case += 1

        # DTIaverage computing
        DTIAverage = FinalPath.joinpath("DiffeomorphicAtlasDTI.nrrd").__str__()
        ListForAverage=[]
        case = 0
        while case < len(allcases):
          temp=FinalPath.joinpath(allcasesIDs[case] + "_DiffeomorphicDTI.nrrd").__str__()
          ListForAverage.append(temp)
          case += 1
        sp_out=ext_tools['DTIAverage'].average(ListForAverage,DTIAverage)

        if m_Overwrite==1 or not utils.CheckFileExists(DTIAverage, 0, "") : 
        # Computing some images from the final DTI with dtiprocess
          FA= FinalPath.joinpath("DiffeomorphicAtlasFA.nrrd").__str__()
          cFA= FinalPath.joinpath("DiffeomorphicAtlasColorFA.nrrd").__str__()
          RD= FinalPath.joinpath("DiffeomorphicAtlasRD.nrrd").__str__()
          MD= FinalPath.joinpath("DiffeomorphicAtlasMD.nrrd").__str__()
          AD= FinalPath.joinpath("DiffeomorphicAtlasAD.nrrd").__str__()
          

          sp_out=ext_tools['DTIAverage'].average(ListForAverage,DTIAverage) 
          sp_out=ext_tools['DTIProcess'].measure_scalars(inputfile=DTIAverage,
                                                outputfile=FA,
                                                scalar_type='FA',
                                                options=['--scalar_float','-m',MD,'--color_fa_output',cFA,'--RD_output',RD,'--lambda1_output',AD])
          out_file=FinalPath.joinpath("DiffeomorphicAtlasDTI_float.nrrd").__str__()
          sp_out=ext_tools['UNU'].convert_to_float(DTIAverage,out_file)

        else: logger("=> The file '" + DTIAverage + "' already exists so the command will not be executed")

# 4-1 First_Resampling (FinalResampPath) - to be multi-threaded
        # Computing global deformation fields
        case = 0
        while case < len(allcases):
          if m_NeedToBeCropped==1:
            origDTI= AffinePath.joinpath(allcasesIDs[case] + "_croppedDTI.nrrd").__str__()
          else:
            origDTI= allcases[case]
          GlobalDefField = FinalResampPath.joinpath("First_Resampling").joinpath(allcasesIDs[case] + "_GlobalDisplacementField.nrrd").__str__()
          InverseGlobalDefField = FinalResampPath.joinpath("First_Resampling").joinpath(allcasesIDs[case] + "_GlobalDisplacementField_Inverse.nrrd").__str__()
          FinalDef = FinalResampPath.joinpath("First_Resampling").joinpath(allcasesIDs[case] + "_DeformedDTI.nrrd").__str__()

          BRAINSExecDir = os.path.dirname(m_SoftPath[4])
          dtiprocessExecDir = os.path.dirname(m_SoftPath[3])
          ResampExecDir = os.path.dirname(m_SoftPath[1])
          PathList=[BRAINSExecDir,dtiprocessExecDir,ResampExecDir]

          BRAINSTempTfm = FinalResampPath.joinpath("First_Resampling").joinpath(allcasesIDs[case] + "_" + m_ScalarMeasurement + "_AffReg.txt").__str__()
          ANTSTempFileBase = FinalResampPath.joinpath("First_Resampling").joinpath(allcasesIDs[case] + "_" + m_ScalarMeasurement + "_").__str__()

          if m_Overwrite==1 or not utils.CheckFileExists(FinalDef, case, allcasesIDs[case]) :   
            sp_out=ext_tools['DTIReg'].compute_global_deformation_fields(
                                                                          fixed_volume=DTIAverage,
                                                                          moving_volume=origDTI,
                                                                          scalar_measurement=m_ScalarMeasurement,
                                                                          output_displacement_field=GlobalDefField,
                                                                          output_inverse_displacementField=InverseGlobalDefField,
                                                                          output_volume=FinalDef,
                                                                          initial_affine=alltfms[case],
                                                                          brains_transform=BRAINSTempTfm,
                                                                          ants_outbase=ANTSTempFileBase,
                                                                          program_paths=PathList,
                                                                          dti_reg_options=m_DTIRegOptions,
                                                                          options=[])
            out_file=FinalResampPath.joinpath("First_Resampling").joinpath(allcasesIDs[case] + "_DeformedDTI_float.nrrd").__str__()
            sp_out=ext_tools['UNU'].convert_to_float(FinalDef,out_file)

          else: logger("=> The file '" + FinalDef + "' already exists so the command will not be executed")
          case += 1

# 4-2 Second_Resampling 

        ### looping begins
        cnt=0
        if m_Overwrite==0:
          for i in range(m_nbLoopsDTIReg):
            if os.path.isdir(FinalResampPath.joinpath("Second_Resampling").joinpath("Loop_"+str(i)).__str__()):
              cnt=i 
          cnt=max(cnt,0)

        while cnt < m_nbLoopsDTIReg:
          logger("-----------------------------------------------------------")
          logger("Iterative Registration cycle %d / %d" % (cnt+1,m_nbLoopsDTIReg) )
          logger("------------------------------------------------------------")
          FinalResampPath.joinpath("Second_Resampling").joinpath("Loop_"+str(cnt)).mkdir(exist_ok=True)
          # dtiaverage recomputing
          IterDir="Loop_"+str(cnt)
          PrevIterDir="Loop_"+str(cnt-1)
          DTIAverage2 = FinalResampPath.joinpath("Second_Resampling").joinpath(IterDir).joinpath("FinalAtlasDTI_averaged.nrrd").__str__()

          ListForAverage=[]
          if cnt==0:
            case = 0
            while case < len(allcases):
              temp=FinalResampPath.joinpath("First_Resampling").joinpath(allcasesIDs[case] + "_DeformedDTI.nrrd").__str__()
              ListForAverage.append(temp)
              case += 1
          else: ### when iterative registration is activated
            case=0
            while case < len(allcases):
              temp=FinalResampPath.joinpath("Second_Resampling").joinpath(PrevIterDir).joinpath(allcasesIDs[case] + "_FinalDeformedDTI.nrrd").__str__()
              ListForAverage.append(temp)
              case += 1 

          if m_Overwrite==1 or not utils.CheckFileExists(DTIAverage2, 0, ""): 
          # Computing some images from the final DTI with dtiprocess
            FA2= FinalResampPath.joinpath("Second_Resampling").joinpath(IterDir).joinpath("FinalAtlasFA.nrrd").__str__()
            cFA2= FinalResampPath.joinpath("Second_Resampling").joinpath(IterDir).joinpath("FinalAtlasColorFA.nrrd").__str__()
            RD2= FinalResampPath.joinpath("Second_Resampling").joinpath(IterDir).joinpath("FinalAtlasRD.nrrd").__str__()
            MD2= FinalResampPath.joinpath("Second_Resampling").joinpath(IterDir).joinpath("FinalAtlasMD.nrrd").__str__()
            AD2= FinalResampPath.joinpath("Second_Resampling").joinpath(IterDir).joinpath("FinalAtlasAD.nrrd").__str__()

            sp_out=ext_tools['DTIAverage'].average(ListForAverage,DTIAverage2) 
            sp_out=ext_tools['DTIProcess'].measure_scalars(inputfile=DTIAverage2,
                                                  outputfile=FA2,
                                                  scalar_type='FA',
                                                  options=['--scalar_float','-m',MD2,'--color_fa_output',cFA2,'--RD_output',RD2,'--lambda1_output',AD2])

            out_file=FinalResampPath.joinpath("Second_Resampling").joinpath(IterDir).joinpath("FinalAtlasDTI_float.nrrd").__str__()
            sp_out=ext_tools['UNU'].convert_to_float(DTIAverage2,out_file)    

          else: logger("=> The file '" + DTIAverage2 + "' already exists so the command will not be executed")

          # Recomputing global deformation fields - to be multi-threaded
          SecondResampRecomputed = [0] * len(allcases) # array of 1s and 0s to know what has been recomputed to know what to copy to final folders
          case = 0
          while case < len(allcases):
            if m_NeedToBeCropped==1:
              origDTI2= AffinePath.joinpath(allcasesIDs[case] + "_croppedDTI.nrrd").__str__()
            else:
              origDTI2= allcases[case]
            GlobalDefField2 = FinalResampPath.joinpath("Second_Resampling").joinpath(IterDir).joinpath(allcasesIDs[case] + "_GlobalDisplacementField.nrrd").__str__()
            InverseGlobalDefField2 = FinalResampPath.joinpath("Second_Resampling").joinpath(IterDir).joinpath(allcasesIDs[case] + "_InverseGlobalDisplacementField.nrrd").__str__()
            FinalDef2 = FinalResampPath.joinpath("Second_Resampling").joinpath(IterDir).joinpath(allcasesIDs[case] + "_FinalDeformedDTI.nrrd").__str__()

            BRAINSExecDir = os.path.dirname(m_SoftPath[4])
            dtiprocessExecDir = os.path.dirname(m_SoftPath[3])
            ResampExecDir = os.path.dirname(m_SoftPath[1])
            PathList=[BRAINSExecDir,dtiprocessExecDir,ResampExecDir]

            BRAINSTempTfm = FinalResampPath.joinpath("First_Resampling").joinpath(allcasesIDs[case] + "_" + m_ScalarMeasurement + "_AffReg.txt").__str__()
            ANTSTempFileBase = FinalResampPath.joinpath("First_Resampling").joinpath(allcasesIDs[case] + "_" + m_ScalarMeasurement + "_").__str__()

            if m_Overwrite==1 or not utils.CheckFileExists(FinalDef2, case, allcasesIDs[case])  :
              SecondResampRecomputed[case] = 1
              DTIRegCaseScalarMeasurement = FinalResampPath.joinpath("Second_Resampling").joinpath(IterDir).joinpath(allcasesIDs[case] + "_FinalDeformed"+m_ScalarMeasurement+".nrrd").__str__()

              sp_out=ext_tools['DTIReg'].compute_global_deformation_fields(
                                                              fixed_volume=DTIAverage2,
                                                              moving_volume=origDTI2,
                                                              scalar_measurement=m_ScalarMeasurement,
                                                              output_displacement_field=GlobalDefField2,
                                                              output_inverse_displacementField=InverseGlobalDefField2,
                                                              output_volume=FinalDef2,
                                                              initial_affine=alltfms[case],
                                                              brains_transform=BRAINSTempTfm,
                                                              ants_outbase=ANTSTempFileBase,
                                                              program_paths=PathList,
                                                              dti_reg_options=m_DTIRegOptions,
                                                              options=[])

              out_file=FinalResampPath.joinpath("Second_Resampling").joinpath(IterDir).joinpath(allcasesIDs[case] + "_FinalDeformedDTI_float.nrrd").__str__()
              sp_out=ext_tools['UNU'].convert_to_float(FinalDef2,out_file)
              sp_out=ext_tools['DTIProcess'].measure_scalars(inputfile=FinalDef2,
                                                outputfile=DTIRegCaseScalarMeasurement,
                                                scalar_type=m_ScalarMeasurement,
                                                options=['--scalar_float'])

            else: logger("=> The file '" + FinalDef2 + "' already exists so the command will not be executed")
            case += 1

          ### Cleanup - delete PrevIterDir
          if cnt > 1:
            PrevPrevIterDir="Loop_"+str(cnt-2)
            DirToRemove = FinalResampPath.joinpath("Second_Resampling").joinpath(PrevPrevIterDir).__str__()
            if os.path.exists(DirToRemove):
              shutil.rmtree(DirToRemove)

          cnt+=1
        # End while cnt < m_nbLoopDTIReg

# 5 FinalAtlasPath
        # Moving final images to final folders
        logger("\n=> Moving final images to final folders")
        case = 0
        LastIterDir="Loop_"+str(m_nbLoopsDTIReg-1)

        while case < len(allcases):
          if SecondResampRecomputed[case] :
            GlobalDefField2 = FinalResampPath.joinpath("Second_Resampling").joinpath(LastIterDir).joinpath(allcasesIDs[case] + "_GlobalDisplacementField.nrrd").__str__()
            NewGlobalDefField2 = FinalResampPath.joinpath("FinalDeformationFields").joinpath(allcasesIDs[case] + "_GlobalDisplacementField.nrrd").__str__()
            if utils.CheckFileExists(GlobalDefField2, case, allcasesIDs[case]) :
              shutil.copy(GlobalDefField2, NewGlobalDefField2)
            InverseGlobalDefField2 = FinalResampPath.joinpath("Second_Resampling").joinpath(LastIterDir).joinpath(allcasesIDs[case] + "_InverseGlobalDisplacementField.nrrd").__str__()
            NewInverseGlobalDefField2 = FinalResampPath.joinpath("FinalDeformationFields").joinpath(allcasesIDs[case] + "_InverseGlobalDisplacementField.nrrd").__str__()
            if utils.CheckFileExists(InverseGlobalDefField2, case, allcasesIDs[case]) :
              shutil.copy(InverseGlobalDefField2, NewInverseGlobalDefField2)
            FinalDef2 = FinalResampPath.joinpath("Second_Resampling").joinpath(LastIterDir).joinpath(allcasesIDs[case] + "_FinalDeformedDTI.nrrd").__str__()
            NewFinalDef2 = FinalResampPath.joinpath("FinalTensors").joinpath(allcasesIDs[case] + "_FinalDeformedDTI.nrrd").__str__()
            if utils.CheckFileExists(FinalDef2, case, allcasesIDs[case]) :
              shutil.copy(FinalDef2, NewFinalDef2)
            FinalDef2f = FinalResampPath.joinpath("Second_Resampling").joinpath(LastIterDir).joinpath(allcasesIDs[case] + "_FinalDeformedDTI_float.nrrd").__str__()
            NewFinalDef2f = FinalResampPath.joinpath("FinalTensors").joinpath(allcasesIDs[case] + "_FinalDeformedDTI_float.nrrd").__str__()
            if utils.CheckFileExists(FinalDef2f, case, allcasesIDs[case]) :
              shutil.copy(FinalDef2f, NewFinalDef2f)
            DTIRegCaseScalarMeasurement = FinalResampPath.joinpath("Second_Resampling").joinpath(LastIterDir).joinpath(allcasesIDs[case] + "_FinalDeformed"+m_ScalarMeasurement+".nrrd").__str__()
            NewDTIRegCaseScalarMeasurement = FinalResampPath.joinpath("FinalTensors").joinpath(allcasesIDs[case] + "_FinalDeformed"+m_ScalarMeasurement+".nrrd").__str__()
            if utils.CheckFileExists(DTIRegCaseScalarMeasurement, case, allcasesIDs[case]) :
              shutil.copy(DTIRegCaseScalarMeasurement, NewDTIRegCaseScalarMeasurement)
          case += 1

        # Copy final atlas components to FinalAtlasPath directory

        logger("Copying Final atlas components to " + str(FinalAtlasPath))
        shutil.rmtree(FinalAtlasPath)
        shutil.copytree(FinalResampPath.joinpath("Second_Resampling").joinpath(LastIterDir),FinalAtlasPath)
        shutil.copytree(FinalResampPath.joinpath("FinalDeformationFields"),FinalAtlasPath.joinpath("FinalDeformationFields"))
        shutil.copytree(FinalResampPath.joinpath("FinalTensors"),FinalAtlasPath.joinpath("FinalTensors"))

        logger("\n============ End of Atlas Building =============")   ### after preprocessing, build atlas with non linear registrations

    @dtiplayground.dmri.common.measure_time
    def postprocess(self):
        assert(self.configuration is not None)
        configuration=self.configuration

        deformSequence=configuration['deformSequence']
        inverseDeformSequence=configuration['inverseDeformSequence']
        projectPath=configuration['projectPath']
        config=configuration['config']
        hbuild=configuration['hbuild']
        node=configuration['node']

        ### copy final atals to 'final_atlas' directory
        if node is None:
            src=projectPath.joinpath("atlases").joinpath(hbuild['project']['target_node'])
        else:
            src=projectPath.joinpath("atlases").joinpath(node)
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



