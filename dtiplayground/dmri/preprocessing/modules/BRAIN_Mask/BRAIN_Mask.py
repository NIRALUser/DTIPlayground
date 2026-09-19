

import dtiplayground.dmri.preprocessing as prep
import dtiplayground.dmri.common.tools as tools
from dtiplayground.dmri.common.dwi import DWI
import yaml
from pathlib import Path
import importlib
###
import numpy as np
import nibabel

class BRAIN_Mask(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)
        global logger
        logger = self.logger.write

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
                          averagingMethod=self.protocol['averagingMethod'],
                          customMaskPath=self.protocol['customMaskPath'])
        self.result['output']['success']=True
        return self.result
        

### User defined methods
    
    def verify_path(self, file_path):
        if len(file_path) > 0 and file_path and Path(file_path).exists():
            return True
        else: return False

    def mask_antspynet(self,params):
        import ants 
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
            print(averaged_path)
            nibabel.save(averaged_image, averaged_path)
        fractional_threshold=float(self.protocol.get('betFractionalThreshold', 0.5))
        if not 0 < fractional_threshold < 1:
            raise ValueError("betFractionalThreshold must be between 0 and 1 (exclusive): {}".format(fractional_threshold))
        logger("bet fractional intensity threshold (-f) : {}".format(fractional_threshold),prep.Color.INFO)
        cmd_output=fsl.bet(averaged_path, output_image_path, fractional_threshold=fractional_threshold)
        mask=DWI(output_mask_path)
        mask.setSpaceDirection(self.getSourceImageInformation()['space'])
        mask.writeImage(output_mask_path_nrrd,dest_type='nrrd')
        self.addOutputFile(output_mask_path, 'Mask')
        self.addOutputFile(output_mask_path_nrrd, 'Mask')
        self.addGlobalVariable('mask_path',output_mask_path_nrrd)
        res=None
        return res

    def mask_input(self, source, name):
        """3D image a brain extraction network (*name*) is applied to: the axial diffusivity (AD) of a DTI fit of the
        current image ('ad'), or the average of its baseline (b=0) images ('b0'). Returns (image, description)."""
        gradients = self.image.getGradients(self.baseline_threshold)
        baseline = np.array([g['baseline'] for g in gradients])
        if source == 'b0':
            if not baseline.any():
                raise ValueError("{} input b0: the image has no baseline (b=0) volume".format(name))
            return self.image.images[..., baseline].mean(axis=3), "average of {} baseline image(s)".format(int(baseline.sum()))
        if source != 'ad':
            raise ValueError("Unknown {} input: {} (ad or b0)".format(name, source))
        import dipy.reconst.dti as dti
        from dipy.core.gradients import gradient_table
        bvals = np.array([g['b_value'] for g in gradients], dtype=np.float64)
        bvecs = np.array([g['unit_gradient'] for g in gradients], dtype=np.float64)
        if not baseline.any() or baseline.all():
            raise ValueError("{} input ad: the DTI fit needs baseline (b=0) and diffusion weighted volumes".format(name))
        ## DTI regime: the diffusion weighted volumes up to b=1500 when there are any, all of them otherwise
        use = baseline | (bvals <= 1500)
        if use.sum() == baseline.sum():
            use = np.ones(len(bvals), dtype=bool)
        gtab = gradient_table(bvals[use], bvecs[use], b0_threshold=max(float(self.baseline_threshold), float(bvals[baseline].max())))
        fitted = dti.TensorModel(gtab, fit_method='WLS').fit(self.image.images[..., use])
        ad = np.clip(np.nan_to_num(fitted.ad), 0, None)
        return ad, "axial diffusivity of a DTI fit (WLS, {} volumes, b <= {:g})".format(int(use.sum()), bvals[use].max())

    def write_mask_input(self, source, name, filename):
        image, description = self.mask_input(source, name)
        logger("{} input : {}".format(name, description),prep.Color.INFO)
        input_path = Path(self.output_dir).joinpath(filename).__str__()
        nibabel.save(nibabel.Nifti1Image(image.astype(np.float32), self.image.getAffineMatrixForNifti()), input_path)
        return input_path

    def register_mask(self, output_mask_path):
        """Writes the NRRD version of the mask (NIfTI) and makes it the module's output mask."""
        output_mask_path_nrrd = Path(self.output_dir).joinpath("mask.nrrd").__str__()
        mask=DWI(output_mask_path)
        mask.setSpaceDirection(self.getSourceImageInformation()['space'])
        mask.writeImage(output_mask_path_nrrd,dest_type='nrrd')
        self.addOutputFile(output_mask_path, 'Mask')
        self.addOutputFile(output_mask_path_nrrd, 'Mask')
        self.addGlobalVariable('mask_path',output_mask_path_nrrd)

    def mask_synthstrip(self, params):
        from dtiplayground.dmri.common import synthstrip
        border = float(self.protocol.get('synthstripBorder', 1.0))
        no_csf = bool(self.protocol.get('synthstripNoCSF', False))
        implementation = str(self.protocol.get('synthstripImplementation', 'auto') or 'auto').lower()
        source = str(self.protocol.get('synthstripInput', 'ad') or 'ad').lower()
        output_mask_path = Path(self.output_dir).joinpath("mask.nii.gz").__str__()
        input_path = self.write_mask_input(source, 'SynthStrip', "synthstrip_input.nii.gz")

        executable = None
        if implementation in ('auto', 'freesurfer'):
            executable = synthstrip.find_mri_synthstrip(self.protocol.get('synthstripPath'))
            if executable is None and implementation == 'freesurfer':
                raise Exception("FreeSurfer's mri_synthstrip not found (synthstripPath, $FREESURFER_HOME or the PATH)")
        elif implementation != 'builtin':
            raise ValueError("Unknown synthstripImplementation: {} (auto, freesurfer or builtin)".format(implementation))
        logger("SynthStrip (border {} mm{}) : {}".format(border, ', CSF excluded' if no_csf else '',
               executable if executable else 'built-in (torch)'),prep.Color.PROCESS)
        if executable:
            command, _ = synthstrip.run_mri_synthstrip(executable, input_path, output_mask_path, border, no_csf, self.num_threads)
            logger(' '.join(command),prep.Color.INFO)
        else:
            try:
                import torch
            except ImportError:
                raise Exception("The built-in SynthStrip needs torch (pip install torch), or install FreeSurfer (7.3+) and set synthstripPath")
            synthstrip.run_builtin(input_path, output_mask_path, border, no_csf, self.num_threads)
        logger("If you use SynthStrip, please cite: A Hoopes, JS Mora, AV Dalca, B Fischl, M Hoffmann, SynthStrip: "
               "Skull-Stripping for Any Brain Image, NeuroImage 206 (2022), 119474",prep.Color.INFO)
        self.register_mask(output_mask_path)
        return None

    def mask_hdbet(self, params):
        from dtiplayground.dmri.common import hdbet
        device = str(self.protocol.get('hdbetDevice', 'auto') or 'auto').lower()
        tta = bool(self.protocol.get('hdbetTTA', True))
        if device not in ('auto', 'cuda', 'cpu'):
            raise ValueError("Unknown hdbetDevice: {} (auto, cuda or cpu)".format(device))
        executable = hdbet.find_hdbet(self.protocol.get('hdbetPath'))
        if executable is None:
            raise Exception("hd-bet not found (hdbetPath, the Python environment of dtiplayground or the PATH); "
                            "install it with pip install hd-bet, e.g. in a separate environment, and set hdbetPath")
        output_mask_path = Path(self.output_dir).joinpath("mask.nii.gz").__str__()
        input_path = self.write_mask_input('b0', 'HD-BET', "hdbet_input.nii.gz")
        logger("HD-BET ({}test time augmentation) : {}".format('' if tta else 'no ', executable),prep.Color.PROCESS)
        command, device = hdbet.run_hdbet(executable, input_path, output_mask_path, device=device, tta=tta)
        logger(' '.join(command),prep.Color.INFO)
        logger("If you use HD-BET, please cite: F Isensee, M Schell, I Pflueger, et al., Automated brain extraction of "
               "multisequence MRI using artificial neural networks, Human Brain Mapping 40 (2019), 4952-4964",prep.Color.INFO)
        self.register_mask(output_mask_path)
        return None

    def mask_median_otsu(self, params):
        from dipy.segment.mask import median_otsu
        radius = int(self.protocol.get('medianOtsuRadius', 4))
        numpass = int(self.protocol.get('medianOtsuNumpass', 4))
        dilate = int(self.protocol.get('medianOtsuDilate', 0))
        gradients = self.image.getGradients(self.baseline_threshold)
        baseline = np.nonzero([g['baseline'] for g in gradients])[0]
        if len(baseline) == 0:
            logger("No baseline (b=0) image, median_otsu uses the average of all volumes",prep.Color.WARNING)
            baseline = np.arange(len(gradients))
        logger("dipy median_otsu (median radius {}, {} pass(es), dilation {}) on the average of {} volume(s)".format(
               radius, numpass, dilate, len(baseline)),prep.Color.PROCESS)
        _, mask = median_otsu(self.image.images, vol_idx=baseline, median_radius=radius, numpass=numpass,
                              dilate=dilate if dilate > 0 else None)
        output_mask_path = Path(self.output_dir).joinpath("mask.nii.gz").__str__()
        nibabel.save(nibabel.Nifti1Image(mask.astype(np.uint8), self.image.getAffineMatrixForNifti()), output_mask_path)
        self.register_mask(output_mask_path)
        return None

    def custom_mask(self, params):
        logger("Custom Mask is running ...",prep.Color.INFO)
        input_image_base=Path(self.output_dir).joinpath("input").__str__()
        output_image_base=Path(self.output_dir).joinpath("mask").__str__()

        input_image_path=input_image_base+".nii.gz"
        output_mask_path=output_image_base+".nii.gz"
        output_mask_path_nrrd=output_image_base+".nrrd"
        src_image=params['image']
        custom_mask_path=params['customMaskPath']
        if not self.verify_path(custom_mask_path):
            logger("Mask path cannot be verified",prep.Color.ERROR)
            return False
        src_image.writeImage(input_image_path,dest_type='nifti')
        mask=DWI(custom_mask_path)
        mask.setSpaceDirection(self.getSourceImageInformation()['space'])
        mask.writeImage(output_mask_path_nrrd,dest_type='nrrd')
        mask.writeImage(output_mask_path,dest_type='nifti')
        self.addOutputFile(output_mask_path, 'Mask')
        self.addOutputFile(output_mask_path_nrrd, 'Mask')
        self.addGlobalVariable('mask_path',output_mask_path_nrrd)
        res=None
        return res

    def run_mask(self, method, averagingMethod, customMaskPath):
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
        elif method=='synthstrip':
            res=self.mask_synthstrip({'image': self.image})
        elif method=='hdbet':
            res=self.mask_hdbet({'image': self.image})
        elif method=='medianOtsu':
            res=self.mask_median_otsu({'image': self.image})
        elif method=='customMask':
            params={
                'image': self.image,
                'customMaskPath': customMaskPath
            }
            res=self.custom_mask(params)
        logger("Mask generation is completed",prep.Color.OK)
        return res


