

  
import dmri.preprocessing as prep

import yaml
from pathlib import Path 
import EDDYMOTION_Correct.utils as utils
import dmri.common.tools as tools 
logger=prep.logger.write
from dmri.common import measure_time
import shutil

logger=prep.logger.write

class EDDYMOTION_Correct(prep.modules.DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(EDDYMOTION_Correct)

    def generateDefaultEnvironment(self):
        #find fsl path 
        fsldir, fsl_version=utils.find_fsl(['/NIRAL/tools/FSL/fsl-6.0.3'])
        res={'fsl_path': fsldir, 'fsl_version' : fsl_version}
        return res
    
    def checkDependency(self,environment): #use information in template, check if this module can be processed
        # FSL should be ready before execution
        if self.name in environment:
            try:
                fslpath=Path(environment[self.name]['fsl_path'])
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
        return self.protocol

    def process(self,*args,**kwargs): ## variables : self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        gradient_indexes_to_remove=[]
        protocol_options=args[0]
        self.num_threads=protocol_options['software_info']['parameters']['num_max_threads']
        self.software_info=protocol_options['software_info']['softwares']
        susceptibility=False
        susceptibility_parameters=None
        if 'susceptibility_parameters' in inputParams:
            susceptibility=True
            susceptibility_parameters=inputParams['susceptibility_parameters']
        res=None
        if susceptibility:
            res=self.eddy_with_susceptibility(self.image,None,susceptibility_parameters)
        else:
            res=self.eddy(self.image,None)

        ## results
        self.result['output']['excluded_gradients_original_indexes']=self.image.convertToOriginalGradientIndex(gradient_indexes_to_remove)
        self.result['output']['success']=True
        return self.result

    ### fsl parameters
    def make_acqp(self,axis=0,val=0.0924):
        acqps=[[0,1,0,val]]
        outfilename=Path(self.output_dir).joinpath('acqp.txt').__str__()
        with open(outfilename,'w') as f:
            for e in acqps:
                strline="{:d} {:d} {:d} {:.4f}\n".format(*e)
                f.write(strline)
        return outfilename

    def make_index(self,image):
        outfilename=Path(self.output_dir).joinpath('index.txt').__str__()
        grads=image.getGradients()
        with open(outfilename,'w') as f:
            for g in grads:
                f.write("1 ")
        return outfilename 

    def make_index_new(self,image,baseline_index_file):
        grads=image.getGradients()
        bidx_sarr=open(baseline_index_file,'r').read().split()
        bidx=list(map(int,bidx_sarr))
        index_filename=Path(self.output_dir).joinpath('index.txt').__str__()

        b0idx=1
        res_index=[]
        for i,g in enumerate(grads):
            if b0idx<len(bidx):
                if bidx[b0idx-1]==i:
                    b0idx+=1
            res_index.append(b0idx)
        res_str=" ".join(list(map(str,res_index)))
        open(index_filename,'w').write(res_str)
        return index_filename
    ### scripts
    @measure_time
    def eddy(self,image,outfilename):
        output_dir=Path(self.output_dir)

        ### conversion to nifti 
        input_nifti=output_dir.joinpath('input.nii.gz').__str__()
        input_bvals=output_dir.joinpath('input.bvals').__str__()
        input_bvecs=output_dir.joinpath('input.bvecs').__str__()
        output_nifti=output_dir.joinpath('output.nii.gz').__str__()
        binary_mask=output_dir.joinpath('output_mask.nii.gz').__str__()
        processed_nifti=output_dir.joinpath('output_eddied.nii.gz').__str__()
        processed_bvals=output_dir.joinpath('output_eddied.bvals').__str__()
        processed_bvecs=output_dir.joinpath('output_eddied.bvecs').__str__()
        output_nrrd=output_dir.joinpath('output.nrrd').__str__()

        self.writeImage(str(input_nifti),dest_type='nifti')

        ### generate mask
        fsl=tools.FSL(self.software_info['FSL']['path'])
        fsl._set_num_threads(self.num_threads)
        fsl.setDevMode(True)
        logger("Generating Mask : {}".format(binary_mask.__str__()))
        res=fsl.bet(str(input_nifti),str(output_nifti))

        ### acqp file writing
        acqp_filename=self.make_acqp() 
        index_filename=self.make_index(self.image)
        ### eddy correction
        if not Path(processed_nifti).exists():
            logger("Computing eddy ... ",prep.Color.PROCESS)
            res=fsl.eddy_openmp(imain=input_nifti,
                            mask=binary_mask,
                            acqp=acqp_filename,
                            index_file=index_filename,
                            bvals=input_bvals,
                            bvecs=input_bvecs,
                            out=processed_nifti)
        else:
            logger("Eddymotion corrected output exists: {}".format(processed_nifti),prep.Color.OK)
        shutil.copy(input_bvals,processed_bvals)
        shutil.copy(processed_nifti+".eddy_rotated_bvecs",processed_bvecs)
        self.image=self.loadImage(processed_nifti)
        self.image.image_type='nrrd'
        if not Path(output_nrrd).exists():
            self.writeImage(output_nrrd)

        return None

    @measure_time
    def eddy_with_susceptibility(self,image,outfilename,params):
        logger(yaml.dump(params),prep.Color.DEV)

        output_dir=Path(self.output_dir)

        ### conversion to nifti 
        input_nifti=params['image_path']
        input_bvals=params['image_bvals_path']
        input_bvecs=params['image_bvecs_path']
        output_nifti=output_dir.joinpath('output.nii.gz').__str__()
        binary_mask=params['mask_path']
        processed_nifti=output_dir.joinpath('output_eddied.nii.gz').__str__()
        processed_bvals=output_dir.joinpath('output_eddied.bvals').__str__()
        processed_bvecs=output_dir.joinpath('output_eddied.bvecs').__str__()
        output_nrrd=output_dir.joinpath('output.nrrd').__str__()

        ### generate mask
        fsl=tools.FSL(self.software_info['FSL']['path'])
        fsl._set_num_threads(self.num_threads)
        fsl.setDevMode(True)

        ### acqp file writing
        acqp_filename=params['acqp_path']
        index_filename=self.make_index_new(self.image,params['index_path'])
        #topup_filename=Path(params['topup_path']).parent.joinpath(Path(params['topup_path']).name.split('.')[0])
        topup_filename=params['topup_path']
        ### eddy correction
        if not Path(processed_nifti).exists():
            logger("Computing eddy with susceptibility correction... ",prep.Color.PROCESS)
            res=fsl.eddy_openmp(imain=input_nifti,
                            mask=binary_mask,
                            acqp=acqp_filename,
                            index_file=index_filename,
                            bvals=input_bvals,
                            bvecs=input_bvecs,
                            out=processed_nifti,
                            estimate_move_by_susceptibility=True,
                            topup=topup_filename)
        else:
            logger("Eddymotion corrected output exists: {}".format(processed_nifti),prep.Color.OK)
        shutil.copy(input_bvals,processed_bvals)
        shutil.copy(processed_nifti+".eddy_rotated_bvecs",processed_bvecs)
        self.image=self.loadImage(processed_nifti)
        self.image.image_type='nrrd'
        if not Path(output_nrrd).exists():
            self.writeImage(output_nrrd)

        return None


