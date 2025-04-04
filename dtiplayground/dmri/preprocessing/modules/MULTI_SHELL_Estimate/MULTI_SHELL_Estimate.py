#!/usr/bin/env python3
# -*- coding: utf-8 -*- 

import dtiplayground.dmri.preprocessing as prep
from dtiplayground.dmri.common import measure_time
import dtiplayground.dmri.common.tools as tools 
from dtiplayground.dmri.common.dwi import DWI
import yaml
from pathlib import Path
import copy
import subprocess
import os
import numpy as np
import amico

import numpy as np
from dipy.reconst.vec_val_sum import vec_val_vect
import dipy.reconst.dti as dti
import dipy.reconst.fwdti as fwdti
import dipy.reconst.msdki as msdki
import dipy.reconst.dki as dki
import dipy.reconst.ivim as ivim
from dipy.core.gradients import gradient_table
import dipy.denoise.noise_estimate as ne
from dipy.io.image import save_nifti


class MULTI_SHELL_Estimate(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)
        global logger
        global dipy_conversion
        logger = self.logger.write
        dipy_conversion = { 'dti': { 'lls' : 'LS',
                                    'wls' : 'WLS',
                                    'nls': 'NLLS',
                                    'ols': 'OLS',
                                    'restore' : 'RESTORE' },
                            'fwdti': { 'wls' : 'WLS',
                                    'nls' : 'NLS' },                            
                            }

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
        model = self.protocol['model']
        if model in ['dti', 'fwdti']:
            optimization_method = self.protocol[f'optimizationMethod_{model}']
        elif model == 'ivim':
            split_b_d = self.protocol['split_b_D']
            split_b_s = self.protocol['split_b_S0']
            optimization_method = f'{split_b_d}, {split_b_s}'
        else:
            optimization_method = ''
        
        res=self.runMSE(tool=self.protocol['tool'],
                        optimizationMethod=optimization_method,
                        model=model)
        self.result['output']['success']=True
        return self.result


### User defined methods

    def runMSE(self,tool, optimizationMethod, model):
        res = None
        logger("Using {}".format(tool),prep.Color.INFO)
        if tool.lower() == 'dipy':
            self.runDIPY(optimizationMethod, model)
        elif tool.lower() == 'amico':
            self.runAMICCO(optimizationMethod)
        elif tool.lower() == 'mrtrix3':
            self.runMRTRIX3()
        else:
            raise Exception("Unknown method name : {}".format(tool))

