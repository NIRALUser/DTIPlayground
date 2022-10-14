

  
import dtiplayground.dmri.preprocessing as prep
from dtiplayground.dmri.common.dwi import DWI
import dtiplayground.dmri.common
import yaml
from pathlib import Path 
# import SUSCEPTIBILITY_Correct.utils as utils
from dtiplayground.dmri.common import measure_time
import dtiplayground.dmri.common.tools as tools 
import shutil
import copy
import os
import markdown
from . import data 

def find_fsl(lookup_dirs=[]):
    fsldir=os.environ.get('FSLDIR')
    candidates=[]
    if fsldir is not None:
        fsldir=Path(fsldir)
        candidates.append(fsldir)
    else:
        candidates=[]
        for d in lookup_dirs:
            candidates+=list(Path(d).glob("**/etc/fslversion"))
        
        if len(candidates)==0 : 
            logger("FSL6 NOT found",prep.Color.WARNING)
            return None,None 
        candidates=list(map(lambda x: x.parent.parent, candidates))

    fsl_version=None
    for d in candidates:
        fsldir=d
        versionfile=fsldir.joinpath('etc/fslversion')
        if versionfile.exists():
            with open(versionfile,'r') as f:
                fsl_version=f.readlines()[0]
            bigversion=int(fsl_version.split('.')[0])
            if bigversion>=6:
                return str(fsldir), fsl_version

    return str(fsldir),fsl_version
    
