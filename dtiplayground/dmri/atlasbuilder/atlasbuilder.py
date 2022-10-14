
#
#   atlasbuilder.py 
#   2022-10-09
#   Written by SK Park, NIRAL, UNC
#
#   Atlasbuilding class under dtiplayground
#


import os
import time
import sys
import json 
import argparse
import csv
import shutil
import threading
import traceback
import copy
from pathlib import Path 
import yaml 

# import dtiplayground.dmri.atlasbuilder.utils as utils 
import dtiplayground.dmri.atlasbuilder.data as data
import dtiplayground.dmri.common
import dtiplayground.dmri.common.tools as ext_tools 
import dtiplayground.dmri.atlasbuilder.data as data
common = dtiplayground.dmri.common

class AtlasBuilder(object):
    def __init__(self,*args,**kwargs):
        kwargs.setdefault('logger', common.logger)
        self.configuration=None  ## configuration (build, params, ...)
        self.tools={}  #external tools (tool class instances)
        self.logger=kwargs['logger']
        global logger
        logger = self.logger.write

    def configure(self,output_dir,config_path,hbuild_path,greedy_path,node=None):

        ### assertions
        assert(Path(config_path).exists())
        assert(Path(hbuild_path).exists())
        assert(Path(greedy_path).exists())

        ### init output directories
        logger=self.logger.write
        projectPath=Path(output_dir).absolute().resolve(strict=False)
        scriptPath=projectPath.joinpath("scripts")
        commonPath=projectPath.joinpath('common')
        configPath=Path(config_path)
        hbuildPath=Path(hbuild_path)
        greedyPath=Path(greedy_path)
        # greedyParamsPath=Path(data.__file__).resolve().parent.joinpath('GreedyAtlasParameters.xml') 
        log_fn = projectPath.joinpath('log.txt')
        self.logger.setLogfile(str(log_fn))  
        ### generate directories
        projectPath.mkdir(parents=True,exist_ok=True)
        commonPath.mkdir(parents=False,exist_ok=True)
    
        ### basic parameter loading
        greedy = yaml.safe_load(open(greedyPath,'r'))
        hbuild = yaml.safe_load(open(hbuildPath,'r'))
        config = yaml.safe_load(open(configPath,'r'))

        ###  Tool mappings
        logger("Loading external tool settings",dtiplayground.dmri.common.Color.INFO)
        ### init external toolset
        tool_paths, m_softpath, tool_list = self.generate_software_paths()
        config['m_SoftPath'] = m_softpath
        config['m_OutputPath']=str(projectPath)
        tool_instances=list(map(lambda x: getattr(ext_tools,x[0])(x[1],logger=self.logger),tool_paths.items()))
        self.tools=dict(zip(tool_list,tool_instances))
        config['m_DTIRegExtraPath']=self.get_ants_path()
        configPath=commonPath.joinpath('config.yml')
        yaml.dump(config,open(configPath,'w'))

        ### generate build sequence

        hbuild["config"]=config
        hbuild['config']['m_GreedyAtlasParametersTemplatePath']=str(commonPath.joinpath('GreedyAtlasParameters.xml'))

        initSequence=parse_hbuild(hbuild,root_path=projectPath,root_node=node)
        buildSequence=furnish_sequence(hbuild,initSequence)

        #save sequence 
        with open(commonPath.joinpath('initial_sequence.yml'),'w') as f:
            yaml.safe_dump(initSequence,f,indent=4)
        with open(commonPath.joinpath('build_sequence.yml'),'w') as f:
            yaml.safe_dump(buildSequence,f)
        # numThreads=max(int(buildSequence[0]["m_NbThreadsString"]),1)
        generate_directories(projectPath,buildSequence)
        ## generate deformation field map
        deformInitSequence=generate_deformation_track(initSequence,node=hbuild['project']['target_node'])
        deformSequence=furnish_deformation_track(deformInitSequence,projectPath,buildSequence)
        inverseDeformSequence=invert_deformation_track(deformSequence)

        with open(commonPath.joinpath('deformation_track.yml'),'w') as f:
            yaml.dump(deformSequence,f)
        with open(commonPath.joinpath('deformation_track_inverted.yml'),'w') as f:
            yaml.dump(inverseDeformSequence,f)   

        output={
            "buildSequence" : buildSequence,
            "hbuild":hbuild,
            "config":config,
            "greedy": greedy,
            "deformInitSequence":deformInitSequence,
            "deformSequence":deformSequence,
            "inverseDeformSequence":inverseDeformSequence,
            "projectPath": projectPath,
            "node":node 
        }
        self.configuration=output
        return output

    def get_ants_path(self):
        ants_binaries = common.get_default_ants_executables()
        return Path(ants_binaries['ANTS']).parent.__str__()

    def generate_software_paths(self):
        
        tool_list=['ImageMath','ResampleDTIlogEuclidean','CropDTI','DTIProcess','BRAINSFit','GreedyAtlas','DTIAverage','DTIReg','UNU','ITKTransformTools']
        installed_tools = common.get_default_dpg_executables()
        tools_paths = {
            'ImageMath' : installed_tools['ImageMath'],
            'ResampleDTIlogEuclidean' : installed_tools['ResampleDTIlogEuclidean'],
            'CropDTI' : installed_tools['CropDTI'],
            'DTIProcess' : installed_tools['dtiprocess'],
            'BRAINSFit' : installed_tools['BRAINSFit'],
            'GreedyAtlas' : installed_tools['GreedyAtlas'],
            'DTIAverage' : installed_tools['dtiaverage'],
            'DTIReg' : installed_tools['DTI-Reg'],
            'UNU' : installed_tools['unu'],
            'ITKTransformTools' : installed_tools['ITKTransformTools'],
        }

        m_softpath = list(map(lambda x: tools_paths[x], tool_list))
        return tools_paths, m_softpath, tool_list

    @dtiplayground.dmri.common.measure_time
    def build(self):
        assert(self.configuration is not None)
        self.logger.resetLogfile()
        logger=self.logger.write
        configuration=self.configuration
        buildSequence=configuration['buildSequence']
        hbuild=configuration['hbuild']
        projectPath=configuration['projectPath']
        config=configuration['config']
        greedy=configuration['greedy']
        # numThreads=max(1,int(config["m_NbThreadsString"]))
        numProcess=max(1,int(config['m_nbParallelism']))
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
              self.build_atlas(conf,greedy)  
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
            if len(runningAtlases) < numProcess and len(buildSequence)>0:
                if dependency_satisfied(hbuild,buildSequence[0]["m_NodeName"],completedAtlases):
                    cfg=buildSequence.pop(0)
                    generate_results_csv(cfg)
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
        logger=self.logger.write
        config=cfg 
        ext_tools=copy.copy(self.tools) ### for thread safe

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
          if overwrite or (not CheckFileExists(RescaleTemp,0,"")):
            sp_out=ext_tools['ImageMath'].rescale(AtlasScalarMeasurementref,RescaleTemp,rescale=[0,10000])
          else : logger("=> The file \\'" + RescaleTemp + "\\' already exists so the command will not be executed")
          AtlasScalarMeasurementref= RescaleTemp
        else:
        # Filter case 1 DTI
          FilteredDTI= OutputPath.joinpath(config['m_CasesIDs'][0] +"_filteredDTI.nrrd").__str__()
          if overwrite or (not CheckFileExists(FilteredDTI, 0, "" + config["m_CasesIDs"][0] + "" ) ):
            sp_out=ext_tools['ResampleDTIlogEuclidean'].filter_dti(allcases[0],FilteredDTI,'zero')
          else : logger("=> The file \'" + FilteredDTI + "\' already exists so the command will not be executed")

          # Cropping case 1 DTI
          if needToCrop:
            croppedDTI = OutputPath.joinpath(config['m_CasesIDs'][0] + "_croppedDTI.nrrd").__str__()
            if overwrite or (not CheckFileExists(croppedDTI, 0, "" + config['m_CasesIDs'][0] + "" )):
              sp_out=ext_tools['CropDTI'].crop(FilteredDTI,croppedDTI,size=config['m_CropSize'])
            else: logger("=> The file '" + croppedDTI + "' already exists so the command will not be executed")

          # Generating case 
          DTI= allcases[0]
          if needToCrop:
            DTI= OutputPath.joinpath(config['m_CasesIDs'][0]+"_croppedDTI.nrrd").__str__()

          ScalarMeasurement= OutputPath.joinpath(config['m_CasesIDs'][0] + "_" + config['m_ScalarMeasurement']+".nrrd").__str__()
          if overwrite or (not CheckFileExists(ScalarMeasurement, 0, config["m_CasesIDs"][0] )) :
            sp_out=ext_tools['DTIProcess'].measure_scalars(DTI,ScalarMeasurement,scalar_type=config['m_ScalarMeasurement'])
          else : logger("=> The file \'" + ScalarMeasurement + "\' already exists so the command will not be executed")
            
        # Affine Registration and Normalization Loop
        n = 0
        while n <= int(config['m_nbLoops']) : 
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
            if n==0 and CheckFileExists( InitLinearTransMat, case, allcasesIDs[case] ) and CheckFileExists( InitLinearTransTxt, case, allcasesIDs[case] ):
              logger("[WARNING] Both \'" + allcasesIDs[case] + "_InitLinearTrans.mat\' and \'" + allcasesIDs[case] + "_InitLinearTrans.txt\' have been found. The .mat file will be used.")              
            elif n==0 and CheckFileExists( InitLinearTransMat, case, allcasesIDs[case] ) : 
              pass 
            elif n==0 and CheckFileExists( InitLinearTransTxt, case, allcasesIDs[case] ) : 
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
            if n == int(config["m_nbLoops"]) : LoopScalarMeasurement= OutputPath.joinpath("Loop"+str(n)).joinpath(allcasesIDs[case] + "_Loop"+ str(n)+"_Final"+config["m_ScalarMeasurement"]+".nrrd").__str__() # the last FA will be the Final output
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
            if overwrite or (not CheckFileExists(ScalarMeasurementAverage, 0, "")):
              sp_out=ext_tools['ImageMath'].average(ScalarMeasurementList[0],ScalarMeasurementAverage,ScalarMeasurementList[1:])
              AtlasScalarMeasurementref = ScalarMeasurementAverage # the average becomes the reference
            else:
              logger("=> The file '" + ScalarMeasurementAverage + "' already exists so the command will not be executed")
              AtlasScalarMeasurementref = ScalarMeasurementAverage # the average becomes the reference
          n += 1 # indenting main loop

        logger("\n============ End of Pre processing =============")

    @dtiplayground.dmri.common.measure_time
    def build_atlas(self,cfg, greedy):
        logger=self.logger.write
        ext_tools=copy.copy(self.tools) ### for thread safe
        config=cfg

        m_OutputPath=config["m_OutputPath"]
        m_ScalarMeasurement=config["m_ScalarMeasurement"]
        # m_GridAtlasCommand=config["m_GridAtlasCommand"]
        #m_RegType=config["m_RegType"]
        m_Overwrite=config["m_Overwrite"]
        #m_useGridProcess=config["m_useGridProcess"]
        m_SoftPath=config["m_SoftPath"]
        m_nbLoops=int(config["m_nbLoops"])
        m_TensTfm=config["m_TensTfm"]
        #m_TemplatePath=config["m_TemplatePath"]
        #m_BFAffineTfmMode=config["m_BFAffineTfmMode"]
        m_CasesIDs=config["m_CasesIDs"]
        m_CasesPath=config["m_CasesPath"]
        #m_CropSize=config["m_CropSize"]
        m_DTIRegExtraPath=config["m_DTIRegExtraPath"]
        m_DTIRegOptions=config["m_DTIRegOptions"]
        # m_GridAtlasCommand=config["m_GridAtlasCommand"]
        # m_GridGeneralCommand=config["m_GridGeneralCommand"]
        m_InterpolLogOption=config["m_InterpolLogOption"]
        m_InterpolOption=config["m_InterpolOption"]
        m_InterpolType=config["m_InterpolType"]
        # m_NbThreadsString=config["m_NbThreadsString"]
        m_NeedToBeCropped=config["m_NeedToBeCropped"]
        # m_PythonPath=config["m_PythonPath"]
        m_TensInterpol=config["m_TensInterpol"]
        m_nbLoopsDTIReg=int(config["m_nbLoopsDTIReg"])

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
        generateGreedyAtlasParametersFile(config, greedy)
        XMLFile= DeformPath.joinpath("GreedyAtlasParameters.xml").__str__()
        ParsedFile= DeformPath.joinpath("ParsedXML.xml").__str__()
        if m_Overwrite==1 or (not CheckFileExists(DeformPath.joinpath("MeanImage.mhd").__str__(), 0, "")):
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
            CheckFileExists(NewImage, case, allcasesIDs[case])
            NewHField=DeformPath.joinpath(allcasesIDs[case] + "_HField.mhd").__str__()
            CheckFileExists(NewHField, case, allcasesIDs[case])
            NewInvHField=DeformPath.joinpath(allcasesIDs[case] + "_InverseHField.mhd").__str__()
            CheckFileExists(NewInvHField, case, allcasesIDs[case])
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

          if m_Overwrite==1 or (not CheckFileExists(FinalDTI, case, allcasesIDs[case])):
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

        if m_Overwrite==1 or not CheckFileExists(DTIAverage, 0, "") : 
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
          ITKTransformToolDir = os.path.dirname(m_SoftPath[9])
          PathList=[BRAINSExecDir,m_DTIRegExtraPath, dtiprocessExecDir,ResampExecDir,ITKTransformToolDir]

          BRAINSTempTfm = FinalResampPath.joinpath("First_Resampling").joinpath(allcasesIDs[case] + "_" + m_ScalarMeasurement + "_AffReg.txt").__str__()
          ANTSTempFileBase = FinalResampPath.joinpath("First_Resampling").joinpath(allcasesIDs[case] + "_" + m_ScalarMeasurement + "_").__str__()

          if m_Overwrite==1 or not CheckFileExists(FinalDef, case, allcasesIDs[case]) :   
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
          for i in range(int(m_nbLoopsDTIReg)):
            if os.path.isdir(FinalResampPath.joinpath("Second_Resampling").joinpath("Loop_"+str(i)).__str__()):
              cnt=i 
          cnt=max(cnt,0)

        while cnt < int(m_nbLoopsDTIReg):
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

          if m_Overwrite==1 or not CheckFileExists(DTIAverage2, 0, ""): 
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
            ITKTransformToolDir = os.path.dirname(m_SoftPath[9])
            PathList=[BRAINSExecDir,m_DTIRegExtraPath, dtiprocessExecDir,ResampExecDir,ITKTransformToolDir]

            BRAINSTempTfm = FinalResampPath.joinpath("First_Resampling").joinpath(allcasesIDs[case] + "_" + m_ScalarMeasurement + "_AffReg.txt").__str__()
            ANTSTempFileBase = FinalResampPath.joinpath("First_Resampling").joinpath(allcasesIDs[case] + "_" + m_ScalarMeasurement + "_").__str__()

            if m_Overwrite==1 or not CheckFileExists(FinalDef2, case, allcasesIDs[case])  :
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
            if CheckFileExists(GlobalDefField2, case, allcasesIDs[case]) :
              shutil.copy(GlobalDefField2, NewGlobalDefField2)
            InverseGlobalDefField2 = FinalResampPath.joinpath("Second_Resampling").joinpath(LastIterDir).joinpath(allcasesIDs[case] + "_InverseGlobalDisplacementField.nrrd").__str__()
            NewInverseGlobalDefField2 = FinalResampPath.joinpath("FinalDeformationFields").joinpath(allcasesIDs[case] + "_InverseGlobalDisplacementField.nrrd").__str__()
            if CheckFileExists(InverseGlobalDefField2, case, allcasesIDs[case]) :
              shutil.copy(InverseGlobalDefField2, NewInverseGlobalDefField2)
            FinalDef2 = FinalResampPath.joinpath("Second_Resampling").joinpath(LastIterDir).joinpath(allcasesIDs[case] + "_FinalDeformedDTI.nrrd").__str__()
            NewFinalDef2 = FinalResampPath.joinpath("FinalTensors").joinpath(allcasesIDs[case] + "_FinalDeformedDTI.nrrd").__str__()
            if CheckFileExists(FinalDef2, case, allcasesIDs[case]) :
              shutil.copy(FinalDef2, NewFinalDef2)
            FinalDef2f = FinalResampPath.joinpath("Second_Resampling").joinpath(LastIterDir).joinpath(allcasesIDs[case] + "_FinalDeformedDTI_float.nrrd").__str__()
            NewFinalDef2f = FinalResampPath.joinpath("FinalTensors").joinpath(allcasesIDs[case] + "_FinalDeformedDTI_float.nrrd").__str__()
            if CheckFileExists(FinalDef2f, case, allcasesIDs[case]) :
              shutil.copy(FinalDef2f, NewFinalDef2f)
            DTIRegCaseScalarMeasurement = FinalResampPath.joinpath("Second_Resampling").joinpath(LastIterDir).joinpath(allcasesIDs[case] + "_FinalDeformed"+m_ScalarMeasurement+".nrrd").__str__()
            NewDTIRegCaseScalarMeasurement = FinalResampPath.joinpath("FinalTensors").joinpath(allcasesIDs[case] + "_FinalDeformed"+m_ScalarMeasurement+".nrrd").__str__()
            if CheckFileExists(DTIRegCaseScalarMeasurement, case, allcasesIDs[case]) :
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
        logger=self.logger.write
        assert(self.configuration is not None)
        configuration=self.configuration

        deformSequence=configuration['deformSequence']
        inverseDeformSequence=configuration['inverseDeformSequence']
        projectPath=configuration['projectPath']
        config=configuration['config']
        hbuild=configuration['hbuild']
        greedy=configuration['greedy']
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
        ### Concatenate the displacement fields if tree level is over 2
        logger("\nConcatenating deformation fields")
        ITKTransformTools_Concatenate(config,deformSequence)
        ITKTransformTools_Concatenate_Inverse(config,inverseDeformSequence)
        generate_results_csv_from_deformation_track(deformSequence,projectPath)