### dipy functions  
    @measure_time
    def runDIPY(self, optimizationMethod, model):
        
        # data prep for dipy
        data = self.image.images
        affine = self.image.getAffineMatrixForNifti()
        bvals= np.array(list(map(lambda x: x['b_value'], self.image.getGradients())))
        b0=min(bvals)
        bvecs= np.array(list(map(lambda x: x['unit_gradient'], self.image.getGradients())))
        if model != 'ivim':
            gtab = gradient_table(bvals,bvecs,b0_threshold=min(max(b0,50),199))
        else:
            gtab = gradient_table(bvals,bvecs,b0_threshold=0)
        logger("Affine Matrix (RAS) : \n{}".format(affine),prep.Color.INFO)

        # option parse
        optionmap = {}
        kwargs={}
        fitMethod="WLS"
        if model in ['dti', 'fwdti']:
            optionmap = dipy_conversion[model]
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
        logger("Running with {}, {}".format(fitMethod, kwargs),prep.Color.PROCESS)
        image_fit = None

        if model == 'dti':
            image_fit = dti.TensorModel(gtab,fit_method=fitMethod,**kwargs)
        elif model == 'msdki':
            image_fit = msdki.MeanDiffusionKurtosisModel(gtab,**kwargs)
            image_fit2 = dki.DiffusionKurtosisModel(gtab,fit_method=fitMethod,**kwargs)
        elif model == 'fwdti':
            image_fit = fwdti.FreeWaterTensorModel(gtab,fit_method=fitMethod,**kwargs)
        elif model == 'ivim':
            split_options = optimizationMethod.split(',')
            image_fit = ivim.IvimModelTRR(gtab, split_b_D=float(split_options[0]), split_b_S0=float(split_options[1]), **kwargs)
            


        
        try:
            fitted = image_fit.fit(data,mask)
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
        
        if model in ['dti', 'fwdti', 'msdki']:
            if model != 'msdki':
                quad_form = fitted.quadratic_form
            else:
                fitted2 = image_fit2.fit(data,mask)
                quad_form = fitted2.quadratic_form
            
            new_quadform = np.empty(quad_form.shape[:-1] + (6,), dtype=float)
            for d1 in range(quad_form.shape[0]):
                for d2 in range(quad_form.shape[1]):
                    for d3 in range(quad_form.shape[2]):
                        mat = quad_form[d1, d2, d3]
                        new_quadform[d1, d2, d3] = uppertriangle(mat)

        if model in ['dti', 'fwdti']:
            temp_dipy_image = DWI()
            temp_dipy_image.copyFrom(self.image, image=False, gradients=False)
            temp_dipy_image.setImage(new_quadform,modality=model.upper(), kinds=['space','space','space','3D-symmetric-matrix'])
            dipy_filename=Path(self.output_dir).joinpath('tensor.nrrd').__str__()
            sp_dir=self.getSourceImageInformation()['space']
            temp_dipy_image.setSpaceDirection(target_space=sp_dir)
            temp_dipy_image.writeImage(dipy_filename,dest_type='nrrd',dtype="float32")
            self.addOutputFile(dipy_filename, model.upper())
            self.addGlobalVariable('dipy_path',dipy_filename)
        if model == 'msdki':
            temp_dipy_image = DWI()
            temp_dipy_image.copyFrom(self.image, image=False, gradients=False)
            temp_dipy_image.setImage(new_quadform,modality='DKI', kinds=['space','space','space','3D-symmetric-matrix'])
            dipy_filename=Path(self.output_dir).joinpath('tensor.nrrd').__str__()
            sp_dir=self.getSourceImageInformation()['space']
            temp_dipy_image.setSpaceDirection(target_space=sp_dir)
            temp_dipy_image.writeImage(dipy_filename,dest_type='nrrd',dtype="float32")
            self.addOutputFile(dipy_filename, 'DKI')
            self.addGlobalVariable('dipy_path',dipy_filename)
            if fitted.model_params.shape[1] > 11:
                kurtosis_params = fitted.model_params[..., 12:]
                temp_dki_kurtosis = DWI()
                temp_dki_kurtosis.copyFrom(self.image, image=False, gradients=False)
                temp_dki_kurtosis.setImage(kurtosis_params, modality='DKI', kinds=['space', 'space', 'space', 'kurtosis'])
                kurtosis_filename=Path(self.output_dir).joinpath('kurtosis_tensor.nrrd').__str__()
                sp_dir=self.getSourceImageInformation()['space']
                temp_dki_kurtosis.setSpaceDirection(target_space=sp_dir)
                temp_dki_kurtosis.writeImage(kurtosis_filename,dest_type='nrrd',dtype="float32")
                self.addOutputFile(kurtosis_filename, 'Kurtosis')
                self.addGlobalVariable('dipy_path',dipy_filename)
            else:
                logger('Image shape is less than (12): Kurtosis data is not included')

        scalarData={}
        if model == 'dti':
            evals = fitted.evals
            evecs = fitted.evecs
            scalarData = {
                'eigenval': evals,
                'eigenvec': evecs,
                'fa': fitted.fa,
                'cfa': dti.color_fa(fitted.fa,evecs),
                'md': fitted.md,
                'ad': fitted.ad,
                'rd': fitted.rd    
            }
        elif model == 'fwdti':
            evals = fitted.evals
            evecs = fitted.evecs
            scalarData = {
                'eigenval': evals,
                'eigenvec': evecs,
                'fa': fitted.fa,
                'md': fitted.md,
                'ad': fitted.ad,
                'rd': fitted.rd    
            }
        elif model == 'msdki':
            evals = fitted2.evals
            evecs = fitted2.evecs
            scalarData = {
                'eigenval': evals,
                'eigenvec': evecs,
                'msd': fitted.msd,
                'msk': fitted.msk
            }
        elif model == 'ivim':
            scalarData = {
                'S0': fitted.S0_predicted,
                'perfusion_frac': fitted.perfusion_fraction,
                'D*': fitted.D_star,
                'D': fitted.D
            }

        # saving outputs
        for scalar, val in scalarData.items():
            output_tensor_path = Path(self.output_dir).joinpath('tensor_{}.nii.gz'.format(scalar)).__str__()
            val[np.isnan(val)] = 0
            num_type=np.float32
            save_nifti(output_tensor_path, val.astype(num_type), affine)
            self.addOutputFile(output_tensor_path, '{}_{}'.format(model.upper(), scalar.upper()))

        return None
    


    @measure_time
    def runMRTRIX3(self):
        gradient_filename=Path(self.output_dir).joinpath('gradients.txt').__str__()
        output_filename=Path(self.output_dir).joinpath('output_image.nii.gz').__str__()
        self.image.saveGradientFile(gradient_filename)
        command = [f'dwi2adc -force -nthreads {self.num_threads} -grad {gradient_filename} {self.image.filename} {output_filename}']
        try:
            # as of right now mrtrix3 pipes all outputs to stderr
            value = subprocess.run(command, capture_output=True, shell=True, text=True)
            print([value.stdout, value.stderr])
            if len(value.stderr) > 0 and 'error' not in value.stderr.lower() and '100' in value.stderr.lower():
                self.addOutputFile(output_filename, 'ADC')
            else:
                logger(f"Error running {command}\n{value.stderr}", prep.Color.ERROR)
        except Exception as e:
            logger(f"Error running {command}\nError: {e}", prep.Color.ERROR)

    def runAMICCO(self, optimizationMethod, model='dti'):
        optionmap = dipy_conversion[model]
        fitMethod=optionmap[optimizationMethod]
        image_path = Path(self.image.filename)
        parent_path = image_path.parent
        study_name = image_path.stem.split(".")[0]
        bvec_path = parent_path.joinpath(study_name+'.bvec')
        bval_path = parent_path.joinpath(study_name+'.bval')
        bvec = np.loadtxt(bvec_path)
        bvecT = np.transpose(bvec)
        bvecT_path = Path(self.output_dir).joinpath(f'{study_name}.bvecT').__str__()
        np.savetxt (bvecT_path, bvecT)
        bval = np.loadtxt(bval_path)
        bvalT = np.transpose(bval)
        bvalT_path = Path(self.output_dir).joinpath(f'{study_name}.bvalT').__str__()
        scheme_path  = Path(self.output_dir).joinpath(f'{study_name}.scheme').__str__()
        np.savetxt (bvalT_path, bvalT)
        amico.setup()
        amico.util.fsl2scheme(bvalT_path, bvecT_path, bStep = 100)
        ae = amico.Evaluation()
        ae.set_config('DTI_fit_method', fitMethod)
        ae.set_config('nthreads', int(self.num_threads))
        ae.set_config('BLAS_nthreads', int(self.num_threads))
        ae.set_config("study_path", self.output_dir)
        ae.set_config("OUTPUT_path", Path(self.output_dir).parent.parent.joinpath('amico_output'))

        # Try loading mask if exists
        mask=self.protocol['maskPath']
        if not mask:
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

        if mask:
            ae.load_data(image_path, scheme_path, mask_filename=mask, b0_thr=0)
        else:
            ae.load_data(image_path, scheme_path, b0_thr=0)
        ae.set_model('NODDI')
        ae.generate_kernels(ndirs=2000,regenerate=True)
        ae.load_kernels()
        ae.fit()
        ae.save_results()