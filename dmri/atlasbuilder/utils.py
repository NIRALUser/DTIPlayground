
#
#   utils.py 
#   2021-05-10
#   Written by SK Park, NIRAL, UNC
#
#   Atlasbuilding utilities
#


import os # To run a shell command : os.system("[shell command]")
import sys # to return an exit code
import shutil # to remove a non empty directory
import json
import argparse
import csv 
import copy 

def _check_deformation_sequence_file(config,payload):
    binaryPath=config["m_SoftPath"][9]
    if(not os.path.exists(binaryPath)):
        print("Software is missing : %s" %binaryPath)
        return False
    print("Software path is : %s " % binaryPath)
    res=True
    for s in payload:
        cnt=0
        for f in s["filelist"]:
            if(not os.path.exists(f)):
                print("Error while checking : %s " % f)
                cnt+=1
                res=False
        if cnt==0:
            print("%s : OK" % s["id"])
        else:
            print("%s : NOT OK" %s['id'])
    return res 

def _generate_concatenated_displacement_directory(config):
    projectDir=config["m_OutputPath"]
    outDir=os.path.join(projectDir,"displacement_fields")
    if not os.path.isdir(outDir):
      print("\n=> Creation of the directory containing concatenated displacement fields = " + outDir)
      os.mkdir(outDir)
    return outDir

def ITKTransformTools_Concatenate(config,payload): ## payload should be deformation_track.json list
    command=""
    if(_check_deformation_sequence_file(config,payload)):
        outputDir=_generate_concatenated_displacement_directory(config)
        binaryPath=config["m_SoftPath"][9] 
        command+=binaryPath + " concatenate "
        refDTI=config["m_OutputPath"] + "/final_atlas/5_Final_Atlas/FinalAtlasDTI.nrrd"
        for idx, elm in enumerate(payload):
            hpairList=elm["id"].split("/")
            outFilename="_".join(hpairList) + "_GlobalDisplacementField_Concatenated.nrrd"
            outFilename=os.path.join(outputDir,outFilename)
            #print("Output filename : %s"%outFilename)
            tmpCommand=command + outFilename +" -r " + refDTI + " "
            inpListStr=""
            fl=map(str,elm["filelist"])
            #fl.reverse()
            for fn in fl:
                inpListStr+= fn + " displacement "
            tmpCommand+=inpListStr
            #print("%d : %s " %(idx,tmpCommand))
            os.system(tmpCommand)
    else:
        print("There are some missing deformation fields file(s)")
        raise(Exception("There are some missing deformation fields file(s)"))

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
            #print("Output filename : %s"%outFilename)
            tmpCommand=command + outFilename +" -r " + refDTI + " "
            inpListStr=""
            fl=map(str,elm["filelist"])
            #fl.reverse()
            for fn in fl:
                inpListStr+= fn + " displacement "
            tmpCommand+=inpListStr
            #print("%d : %s " %(idx,tmpCommand))
            os.system(tmpCommand)
    else:
        print("There are some missing deformation fields file(s)")
        raise(Exception("There are some missing deformation fields file(s)"))



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
    seq=copy.deepcopy(deformation_seq)
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