### utils
import os # To run a shell command : os.system("[shell command]")
import sys # to return an exit code
import shutil # to remove a non empty directory
import json
import argparse
import csv 
import xml.etree.cElementTree as ET 
import xml.dom.minidom as minidom
from pathlib import Path 

import dtiplayground.dmri.atlasbuilder as ab 
import dtiplayground.dmri.common.tools as tools
import dtiplayground.dmri.common as common

# logger=common.logger.write

def dumpXml(xml):
    root = xml.getroot()
    xmlstr = minidom.parseString(ET.tostring(root)).toprettyxml(indent="\t")
    return xmlstr

def makeXmlElementTree(config, greedy): ## generate greedy xml from the scratch (recommended)
    root = ET.Element('ParameterFile')
    wis = ET.SubElement(root,'WeightedImageSet')
    ### WeightedImageSet
    siw = ET.SubElement(wis, 'ScaleImageWeights', { 'val':'true' })
    for cid in config['m_CasesIDs']:
        wi=ET.Element('WeightedImage',{})
        lastLoop=str(config['m_nbLoops'])
        p=os.path.join(config['m_OutputPath'],"1_Affine_Registration/Loop"+lastLoop+"/"+cid+"_Loop"+lastLoop+"_Final"+config["m_ScalarMeasurement"]+".nrrd")
        wiFilename=ET.Element('Filename',{'val':str(p)})
        wiItkTransform=ET.Element('ItkTransform',{'val':'1'})
        wi.insert(0,wiFilename)
        wi.insert(1,wiItkTransform)
        wis.insert(-1, wi)

    iif = ET.SubElement(wis, 'InputImageFormatString')
    fs = ET.SubElement(iif, 'FormatString', { 'val':'' })
    base = ET.SubElement(iif, 'Base', {'val':'0' })
    num_files = ET.SubElement(iif, 'NumFiles', { 'val' : str(len(config['m_CasesIDs'])) } )
    
    weight = ET.SubElement(iif, 'Weight', { 'val': '1' })

    ### GreedyScaleLevel
    for row in greedy['rows']:
        gsl = ET.SubElement(root,'GreedyScaleLevel',{})
        scale_level = ET.SubElement(gsl, 'ScaleLevel')
        downsample_factor = ET.SubElement(scale_level, 'DownSampleFactor')
        downsample_factor.set('val',str(row['scale_level']))
        n_iteration = ET.SubElement(gsl, 'NIterations')
        n_iteration.set('val',str(row['n_iterations']))
        iterator = ET.SubElement(gsl,'Iterator')
        maxpert = ET.SubElement(iterator,'MaxPert')
        maxpert.set('val',str(row['max_perturbation']))
        diffoper = ET.SubElement(iterator, 'DiffOper')
        alpha = ET.SubElement(diffoper,'Alpha')
        alpha.set('val',str(row['alpha']))
        beta = ET.SubElement(diffoper,'Beta')
        beta.set('val', str(row['beta']))
        gamma = ET.SubElement(diffoper,'Gamma')
        gamma.set('val', str(row['gamma']))
        
    ### Other options
    n_threads = ET.SubElement(root, 'nThreads')
    n_threads.set('val', str(config['m_NbThreadsString']))
    outputprefix = ET.SubElement(root, 'OutputPrefix')
    outputprefix.set('val', config["m_OutputPath"]+"/2_NonLinear_Registration/")
    outputsuffix = ET.SubElement(root, 'OutputSuffix')
    outputsuffix.set('val', 'mhd')
    xml = ET.ElementTree(element=root)
    return xml

