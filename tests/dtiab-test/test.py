
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

### for dev

sys.path.append('../../')

import dmri.atlasbuilder.preprocess as preprocess
import dmri.atlasbuilder.atlas as atlas 
import dmri.atlasbuilder.utils as utils 

### load configutation json

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
    seq=deepcopy(deformation_seq)
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
            nodeAtlasPath=os.path.join(root_path,"atlases/"+c+"/5_Final_Atlas/FinalAtlasDTI.nrrd")
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
      print("\n=> Creation of the atlas directory = " + atlasesPath)
      os.mkdir(atlasesPath)
    if not os.path.isdir(finalAtlasPath):
      print("\n=> Creation of the atlas directory = " + finalAtlasPath)
      os.mkdir(finalAtlasPath)
    for s in sequence:
        apath=os.path.join(s["m_OutputPath"])
        if not os.path.isdir(apath):
          print("\n=> Creation of the atlas directory = " + apath)
          os.mkdir(apath)
    print("Initial directories are generated")


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




def main(args):
    projectPath=Path(args.output_dir).absolute().resolve(strict=False)
    scriptPath=projectPath.joinpath("scripts")
    commonPath=projectPath.joinpath('common')
    configPath=Path(args.config)
    hbuildPath=Path(args.hbuild)
    greedyParamsPath=Path(args.greedy_params)

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
    if args.buildsequence is None:
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
        hbuild['config']['m_GreedyAtlasParametersTemplatePath']=str(os.path.join(commonPath,'GreedyAtlasParameters.xml'))

        initSequence=parse_hbuild(hbuild,root_path=projectPath,root_node=args.node)
        buildSequence=furnish_sequence(hbuild,initSequence)

        #save sequence 
        with open(os.path.join(commonPath,'build_sequence.yml'),'w') as f:
            yaml.dump(buildSequence,f)

        # generate scaffolding directories 
        generate_directories(projectPath,buildSequence)
    else:
        with open(args.buildsequence,'r') as f:
            buildSequence=yaml.safe_load(f)
        numThreads=max(int(buildSequence[0]["m_NbThreadsString"]),1)

    with open(os.path.join(commonPath,'initial_sequence.yml'),'w') as f:
        yaml.dump(initSequence,f,indent=4)



    ## generate deformation field map
    deformInitSequence=generate_deformation_track(initSequence,node=hbuild['project']['target_node'])
    deformSequence=furnish_deformation_track(deformInitSequence,projectPath,buildSequence)
    inverseDeformSequence=invert_deformation_track(deformSequence)

    with open(os.path.join(commonPath,'deformation_track.yml'),'w') as f:
        yaml.dump(deformSequence,f)
    with open(os.path.join(commonPath,'deformation_track_inverted.yml'),'w') as f:
        yaml.dump(inverseDeformSequence,f)





    ### atlas build begins (to be multiprocessed)
    print("\nThe current date and time are:")
    print( time.strftime('%x %X %Z') )
    print("\n=============== Main Script ================")
    time1=time.time()


    ## threading
    completedAtlases=[] #entry should be the node name 
    runningAtlases=[] # should have length less or equal than numTheads, entry is the node name


    def buildAtlas(conf,rt,ct): # rt : list of running threads, ct : list of completed threads, nt : number of thread (numThreads)
        prjName=conf["m_NodeName"]
        rt.append(prjName)
        try:
            preprocess.run(conf)
        except Exception as e:
            raise Exception("Error occurred in DTIAtlasBuilder_Preprocess : " + str(e))

        try:
            atlas.run(conf)
        except Exception as e:
            raise Exception("Error occurred in DTIAtlasBuilding_DTIAtlasBuilder : " + str(e))    
        rt.remove(prjName)
        ct.append(prjName)

    numNodes=len(buildSequence)
    while len(completedAtlases) < numNodes:
        if len(runningAtlases) < numThreads and len(buildSequence)>0:
            if dependency_satisfied(hbuild,buildSequence[0]["m_NodeName"],completedAtlases):
                cfg=buildSequence.pop(0)
                generate_results_csv(cfg)
                threading.Thread(target=buildAtlas,args=(cfg,runningAtlases,completedAtlases)).start()

        # print("Completed : " + str(completedAtlases))
        # print("Running : " + str(runningAtlases))
        # print("Pending : " + str([x["m_NodeName"] for x in buildSequence]))
        time.sleep(1.0)

    # print("Completed : " + str(completedAtlases))
    # print("Running : " + str(runningAtlases))
    # print("Pending : " + str([x["m_NodeName"] for x in buildSequence]))

    ### copy final atals to 'final_atlas' directory
    try:
        if args.node is None:
            src=os.path.join(projectPath,"atlases/"+hbuild['project']['target_node'])
        else:
            src=os.path.join(projectPath,"atlases/"+args.node)
        dst=os.path.join(projectPath,"final_atlas")
        print("Copying filed from %s to %s" %(src,dst))
        shutil.rmtree(dst)
        shutil.copytree(src,dst)

    except Exception as e:
        raise Exception("Error occurred in copying final atlas directory : " +str(e))

    print("Final atlas copied into %s "% dst)


    ### Concatenate the displacement fields
    print("\nConcatenating deformation fields")
    try:
        utils.ITKTransformTools_Concatenate(config,deformSequence)
        utils.ITKTransformTools_Concatenate_Inverse(config,inverseDeformSequence)
        generate_results_csv_from_deformation_track(deformSequence,projectPath)

    except Exception as e:
        raise Exception("Error occurred in concatenating deformation fields : " + str(e))

    # Display execution time
    time2=time.time()
    timeTot=time2-time1
    if timeTot<60 : print("| Execution time = " + str(int(timeTot)) + "s")
    elif timeTot<3600 : print("| Execution time = " + str(int(timeTot)) + "s = " + str(int(timeTot/60)) + "m " + str( int(timeTot) - (int(timeTot/60)*60) ) + "s")
    else : print("| Execution time = " + str(int(timeTot)) + "s = " + str(int(timeTot/3600)) + "h " + str( int( (int(timeTot) - int(timeTot/3600)*3600) /60) ) + "m " + str( int(timeTot) - (int(timeTot/60)*60) ) + "s")


    

if __name__=="__main__":
    parser=argparse.ArgumentParser(description="Argument Parser")
    parser.add_argument('--output-dir', help='configuration file',default='output',type=str)
    parser.add_argument('--config',help='configuration file',default='config.yml',type=str)
    parser.add_argument('--hbuild',help='hierarchical build file', default='h-build.yml', type=str)
    parser.add_argument('--greedy-params',help='Greedy atlas parameter xml file', type=str)
    parser.add_argument('--node',help="node to build",type=str)
    parser.add_argument('--buildsequence',help='build sequence file, if this option is inputted then build sequence process will be skipped',type=str)
    args=parser.parse_args()


    try:
       main(args)
       sys.exit(0)
    except Exception as e:
        print(str(e))
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)











