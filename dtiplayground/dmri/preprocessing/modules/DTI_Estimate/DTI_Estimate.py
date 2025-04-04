import dtiplayground.dmri.preprocessing as prep
from dtiplayground.dmri.common import measure_time
import dtiplayground.dmri.common.tools as tools 
from dtiplayground.dmri.common.dwi import DWI
import yaml
from pathlib import Path
import copy

import numpy as np
import dipy.reconst.dti as dti
from dipy.core.gradients import gradient_table
import dipy.denoise.noise_estimate as ne
from dipy.io.image import save_nifti


class DTI_Estimate(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)
        global logger
        logger = self.logger.write

    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    def process(self,*args,**kwargs): ## variables : self.global_variables, self.softwares, self.output_dir, self.config_dir, self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        # << TODOS>>
        protocol_options=args[0]
        self.num_threads=protocol_options['software_info']['parameters']['num_max_threads']
        self.software_info=protocol_options['software_info']['softwares']
        self.baseline_threshold=protocol_options['baseline_threshold']
        self.global_vars=self.getGlobalVariables()
        res=self.runDTI(method=self.protocol['method'],
                        optimizationMethod=self.protocol['optimizationMethod'],
                        correctionMethod=self.protocol['correctionMethod'])
        self.result['output']['success']=True
        return self.result