# def makeXmlElementTreeDefault(cfg): ## generate them by default template (not recommended)
#     xmlfile=cfg["m_GreedyAtlasParametersTemplatePath"]
#     x=ET.parse(xmlfile)
#     r=x.getroot()

#     ## remove all dummy dataset files
#     wis=r.find('WeightedImageSet')
#     wi_list=wis.findall('WeightedImage')
#     for w in wi_list:
#         wis.remove(w)

#     ## insert new dataset
#     for cid in cfg["m_CasesIDs"]:
#         wi=ET.Element('WeightedImage',{})
#         lastLoop=str(cfg['m_nbLoops'])
#         p=os.path.join(cfg['m_OutputPath'],"1_Affine_Registration/Loop"+lastLoop+"/"+cid+"_Loop"+lastLoop+"_Final"+cfg["m_ScalarMeasurement"]+".nrrd")
#         wiFilename=ET.Element('Filename',{'val':str(p)})
#         wiItkTransform=ET.Element('ItkTransform',{'val':'1'})
#         wi.insert(0,wiFilename)
#         wi.insert(1,wiItkTransform)
#         wis.insert(-1,wi)  ## insert to the last

#     ## change output path 
#     for neighbor in r.iter('OutputPrefix'):
#         logger("{} {}".format(neighbor.tag,neighbor.attrib))
#         neighbor.set('val',cfg["m_OutputPath"]+"/2_NonLinear_Registration/")

