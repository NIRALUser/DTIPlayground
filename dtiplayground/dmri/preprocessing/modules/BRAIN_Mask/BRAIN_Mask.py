

import dtiplayground.dmri.preprocessing as prep
import dtiplayground.dmri.common.tools as tools
from dtiplayground.dmri.common.dwi import DWI
import yaml
from pathlib import Path
import importlib
###
import numpy as np
import ants 
import nibabel

logger=prep.logger.write

class BRAIN_Mask(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)
        
    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    def process(self,*args,**kwargs): ## variables : self.config_dir, self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        # << TODOS>>
        protocol_options=args[0]
        self.num_threads=protocol_options['software_info']['parameters']['num_max_threads']
        self.software_info=protocol_options['software_info']['softwares']
        self.baseline_threshold=protocol_options['baseline_threshold']
        res=self.run_mask(method=self.protocol['method'],
                          #modality=self.protocol['modality'],
                          averagingMethod=self.protocol['averagingMethod'])
        self.result['output']['success']=True
        return self.result
        

### User defined methods
    def mask_antspynet(self,params):
        import antspynet
        logger("AntsPyNet is running ...",prep.Color.INFO)
        res=None
        input_image_path=Path(self.output_dir).joinpath("input.nii.gz").__str__()
        output_mask_path=Path(self.output_dir).joinpath("mask.nii.gz").__str__()

        src_image=params['image']
        modality=params['modality']
        averagingMethod=params['averagingMethod']
        src_image.writeImage(input_image_path,dest_type='nifti')
        ants_image=ants.image_read(input_image_path)

        logger("Reduce to 3D volume for masking",prep.Color.INFO)
        baseline_img = self.image.extractBaselines()
        if len(baseline_img.getGradients()) < 1 :
            baseline_img = self.image
        reduced=baseline_img.reduceTo3D(method=averagingMethod)
        ants_image_3d=ants.from_numpy(data=reduced)
        ants_image_3d.set_origin(list(ants_image.origin)[:3])
        ants_image_3d.set_spacing(list(ants_image.spacing)[:3])
        new_dir=np.resize(ants_image.direction,[4,4])[:3,:3]
        ants_image_3d.set_direction(new_dir.tolist())
        logger("Computing probability mask ...",prep.Color.INFO)
        probability_mask=antspynet.brain_extraction(ants_image_3d,modality)
        logger("Generating thresholded mask ...",prep.Color.INFO)
        mask=ants.threshold_image(probability_mask,
                                  low_thresh=0.5,
                                  high_thresh=1.0,
                                  inval=1,
                                  outval=0)
        logger("Writing mask file",prep.Color.PROCESS)
        ants.image_write(mask, output_mask_path)
        dest_filename = input_image_path
        ## dev for nrrd output
        logger("Loading mask file",prep.Color.PROCESS)
        image=DWI(output_mask_path)
        # print(image.information)
        logger("Mask loaded",prep.Color.OK)
        logger("Saving NRRD")
        output_nrrd_path = Path(self.output_dir).joinpath("mask.nrrd").__str__()
        # print(image.information)
        image.setSpaceDirection(self.getSourceImageInformation()['space'])
        image.writeImage(output_nrrd_path,dest_type='nrrd')
        # print(image.information)
        logger("Saved as NRRD")
        ## dev-end
        self.addOutputFile(output_mask_path, 'Mask')
        self.addOutputFile(output_nrrd_path, 'Mask')
        self.addGlobalVariable('mask_path',output_nrrd_path)
        return res 

    def mask_fslbet(self,params): # provide baseline averaged image
        logger("FSL bet is running ...",prep.Color.INFO)
        input_image_base=Path(self.output_dir).joinpath("input").__str__()
        averaged_path=input_image_base+"_averaged"
        output_image_base=Path(self.output_dir).joinpath("mask").__str__()
        output_mask_base=Path(self.output_dir).joinpath("mask").__str__()

        input_image_path=input_image_base+".nii.gz"
        output_image_path=output_image_base+".nii.gz"
        output_mask_path=output_image_base+"_mask.nii.gz"
        output_mask_path_nrrd=output_image_base+".nrrd"
        src_image=params['image']
        averagingMethod=params['averagingMethod']
        src_image.writeImage(input_image_path,dest_type='nifti')
        fsl=tools.FSL(self.software_info['FSL']['path'])
        logger("Generating Mask",prep.Color.INFO)
        baseline_img = self.image.extractBaselines()
        if len(baseline_img.getGradients()) < 1 :
            baseline_img = self.image
        if averagingMethod == "direct_average":
            cmd_output=fsl.fslmaths_ops(input_image_path, averaged_path,'mean')
        if averagingMethod == "idwi":
            averaged_image=baseline_img.idwi() 
            affine_matrix=src_image.getAffineMatrixForNifti()           
            averaged_image = nibabel.Nifti1Image(averaged_image, affine=affine_matrix)
            nibabel.save(averaged_image, averaged_path)
        cmd_output=fsl.bet(averaged_path, output_image_path)
        mask=DWI(output_mask_path)
        mask.setSpaceDirection(self.getSourceImageInformation()['space'])
        mask.writeImage(output_mask_path_nrrd,dest_type='nrrd')
        self.addOutputFile(output_mask_path, 'Mask')
        self.addOutputFile(output_mask_path_nrrd, 'Mask')
        self.addGlobalVariable('mask_path',output_mask_path_nrrd)
        res=None
        return res

    def run_mask(self, method, averagingMethod): #run_mask(self,method, modality,averagingMethod)
        res=None 
        params={}
        logger("Mask is being computed ... ",prep.Color.PROCESS)
        if method=='fsl':
            params={
                'image': self.image,
                'averagingMethod': averagingMethod
            }
            res=self.mask_fslbet(params)
        elif method=='antspynet':
            params={
                'image': self.image,
                #'modality': modality,
                'averagingMethod': averagingMethod
            }
            res=self.mask_antspynet(params)
        logger("Mask generation is completed",prep.Color.OK)
        return res;


