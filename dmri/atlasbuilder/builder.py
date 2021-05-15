
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

import dmri.atlasbuilder.preprocess as preprocess
import dmri.atlasbuilder.atlas as atlas 
import dmri.atlasbuilder.utils as utils 
import dmri.atlasbuilder as ab 
import dmri.common

logger=ab.logger.write


## builder class
class Builder(object):
    def __init__(self,*args,**kwargs):
        self.configuration=None

    def configure(self,
                     output_dir,
                     config_path,
                     hbuild_path,
                     greedy_params_path,
                     buildsequence_path=None,
                     node=None):

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
            preprocess.run(conf)
            atlas.run(conf)  
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