#     return x

def generateGreedyAtlasParametersFile(cfg, greedy):

    # if greedy_scale_table is not None:
    x = makeXmlElementTree(cfg, greedy)
    # else:
    #     x = makeXmlElementTreeDefault(cfg)

    outputfile=cfg["m_OutputPath"]+"/2_NonLinear_Registration/GreedyAtlasParameters.xml"
    xmlstr = dumpXml(x)
    # x.write(outputfile)
    with open(outputfile, 'w') as f:
        f.writelines(xmlstr)



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

def _check_deformation_sequence_file(config,payload):
    binaryPath=config["m_SoftPath"][9]
    if(not os.path.exists(binaryPath)):
        logger("Software is missing : %s" %binaryPath)
        return False
    logger("Software path is : %s " % binaryPath)
    res=True
    for s in payload:
        cnt=0
        for f in s["filelist"]:
            if(not os.path.exists(f)):
                logger("Error while checking : %s " % f)
                cnt+=1
                res=False
        if cnt==0:
            logger("%s : OK" % s["id"])
        else:
            logger("%s : NOT OK" %s['id'])
    return res 

def _generate_concatenated_displacement_directory(config):
    projectDir=config["m_OutputPath"]
    outDir=os.path.join(projectDir,"displacement_fields")
    if not os.path.isdir(outDir):
      logger("\n=> Creation of the directory containing concatenated displacement fields = " + outDir)
      os.mkdir(outDir)
    return outDir