### User defined methods

    def runDTI(self,method, optimizationMethod, correctionMethod):
        res = None
        if method.lower() == 'dipy':
            logger("Using {}".format(method),prep.Color.INFO)
            res = self.runDTI_DIPY(optimizationMethod)
        elif method.lower() == 'dtiestim':
            logger("Using {}".format(method),prep.Color.INFO)
            res = self.runDTI_dtiestim(optimizationMethod,correctionMethod)
        else:
            raise Exception("Unknown method name : {}".format(method))
    
    @measure_time
    def runDTI_DIPY(self, optimizationMethod):
        
        # data prep for dipy
        data = self.image.images
        affine = self.image.getAffineMatrixForNifti()
        bvals= np.array(list(map(lambda x: x['b_value'], self.image.getGradients())))
        b0=min(bvals)
        bvecs= np.array(list(map(lambda x: x['unit_gradient'], self.image.getGradients())))
        gtab = gradient_table(bvals,bvecs,b0_threshold=min(max(b0,50),199))
        logger("Affine Matrix (RAS) : \n{}".format(affine),prep.Color.INFO)
        # option parse
        optionmap = { 'lls' : 'LS',
                      'wls' : 'WLS',
                      'nls': 'NLLS',
                      'restore' : 'RESTORE' }
        fitMethod="WLS"
        kwargs={}
        try:
            fitMethod=optionmap[optimizationMethod]
            if fitMethod=='RESTORE':
                kwargs={ 'sigma': ne.estimate_sigma(data) }
        except:
            fitMethod="WLS"
            logger("WARNING: The method {} is not available with the method. Changing it to {}.".format(optimizationMethod,fitMethod), prep.Color.WARNING)

        # Try loading mask if exists
        mask=None
        if 'mask_path' in self.global_vars:
            mpath = self.global_vars['mask_path']
            if Path(mpath).exists():
                logger('Mask file found : {}'.format(self.global_vars['mask_path']),prep.Color.OK)
                temp_img=DWI(mpath)
                mask=temp_img.images
            else:
                logger('Mask not found, estimating whole image...',prep.Color.WARNING)
        else:
            logger('Mask not found, estimating whole image...',prep.Color.WARNING)
        # fitting and estimation of scalars
        dti_fit = dti.TensorModel(gtab,fit_method=fitMethod,**kwargs)
        logger("Running with {}, {}".format(fitMethod, kwargs),prep.Color.PROCESS)
        #fitted = dti_fit.fit(data) ## dti_fit.fit(data, mask) mask array (boolean)
        try:
            fitted = dti_fit.fit(data,mask)
            logger("Fitting completed",prep.Color.OK)
        except ValueError as e:
            logger("Mask is not the same shape as data.",prep.Color.ERROR)
            raise ValueError


        ## convert 3x3 symmetric matrices to xx,xy,xz,yy,yz,zz vectors
        logger("Reducing 3x3 symmetric matrix to vector")
        def uppertriangle(matrix):
            outvec=[]
            for i in range(3):
                for j in range(i,3):
                    outvec.append(matrix[i,j])
            return np.array(outvec)
        quad_form = fitted.quadratic_form
        new_quadform = np.empty(quad_form.shape[:-1] + (6,), dtype=float)
        for d1 in range(quad_form.shape[0]):
            for d2 in range(quad_form.shape[1]):
                for d3 in range(quad_form.shape[2]):
                    mat = quad_form[d1,d2,d3]
                    new_quadform[d1,d2,d3]=uppertriangle(mat)

        # TODO : make nrrd file for new_quadform image volume (kind will be "3D-symmetric-matrix") , ref: http://teem.sourceforge.net/nrrd/format.html
        temp_dti_image = DWI()
        temp_dti_image.copyFrom(self.image, image=False, gradients=False)
        temp_dti_image.setImage(new_quadform,modality='DTI', kinds=['space','space','space','3D-symmetric-matrix'])
        dti_filename=Path(self.output_dir).joinpath('tensor.nrrd').__str__()
        sp_dir=self.getSourceImageInformation()['space']
        temp_dti_image.setSpaceDirection(target_space=sp_dir)
        temp_dti_image.writeImage(dti_filename,dest_type='nrrd',dtype="float32")
        self.addOutputFile(dti_filename, 'DTI')
        self.addGlobalVariable('dti_path',dti_filename)
        # retrieve outputs
        evals = fitted.evals
        evecs = fitted.evecs
        scalarData={
            'eigenval': evals,
            'eigenvec': evecs,
            'fa': fitted.fa,
            'cfa': dti.color_fa(fitted.fa,evecs),
            'md': fitted.md,
            'ad': fitted.ad,
            'rd': fitted.rd    
        }
        # sphere = dpd.default_sphere

        # saving outputs
        for scalar, val in scalarData.items():
            output_tensor_path = Path(self.output_dir).joinpath('tensor_{}.nii.gz'.format(scalar)).__str__()
            val[np.isnan(val)] = 0
            num_type=np.float32
            save_nifti(output_tensor_path, val.astype(num_type), affine)
            self.addOutputFile(output_tensor_path, 'DTI_{}'.format(scalar.upper()))

        return None

    @measure_time
    def runDTI_dtiestim(self, optimizationMethod, correctionMethod):

        # option parse
        optionmap = { 'lls' : 'lls',
                      'wls' : 'wls',
                      'nls': 'nls',
                      'ml' : 'ml'}
        fitMethod="wls"
        try:
            fitMethod=optionmap[optimizationMethod]
        except:
            fitMethod="wls"
            logger("WARNING: The method {} is not available with the method. Changing it to {}.".format(optimizationMethod,fitMethod), prep.Color.WARNING)

        temp_dti_image = DWI()
        temp_dti_image.copyFrom(self.image, image=True, gradients=True)
        dtiestim=tools.DTIEstim(self.software_info['dtiestim']['path'])
        input_image_path = Path(self.output_dir).joinpath('input.nrrd').__str__()
        output_tensor_path = Path(self.output_dir).joinpath('tensor.nrrd').__str__()
        sp_dir=self.getSourceImageInformation()['space']
        temp_dti_image.setSpaceDirection(target_space=sp_dir)
        temp_dti_image.writeImage(str(input_image_path),dest_type='nrrd')
        options = [ '-m',fitMethod,
                    '--correction', correctionMethod]

        dtiestim.estimate(input_image_path, output_tensor_path,options)
        self.addOutputFile(output_tensor_path, 'DTI')
        self.addGlobalVariable('dti_path',output_tensor_path)
        return None