class SUSCEPTIBILITY_Correct(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)
        global logger
        logger = self.logger.write


    def install(self,install_dir,*args,**kwargs):
        topup_config='fsl_regb02b0.cnf'
        install_dir=Path(install_dir).joinpath('parameters').joinpath('fsl')
        install_dir.mkdir(parents=True,exist_ok=True)
        #source_path=Path(dtiplayground.dmri.common.__file__).parent.joinpath('data').joinpath(topup_config)
        source_path=Path(data.__file__).parent.joinpath(topup_config)
        dest_path=install_dir.joinpath(topup_config)
        logger("Copying FSL config file to {}".format(str(dest_path)))
        shutil.copy(source_path,dest_path)

    def generateDefaultEnvironment(self):
        return super().generateDefaultEnvironment()
    
    def checkDependency(self,environment): #use information in template, check if this module can be processed
        # FSL should be ready before execution
        software_path=Path(self.config_dir).joinpath('software_paths.yml')
        software_info = yaml.safe_load(open(software_path,'r'))
        if self.name in environment:
            fslpath=Path(software_info['softwares']['FSL']['path'])
            try:
                #fslpath=Path(environment[self.name]['fsl_path'])
                fsl_exists=fslpath.exists()
                if fsl_exists:
                    return True, None 
                else:
                    return False, "FSL Path doesn't exist : {}".format(str(fslpath))
            except Exception as e:
                return False, "Exception in finding FSL6 : {}".format(str(e))
        else:
            return False, "Can't locate FSL" #test

    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        self.protocol['configurationFilePath']=self.protocol['configurationFilePath'].replace("$CONFIG_DIR",str(self.config_dir))
        return self.protocol

    def process(self,*args,**kwargs): ## variables : self.global_variables, self.softwares, self.output_dir, self.config_dir, self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        #inputParams=self.getPreviousResult()['output']
        gradient_indexes_to_remove=[]
        protocol_options=args[0]
        self.num_threads=protocol_options['software_info']['parameters']['num_max_threads']
        self.software_info=protocol_options['software_info']['softwares']
        self.baseline_threshold=protocol_options['baseline_threshold']

        res=None
        output_image_file=Path(self.output_dir).joinpath('output.nrrd')
        logger("Running topup ...",prep.Color.PROCESS)
        self.run_topup( phaseEncodingAxis=self.protocol['phaseEncodingAxis'],
                        phaseEncodingValue=self.protocol['phaseEncodingValue'],
                        configurationFilePath=self.protocol['configurationFilePath'])
        logger("Topup done",prep.Color.OK)

        ## results
        self.result['output']['excluded_gradients_original_indexes']=self.image.convertToOriginalGradientIndex(gradient_indexes_to_remove)
        self.result['output']['success']=True
        return self.result

    def makeReport(self):
        self.result['report'] = {'module_report_paths': os.path.abspath(self.output_dir) + '/report.md',
                                 'csv_data': {'image_name': None,
                                              'original_number_of_gradients': None,
                                              'excluded_gradients': None,
                                              'rms_gt_1': None,
                                              'rms_gt_2': None,
                                              'rms_gt_3': None}, 
                                 'eddymotion_pdf_path': None}

        
        if self.result['input'][0]["output"]['image_path']:
            input_image_1 = os.path.abspath(self.result['input'][0]["output"]['image_path'])
            input_image_2 = os.path.abspath(self.result['input'][1]["output"]['image_path'])
            if 'image_information' in self.result['input'][0]:
                for number_1 in self.result['input'][0]['image_information']['sizes']:
                    if number_1 not in self.result['input'][0]['image_information']['image_size']:
                        self.result['report']['csv_data']['original_number_of_gradients'] = [number_1]
            if 'image_information' in self.result['input'][1]:
                for number_2 in self.result['input'][1]['image_information']['sizes']:
                    if number_2 not in self.result['input'][1]['image_information']['image_size']:
                        self.result['report']['csv_data']['original_number_of_gradients'] += [number_2]
        else:
            input_image_1 = None
            input_image_2 = None
            input_directory = self.result_history[0]["output"][0]["output"]["output_directory"]
            self.result['report']['csv_data']['original_number_of_gradients'] = [None, None]
            list_report_paths_1 = []
            list_report_paths_2 = []
            self.result['report']['csv_data']['excluded_gradients'] = [None, None, None]
            while input_image_1 == None:
                previous_result = yaml.safe_load(open(str(Path(self.output_dir).parent.parent) + "/" + input_directory + "/result.yml", 'r'))
                input_image_1 = previous_result["input"]["image_path"]
                if previous_result['report']['csv_data']['excluded_gradients']:
                    if not self.result['report']['csv_data']['excluded_gradients'][0]:
                        self.result['report']['csv_data']['excluded_gradients'][0] = []
                    self.result['report']['csv_data']['excluded_gradients'][0] += previous_result['report']['csv_data']['excluded_gradients']
                list_report_paths_1 = [os.path.abspath(previous_result["report"]["module_report_paths"])] + list_report_paths_1
                if "output_directory" in previous_result["input"]:
                    input_directory = previous_result["input"]["output_directory"]
                if 'image_information' in previous_result['input']:
                    for number_1 in previous_result['input']['image_information']['sizes']:
                        if number_1 not in previous_result['input']['image_information']['image_size']:
                            self.result['report']['csv_data']['original_number_of_gradients'][0] = number_1
                print("input_image_1:", input_image_1)
        
            input_directory = self.result_history[0]["output"][1]["output"]["output_directory"]
            while input_image_2 == None:
                previous_result = yaml.safe_load(open(str(Path(self.output_dir).parent.parent) + "/" + input_directory + "/result.yml", 'r'))
                input_image_2 = previous_result["input"]["image_path"]
                if previous_result['report']['csv_data']['excluded_gradients']:
                    if not self.result['report']['csv_data']['excluded_gradients'][1]:
                        self.result['report']['csv_data']['excluded_gradients'][1] = []
                    self.result['report']['csv_data']['excluded_gradients'][1] += previous_result['report']['csv_data']['excluded_gradients']
                list_report_paths_2 = [os.path.abspath(previous_result["report"]["module_report_paths"])] + list_report_paths_2
                if "output_directory" in previous_result["input"]:
                    input_directory = previous_result["input"]["output_directory"]
                if 'image_information' in previous_result['input']:
                    for number_2 in previous_result['input']['image_information']['sizes']:
                        if number_2 not in previous_result['input']['image_information']['image_size']:
                            self.result['report']['csv_data']['original_number_of_gradients'][1] = number_2
                print("number of input gradients :", self.result['report']['csv_data']['original_number_of_gradients'])
                
            self.result['report']['module_report_paths'] = [list_report_paths_1, list_report_paths_2, os.path.abspath(self.output_dir) + '/report.md']
            input_image_1 = os.path.abspath(input_image_1)
            input_image_2 = os.path.abspath(input_image_2)


        with open(os.path.abspath(self.output_dir) + '/report.md', 'bw+') as f:
            f.write('## {}\n'.format("Module: " + self.result['module_name']).encode('utf-8'))
            f.write('### {}\n'.format("input image 1: " + str(input_image_1)).encode('utf-8'))
            f.write('### {}\n'.format("input image 2: " + str(input_image_2)).encode('utf-8'))
            f.seek(0)
            markdown.markdownFromFile(input=f, output=os.path.abspath(self.output_dir) + '/report.html')

        self.result['report']['csv_data']['image_name'] = [input_image_1, input_image_2, os.path.abspath(self.result['output']['image_path'])]