def ITKTransformTools_Concatenate(config,payload): ## payload should be deformation_track.json list
    command=""
    if(_check_deformation_sequence_file(config,payload)):
        outputDir=_generate_concatenated_displacement_directory(config)
        binaryPath=config["m_SoftPath"][9] 
        command+=binaryPath + " concatenate "
        refDTI=config["m_OutputPath"] + "/final_atlas/5_Final_Atlas/FinalAtlasDTI_float.nrrd"
        for idx, elm in enumerate(payload):
            hpairList=elm["id"].split("/")
            outFilename="_".join(hpairList) + "_GlobalDisplacementField_Concatenated.nrrd"
            outFilename=os.path.join(outputDir,outFilename)
            if Path(outFilename).exists() and (not config['m_Overwrite']==1):
                logger("File : {} already exists.".format(outFilename))
                continue
            #logger("Output filename : %s"%outFilename)
            tmpCommand=command + outFilename +" -r " + refDTI + " "
            inpListStr=""
            fl=map(str,elm["filelist"])
            #fl.reverse()
            for fn in fl:
                inpListStr+= fn + " displacement "
            tmpCommand+=inpListStr
            #logger("%d : %s " %(idx,tmpCommand))
            os.system(tmpCommand)
    else:
        logger("There are some missing deformation fields file(s)",common.Color.ERROR)
        #raise(Exception("There are some missing deformation fields file(s)"))

