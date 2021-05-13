
import os # To run a shell command : os.system("[shell command]")
import sys # to return an exit code
import shutil # to remove a non empty directory
import json
import argparse

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


if __name__=="__main__":
  parser=argparse.ArgumentParser()
  parser.add_argument("command",help="Command",type=str)
  parser.add_argument("--parameters",help="parameter json file",default="../common/config.json",type=str)
  parser.add_argument("--payload",help="payload for the command",type=str)
  args=parser.parse_args()

  with open(args.parameters,'r') as f :
    cfg=json.load(f)
  with open(args.payload,'r') as f:
    pl=json.load(f)

  globals()[args.command](cfg,pl)