### User defined methods
### scripts
    @measure_time
    def convert_to_nifti(self,phaseEncodingAxis): ## generate nifti file and return filenames
        axis_alias={0:'lr',1:'ap',2:'is'}
        ped=axis_alias[int(phaseEncodingAxis)]
        inv_ped=ped[::-1] #reverse string
        directions=[ped,inv_ped]
        out_files=[]
        out_images=[]
        if ped=='ap' : directions+=['fh','hf']
        for d in directions:
            for img in self.images:
                fname=Path(img.filename).name.lower()
                if d in fname:
                    outfilename=Path(self.output_dir).joinpath(d+".nii.gz").__str__()
                    img.image_type='nifti'
                    img.writeImage(outfilename,dest_type='nifti')
                    out_files.append(outfilename)
                    out_images.append(img)
        if len(out_files)<2:
            out_files=[]
            for idx,img in enumerate(self.images):
                outfilename=Path(self.output_dir).joinpath(directions[idx]+".nii.gz").__str__()
                img.writeImage(outfilename,dest_type='nifti')
                out_files.append(outfilename)
                out_images.append(img)

        return out_files,out_images


    @measure_time
    def create_b0s(self,pe_images,b0_threshold):  ## create b0 and index file
        b0_files=[]
        b0_images=[]
        b0_indexes=[]
        for img in pe_images:
            minb,maxb=img.getBValueBounds()
            if b0_threshold < minb :   ## if given b0 threshold is less than the least b value of the gradients, substitute it to the minimal b value
                img.setB0Threshold(minb)
                b0_threshold=minb

        for idx,img in enumerate(pe_images):

            b0img=img.extractBaselines(b0_threshold)
            outfilename=Path(self.output_dir).joinpath("b0_{}.nii.gz".format(idx)).__str__()
            index_outfilename=Path(self.output_dir).joinpath("b0_{}.index".format(idx)).__str__()
            b0img.writeImage(outfilename,dest_type='nifti')
            grads=b0img.getGradients()
            indexes=[str(x['original_index']) for x in grads]
            with open(index_outfilename,'w') as f :
                f.write(" ".join(indexes))
            b0_files.append(outfilename)
            b0_images.append(b0img)
            b0_indexes.append(index_outfilename)
        return b0_files,b0_images,b0_indexes,b0_threshold

    def merge_images(self,outputfilename,pe_files:list,b0_threshold):
        fsl=tools.FSL(self.software_info['FSL']['path'])
        fsl._set_num_threads(self.num_threads)
        
        output=fsl.fslmerge(outputfilename,pe_files)
        ## making merged bvals,bvecs
        bvals_fn=Path(self.output_dir).joinpath(Path(outputfilename).name.split('.')[0]+'.bval')
        bvecs_fn=Path(self.output_dir).joinpath(Path(outputfilename).name.split('.')[0]+'.bvec')

        input_bvals_fn_0=Path(self.output_dir).joinpath(Path(pe_files[0]).name.split('.')[0]+'.bval')
        input_bvecs_fn_0=Path(self.output_dir).joinpath(Path(pe_files[0]).name.split('.')[0]+'.bvec')
        input_bvals_fn_1=Path(self.output_dir).joinpath(Path(pe_files[1]).name.split('.')[0]+'.bval')
        input_bvecs_fn_1=Path(self.output_dir).joinpath(Path(pe_files[1]).name.split('.')[0]+'.bvec')
        
        with open(bvals_fn,'w') as fw:
            bvals1=open(input_bvals_fn_0,'r').read()
            bvals2=open(input_bvals_fn_1,'r').read()
            bvals=bvals1+bvals2
            bvals_int=list(map(int,bvals.split()))
            for idx,b in enumerate(bvals_int):
                if b<=b0_threshold:
                    bvals_int[idx]=0 ## fsl's baseline should have 0 b values
            bvals="\n".join(list(map(str,bvals_int)))
            fw.write(bvals)

        with open(bvecs_fn,'w') as fw:
            bvecs1=open(input_bvecs_fn_0,'r').read()
            bvecs2=open(input_bvecs_fn_1,'r').read()
            bvecs=bvecs1+bvecs2
            fw.write(bvecs)


        logger(output.stdout)
        logger(output.stderr)
        output.check_returncode()


    ### fsl parameters
    def make_acqp(self,outfilename,b0index_files:list,axis=1,val=0.0924):
        phase_dir=[0,0,0,val]
        result=[]
        direction=1
        for index_file in b0index_files:
            indexes=open(index_file,'r').read().split()
            for i in indexes:
                p=copy.copy(phase_dir)
                p[int(axis)]=direction
                result.append(p)
            direction*=-1
        with open(outfilename,'w') as fw:
            for r in result:
                strline="{:d} {:d} {:d} {:.4f}\n".format(*r)
                fw.write(strline)
        return result

    def make_index(self,image,outfilename):
        indices=image.getB0Index()
        with open(outfilename,'w') as fw:
            outstr=" ".join(list(map(str,indices)))
            fw.write(outstr)
        return indices 

    def get_phase_axis(self,phaseEncodingAxis):
        return phaseEncodingAxis

    def zero_padding_odd_sizes(self):
        for img in self.images:
            pad_sizes=[0,0,0,0]
            for idx,x in enumerate(list(img.images.shape)[0:3]):
                if x%2==1: 
                    logger("[WARNING] Image size has odd number, automatically padding zero values...",prep.Color.WARNING)
                    pad_sizes[idx]+=1 
            img.zeroPad(pad_sizes)

    @measure_time
    def run_topup(  self,
                    phaseEncodingAxis,
                    phaseEncodingValue,
                    configurationFilePath):

        b0_threshold=self.baseline_threshold 
        phase_axis=self.get_phase_axis(phaseEncodingAxis)

        output_dir=Path(self.output_dir)
        output_nrrd=output_dir.joinpath('output.nrrd').__str__()
        
        fsl=tools.FSL(self.software_info['FSL']['path'])
        fsl._set_num_threads(self.num_threads)
        fsl.setDevMode(True) 

        ## auto zero padding if image dimension has odd number of element (even size of image sizes is only acceptable)
        logger("Checking image sizes...",prep.Color.INFO)
        self.zero_padding_odd_sizes()


        pe_files, pe_images=self.convert_to_nifti(phaseEncodingAxis)
        b0_files, b0_images, b0_index_files,b0_threshold=self.create_b0s(pe_images,b0_threshold)
        
        logger("Merging b0s ...",prep.Color.PROCESS)
        merged_b0_filename=Path(self.output_dir).joinpath("b0_merged.nii.gz").__str__()
        self.merge_images(merged_b0_filename,b0_files,b0_threshold)

        logger("Generating acqp parameters ...",prep.Color.PROCESS)
        acqp_filename=Path(self.output_dir).joinpath("acqp.txt").__str__()
        self.make_acqp(acqp_filename, b0_index_files,axis=phase_axis,val=phaseEncodingValue)

        logger("Merging original images ... ",prep.Color.PROCESS)
        merged_image_filename=Path(self.output_dir).joinpath("merged_image.nii.gz").__str__()
        merged_bvals_filename=Path(self.output_dir).joinpath("merged_image.bval").__str__()
        merged_bvecs_filename=Path(self.output_dir).joinpath("merged_image.bvec").__str__()
        self.merge_images(merged_image_filename,pe_files,b0_threshold)

        ## load merged image into self.image 
        self.image=DWI(merged_image_filename)
        self.image.setB0Threshold(b0_threshold)
        base=Path(merged_image_filename).name.split('.')[0]

        logger("Generating index file ...",prep.Color.PROCESS)
        _index_path=Path(self.output_dir).joinpath(base+".b0index").__str__()
        indices=self.make_index(self.image,_index_path)
        logger("B0 indices : {}".format(indices),prep.Color.INFO)

        logger("Running topup command...",prep.Color.PROCESS)
        _out_path=Path(self.output_dir).joinpath(base+"_topup_fieldcoef.nii.gz").__str__()
        _fout_path=Path(self.output_dir).joinpath(base+"_field.nii.gz").__str__()
        _iout_path=Path(self.output_dir).joinpath(base+"_corr.nii.gz").__str__()
        _out_path_prep=Path(self.output_dir).joinpath(base+"_topup").__str__()
        if not Path(_out_path).exists() or not Path(_fout_path).exists() or not Path(_iout_path).exists():
            
            output=fsl.topup(imain=merged_b0_filename,  # input image filename (merged b0)
                      datain=acqp_filename, # acqp params filename
                      out=_out_path_prep,    # output basename (not a filename)
                      fout=_fout_path,   # field output filename (Hz)
                      iout=_iout_path,   # movement corrected image output filename
                      config=configurationFilePath) # config filename
        
        _average_path=Path(self.output_dir).joinpath(base+"_average.nii.gz").__str__()
        
        logger("Averaging topup corr for the masking...",prep.Color.PROCESS)
        output=fsl.fslmaths_ops(_iout_path,_average_path,'mean')
        logger("Generating mask...",prep.Color.PROCESS)
        _mask_path=Path(self.output_dir).joinpath(base+"_mask.nii.gz").__str__()
        output=fsl.bet(_average_path,_mask_path)
        _mask_path=Path(self.output_dir).joinpath(base+"_mask_mask.nii.gz").__str__()
        
        self.image.zerorizeBaselines(b0_threshold) ## fsl's baseline should have 0 b values

        susceptibility_parameters={
            "mask_path" : _mask_path,
            "acqp_path" : acqp_filename,
            "image_path" : merged_image_filename,
            "image_bvals_path" : merged_bvals_filename,
            "image_bvecs_path" : merged_bvecs_filename,
            "b0_image_path" : merged_b0_filename,
            "topup_path" : _out_path_prep,
            "index_path" : _index_path
        }
        self.updateGlobalVariable(susceptibility_parameters)

        self.result['output']['susceptibility_parameters']=susceptibility_parameters
        self.writeImageWithOriginalSpace(output_nrrd,'nrrd')