def ITKTransformTools_Concatenate_Inverse(config,payload): ## payload should be deformation_track.json list
    command=""
    if(_check_deformation_sequence_file(config,payload)):
        outputDir=_generate_concatenated_displacement_directory(config)
        binaryPath=config["m_SoftPath"][9] 
        command+=binaryPath + " concatenate "
        for idx, elm in enumerate(payload):
            refDTI=elm['original_dti_path']
            hpairList=elm["id"].split("/")
            outFilename=elm['output_path']
            if Path(outFilename).exists() and (not config['m_Overwrite']==1):
                logger("File : {} already exists.".format(outFilename))
                continue
            #logger("Output filename : %s"%outFilename)
            tmpCommand=command + outFilename +" -r " + refDTI + " "
            inpListStr=""
            fl=map(str,elm["filelist"])
            #fl.reverse()
            for fn in fl:
                inpListStr+= fn + " displacement "
            tmpCommand+=inpListStr
            #logger("%d : %s " %(idx,tmpCommand))
            os.system(tmpCommand)
    else:
        logger("There are some missing deformation fields file(s)",common.Color.ERROR)
        #raise(Exception("There are some missing deformation fields file(s)"))



def unique(list1): 
    unique_list = [] 
    for x in list1: 
        # check if exists in unique_list or not 
        if x not in unique_list: 
            unique_list.append(x) 
    return unique_list

def isComponent(seq,name):
    comp=list(filter(lambda x : x['name']==name,seq))
    if len(comp)>0 :
        return comp[0] 
    else:
        return False 

def find_config_by_nodename(build_sequence,nodename):
    for cfg in build_sequence:
        if cfg["m_NodeName"]==nodename:
            return cfg 


def generate_deformation_track(seq,node="target"): #input : initialSequence to generate deformation field tracking information (to concatenate them)
    component=isComponent(seq,node)
    outseq=[]

    if component != False:
        for c in component["dataset_ids"]:
            tmpseq=generate_deformation_track(seq,c)
            for t in tmpseq:
                outseq.append(node+"/"+t)
    else:
        outseq.append(node)
        return outseq 
    return outseq

def invert_deformation_track(deformation_seq):
    seq=copy.copy(deformation_seq)
    outseq=[]
    for s in seq:
        elm=s
        strvec=s['id'].split("/")
        strvec.reverse()
        elm['id']='/'.join(strvec)
        #elm['original_dti_id']=strvec[-1]
        arr=[]
        for e in s['filelist']:
            basedir=os.path.dirname(e)
            name="_".join(os.path.basename(e).split('_')[:-1])+"_InverseGlobalDisplacementField.nrrd"
            inverted_deform_path=os.path.join(basedir,name)
            arr.append(inverted_deform_path)
        arr.reverse()
        elm['filelist']=arr 

        output_dir=os.path.dirname(s['output_path'])
        output_name="_".join(os.path.basename(s['output_path']).split('_')[:-2])+"_InverseGlobalDisplacementField_Concatenated.nrrd"
        output_path=os.path.join(output_dir,output_name)
        elm['output_path']=output_path
        outseq.append(elm)
    return outseq 

    
def furnish_deformation_track(seq,project_path,build_sequence,inverse=False): #input deformSequence 
    res=[]
    for d in seq:
        tmp={}
        tmp['id']=d
        compseq=d.split('/')
        cfg=find_config_by_nodename(build_sequence,compseq[-2])
        originalDTIId=compseq[-1]
        originalDTIPath=None
        for idx,case in enumerate(zip(cfg["m_CasesIDs"],cfg["m_CasesPath"])):
            caseID,casePath=case 
            if originalDTIId==caseID: 
                originalDTIPath=casePath
                break

        entry=[]
        for idx,c in enumerate(compseq[0:-1]):
            fpath="atlases/" + c + "/5_Final_Atlas/FinalDeformationFields/" + compseq[idx+1] + "_GlobalDisplacementField.nrrd"
            fpath=os.path.join(project_path,fpath)
            entry.append(fpath)
        tmp['filelist']=entry
        tmp['original_dti_path']=originalDTIPath 
        tmp['original_dti_id']=originalDTIId
        tmp['scalar_measurement']=cfg["m_ScalarMeasurement"]
        tmp['nb_loops']=cfg['m_nbLoops']
        tmp['nb_loops_dtireg']=cfg['m_nbLoopsDTIReg']
        tmp['project_path']=cfg['m_OutputPath']
        tmp['need_to_be_cropped']=cfg['m_NeedToBeCropped']
        outputDir=os.path.join(project_path,"displacement_fields")
        hpairList=tmp["id"].split("/")
        outFilename="_".join(hpairList) + "_GlobalDisplacementField_Concatenated.nrrd"
        outFilename=os.path.join(outputDir,outFilename)
        tmp['output_path']=outFilename
        res.append(tmp)
    return res 




def parse_hbuild(hb,root_path,root_node="target"): #hbuild parser to generate build sequence
    if root_node is None:
        root_node=hb['project']['target_node']
    root=hb['build'][root_node]
    seq=[]
    nodeFiles=[] ## sub node's final atlases
    # scalar=hb['config']['m_ScalarMeasurement']
    if root["type"]=="node":    
        for c in root["components"]:
            seq+=parse_hbuild(hb, root_path=root_path, root_node=c)
            nodeAtlasPath=os.path.join(root_path,"atlases/"+c+"/5_Final_Atlas/FinalAtlasDTI_float.nrrd")
            nodeFiles.append(nodeAtlasPath)
    elif root["type"]=="end_node":
        if root["filetype"]=="dataset":
            rows=[]
            rows_id=[]
            with open(str(root['datasetfiles']),'r') as f:
                csvreader=csv.reader(f)
                next(csvreader,None)
                for r in csvreader:
                    fpath=str(r[1])
                    fid=os.path.splitext(os.path.basename(fpath))[0]
                    rows.append(fpath)
                    rows_id.append(str(fid))

            return  [{"name" : str(root_node),
                "dataset_files" : rows,
                "dataset_ids" : rows_id,
                "project_path" : str(os.path.join(root_path,"atlases/"+root_node))
                }]
        else:
            flist=list(map(str,root["datasetfiles"]))
            fids=[]
            for e in flist:
                fid=os.path.splitext(os.path.basename(e))[0]
                fids.append(fid)

            return [{"name" : str(root_node),
                    "dataset_files" : flist,
                    "dataset_ids" : fids ,
                    "project_path" : str(os.path.join(root_path,"atlases/"+root_node))
                    }]

    # node type file reading

    seq+=[{"name" : str(root_node),
            "dataset_files" : list(map(str,nodeFiles)),
            "dataset_ids" : list(map(str,root["components"])),
            "project_path" : str(os.path.join(root_path,"atlases/"+root_node))

         }]
    seq=unique(seq)

    ## generate final buildsequence furnished with configuration


    return seq

def furnish_sequence(hb,seq):
    bs=[]
    for s in seq:
        conf=hb["config"].copy()
        conf["m_OutputPath"]=s['project_path']
        conf["m_CasesPath"]=s['dataset_files']
        conf["m_CasesIDs"]=s['dataset_ids']
        conf["m_NodeInfo"]=hb["build"][s['name']]
        conf["m_NodeName"]=s["name"]
        bs.append(conf)

    return bs

def generate_directories(project_path,sequence): ## from build sequence, generate directories
    atlasesPath=os.path.join(project_path,"atlases")
    finalAtlasPath=os.path.join(project_path,"final_atlas")
    if not os.path.isdir(atlasesPath):
      logger("\n=> Creation of the atlas directory = " + atlasesPath)
      os.mkdir(atlasesPath)
    if not os.path.isdir(finalAtlasPath):
      logger("\n=> Creation of the atlas directory = " + finalAtlasPath)
      os.mkdir(finalAtlasPath)
    for s in sequence:
        apath=os.path.join(s["m_OutputPath"])
        if not os.path.isdir(apath):
          logger("\n=> Creation of the atlas directory = " + apath)
          os.mkdir(apath)
    logger("Initial directories are generated")


def dependency_satisfied(hb,node_name,completed_atlases):
    if hb["build"][node_name]["type"]=="end_node": 
        return True
    else:
        comps=hb["build"][node_name]["components"]
        for c in comps:
            if c not in completed_atlases: return False 
        return True



def generate_results_csv_from_deformation_track(deformation_track,project_path): # generate final result file with deformation track file

    dt=deformation_track
    outpath=os.path.join(project_path,"DTIAtlasBuilderResults.csv")
    
    m_ScalarMeasurement=dt[0]["scalar_measurement"]
    m_NeedToBeCropped=dt[0]["need_to_be_cropped"]
    header=["id", "Original DTI Image"]
    if m_NeedToBeCropped==1: header + ["Cropped DTI"]
    tmp=[m_ScalarMeasurement+ " from original",
        "Affine transform", "Affine Registered DTI", 
        "Affine Registered "+m_ScalarMeasurement,
        "Diffeomorphic Deformed " + m_ScalarMeasurement,
        "Diffeomorphic Deformation field to Affine space",
        "Diffeomorphic Deformation field to Affine space",
        "Diffeomorphic DTI",
        "Diffeomorphic Deformation field to Original space",
        "DTI-Reg Final DTI"
        ]
    header+=tmp
    with open(outpath,"w") as f:
        csvwriter=csv.writer(f,delimiter=',')
        csvwriter.writerow(header)
        for idx,case in enumerate(dt):
            caseID,casePath = case["original_dti_id"],case["original_dti_path"]
            m_OutputPath=case["project_path"]
            m_nbLoops=case["nb_loops"]
            m_nbLoopsDTIReg=case["nb_loops_dtireg"]
            row=[
                idx+1,
                casePath]
            if m_NeedToBeCropped==1: row+=[m_OutputPath+"/1_Affine_Registration/" + caseID+"_croppedDTI.nrrd"]
            concatenated_displacement_path=case["output_path"]
            row+=[
                m_OutputPath+"/1_Affine_Registration/" + caseID + "_" + m_ScalarMeasurement + ".nrrd",
                m_OutputPath+"/1_Affine_Registration/Loop" + str(m_nbLoops) + "/" + caseID + "_Loop" + str(m_nbLoops)+"_LinearTrans.txt",
                m_OutputPath+"/1_Affine_Registration/Loop" + str(m_nbLoops) + "/" + caseID + "_Loop" + str(m_nbLoops)+"_LinearTrans_DTI.nrrd",
                m_OutputPath+"/1_Affine_Registration/Loop" + str(m_nbLoops) + "/" + caseID + "_Loop" + str(m_nbLoops)+"_Final" + m_ScalarMeasurement +".nrrd",
                m_OutputPath+"/2_NonLinear_Registration/" + caseID + "_NonLinearTrans_" + m_ScalarMeasurement + ".mhd",
                m_OutputPath+"/2_NonLinear_Registration/" + caseID + "_HField.mhd" ,
                m_OutputPath+"/2_NonLinear_Registration/" + caseID + "_InverseHField.mhd" ,
                m_OutputPath+"/3_Diffeomorphic_Atlas/" + caseID + "_DiffeomorphicDTI.nrrd",
                concatenated_displacement_path,
                m_OutputPath+"/4_Final_Resampling/FinalTensors/" + caseID + "_FinalDeformedDTI.nrrd"
            ]
            csvwriter.writerow(row)

def generate_results_csv(cfg):

    outpath=os.path.join(cfg["m_OutputPath"],"DTIAtlasBuilderResults.csv")
    m_OutputPath=cfg["m_OutputPath"]
    m_ScalarMeasurement=cfg["m_ScalarMeasurement"]
    m_nbLoops=cfg["m_nbLoops"]
    m_nbLoopsDTIReg=cfg["m_nbLoopsDTIReg"]
    m_NeedToBeCropped=cfg["m_NeedToBeCropped"]
    header=["id", "Original DTI Image"]
    if m_NeedToBeCropped==1: header + ["Cropped DTI"]
    tmp=[cfg["m_ScalarMeasurement"]+ " from original",
        "Affine transform", "Affine Registered DTI", 
        "Affine Registered "+cfg["m_ScalarMeasurement"],
        "Diffeomorphic Deformed " + cfg["m_ScalarMeasurement"],
        "Diffeomorphic Deformation field to Affine space",
        "Diffeomorphic Deformation field to Affine space",
        "Diffeomorphic DTI",
        "Diffeomorphic Deformation field to Original space",
        "DTI-Reg Final DTI"
        ]
    header+=tmp
    with open(outpath,"w") as f:
        csvwriter=csv.writer(f,delimiter=',')
        csvwriter.writerow(header)
        for idx,case in enumerate(zip(cfg["m_CasesIDs"],cfg["m_CasesPath"])):
            caseID,casePath = case
            row=[
                idx+1,
                casePath]
            if m_NeedToBeCropped==1: row+=[m_OutputPath+"/1_Affine_Registration/" + caseID+"_croppedDTI.nrrd"]
            row+=[
                m_OutputPath+"/1_Affine_Registration/" + caseID + "_" + m_ScalarMeasurement + ".nrrd",
                m_OutputPath+"/1_Affine_Registration/Loop" + str(m_nbLoops) + "/" + caseID + "_Loop" + str(m_nbLoops)+"_LinearTrans.txt",
                m_OutputPath+"/1_Affine_Registration/Loop" + str(m_nbLoops) + "/" + caseID + "_Loop" + str(m_nbLoops)+"_LinearTrans_DTI.nrrd",
                m_OutputPath+"/1_Affine_Registration/Loop" + str(m_nbLoops) + "/" + caseID + "_Loop" + str(m_nbLoops)+"_Final" + m_ScalarMeasurement +".nrrd",
                m_OutputPath+"/2_NonLinear_Registration/" + caseID + "_NonLinearTrans_" + m_ScalarMeasurement + ".mhd",
                m_OutputPath+"/2_NonLinear_Registration/" + caseID + "_HField.mhd" ,
                m_OutputPath+"/2_NonLinear_Registration/" + caseID + "_InverseHField.mhd" ,
                m_OutputPath+"/3_Diffeomorphic_Atlas/" + caseID + "_DiffeomorphicDTI.nrrd",
                m_OutputPath+"/4_Final_Resampling/FinalDeformationFields/" + caseID + "_GlobalDisplacementField.nrrd",
                m_OutputPath+"/4_Final_Resampling/FinalTensors/" + caseID + "_FinalDeformedDTI.nrrd"
            ]
            csvwriter.writerow(row)




