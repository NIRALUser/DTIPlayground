#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import dtiplayground.dmri.preprocessing as prep
from dtiplayground.dmri.common import measure_time
from dtiplayground.dmri.common.dwi import DWI
from pathlib import Path
import subprocess
import shutil
import numpy as np
import nibabel as nib

import dipy.reconst.dti as dti
import dipy.reconst.fwdti as fwdti
import dipy.reconst.msdki as msdki
import dipy.reconst.dki as dki
import dipy.reconst.ivim as ivim
from dipy.core.gradients import gradient_table
import dipy.denoise.noise_estimate as ne
from dipy.io.image import save_nifti

## upper triangle of a 3x3 symmetric matrix: xx,xy,xz,yy,yz,zz (NRRD 3D-symmetric-matrix without the mask value)
TENSOR_COMPONENTS = [(0,0),(0,1),(0,2),(1,1),(1,2),(2,2)]

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
                            'dki': { 'wls' : 'WLS',
                                    'ols' : 'OLS',
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
        tool = self.protocol['tool']
        model = self.protocol.get('model', 'dti')
        if tool == 'amico':
            optimization_method = self.protocol.get('optimizationMethod_dti', 'wls')
        elif model in ['dti', 'fwdti', 'dki', 'msdki']:
            optimization_method = self.protocol.get('optimizationMethod_{}'.format('dki' if model == 'msdki' else model), 'wls')
        elif model == 'ivim':
            split_b_d = self.protocol['split_b_D']
            split_b_s = self.protocol['split_b_S0']
            optimization_method = f'{split_b_d}, {split_b_s}'
        else:
            optimization_method = ''

        res=self.runMSE(tool=tool,
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
            self.runAMICO(optimizationMethod)
        elif tool.lower() == 'mrtrix3':
            self.runMRTRIX3()
        else:
            raise Exception("Unknown method name : {}".format(tool))

    def loadMask(self):
        """Brain mask (array on the grid of the image): the protocol's maskPath, else the mask of BRAIN_Mask, else None"""
        candidates = [self.protocol.get('maskPath'), self.global_vars.get('mask_path')]
        for mpath in candidates:
            if not mpath:
                continue
            if Path(mpath).exists():
                logger('Mask file found : {}'.format(mpath),prep.Color.OK)
                mask = DWI(str(mpath)).images > 0
                if mask.shape != self.image.images.shape[:3]:
                    raise ValueError("Mask {} has shape {}, the image {}".format(mpath, mask.shape, self.image.images.shape[:3]))
                return mask
            logger('Mask {} not found'.format(mpath),prep.Color.WARNING)
        logger('Mask not found, estimating whole image...',prep.Color.WARNING)
        return None

    def writeTensorImage(self, image, name, modality, kind):
        """Write a (X,Y,Z,N) image of tensor components as NRRD with the geometry and measurement frame of the input"""
        image = np.nan_to_num(image)
        temp_image = DWI()
        temp_image.copyFrom(self.image, image=False, gradients=False)
        temp_image.setImage(image, modality=modality, kinds=['space','space','space',kind])
        filename = Path(self.output_dir).joinpath(name).__str__()
        sp_dir = self.getSourceImageInformation()['space']
        temp_image.setSpaceDirection(target_space=sp_dir)
        temp_image.writeImage(filename,dest_type='nrrd',dtype="float32")
        return filename

    def writeDiffusionTensor(self, quad_form, modality, output_name):
        ## convert 3x3 symmetric matrices (X,Y,Z,3,3) to xx,xy,xz,yy,yz,zz vectors (X,Y,Z,6), in the frame of the
        ## gradients used for the fit (the measurement frame of the image, written in the header)
        logger("Reducing 3x3 symmetric matrix to vector")
        tensor = np.stack([quad_form[...,i,j] for i,j in TENSOR_COMPONENTS], axis=-1)
        filename = self.writeTensorImage(tensor, 'tensor.nrrd', modality, '3D-symmetric-matrix')
        self.addOutputFile(filename, output_name)
        self.addGlobalVariable('dipy_path',filename)

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
        logger("Shells (b-values) : {}".format(sorted(set(np.round(bvals,-1).astype(int).tolist()))),prep.Color.INFO)

        # option parse
        kwargs={}
        fitMethod="WLS"
        conversion_key = 'dki' if model == 'msdki' else model
        if conversion_key in dipy_conversion:
            optionmap = dipy_conversion[conversion_key]
            try:
                fitMethod=optionmap[optimizationMethod]
                if fitMethod=='RESTORE':
                    kwargs={ 'sigma': ne.estimate_sigma(data) }
            except:
                fitMethod="WLS"
                logger("WARNING: The method {} is not available with the method. Changing it to {}.".format(optimizationMethod,fitMethod), prep.Color.WARNING)

        mask = self.loadMask()

        # fitting and estimation of scalars
        logger("Running with {}, {}".format(fitMethod, kwargs),prep.Color.PROCESS)
        if model == 'dti':
            fitted = dti.TensorModel(gtab,fit_method=fitMethod,**kwargs).fit(data,mask)
        elif model == 'dki':
            fitted = dki.DiffusionKurtosisModel(gtab,fit_method=fitMethod).fit(data,mask)
        elif model == 'msdki':
            fitted = msdki.MeanDiffusionKurtosisModel(gtab).fit(data,mask)
            ## the diffusion and kurtosis tensors come from the full DKI model
            fitted_dki = dki.DiffusionKurtosisModel(gtab,fit_method=fitMethod).fit(data,mask)
        elif model == 'fwdti':
            fitted = fwdti.FreeWaterTensorModel(gtab,fit_method=fitMethod).fit(data,mask)
        elif model == 'ivim':
            split_options = optimizationMethod.split(',')
            fitted = ivim.IvimModelTRR(gtab, split_b_D=float(split_options[0]), split_b_S0=float(split_options[1])).fit(data,mask)
        else:
            raise Exception("Unknown model : {}".format(model))
        logger("Fitting completed",prep.Color.OK)

        ## tensors, in the frame of the gradients used for the fit (the measurement frame of the image)
        tensor_fit = fitted_dki if model == 'msdki' else fitted
        if model in ['dti', 'fwdti']:
            self.writeDiffusionTensor(fitted.quadratic_form, model.upper(), model.upper())
        if model in ['dki', 'msdki']:
            self.writeDiffusionTensor(tensor_fit.quadratic_form, 'DKI', 'DKI')
            ## 15 independent elements of the kurtosis tensor, in the order of dipy:
            ## Wxxxx Wyyyy Wzzzz Wxxxy Wxxxz Wxyyy Wyyyz Wxzzz Wyzzz Wxxyy Wxxzz Wyyzz Wxxyz Wxyyz Wxyzz
            kurtosis_filename = self.writeTensorImage(tensor_fit.kt, 'kurtosis_tensor.nrrd', 'DKI', 'list')
            self.addOutputFile(kurtosis_filename, 'Kurtosis')

        scalarData={}
        if model == 'dti':
            scalarData = {
                'eigenval': fitted.evals,
                'eigenvec': fitted.evecs,
                'fa': fitted.fa,
                'cfa': dti.color_fa(fitted.fa,fitted.evecs),
                'md': fitted.md,
                'ad': fitted.ad,
                'rd': fitted.rd
            }
        elif model == 'fwdti':
            scalarData = {
                'eigenval': fitted.evals,
                'eigenvec': fitted.evecs,
                'fa': fitted.fa,
                'md': fitted.md,
                'ad': fitted.ad,
                'rd': fitted.rd,
                'fw': fitted.f
            }
        elif model == 'dki':
            scalarData = {
                'eigenval': fitted.evals,
                'eigenvec': fitted.evecs,
                'fa': fitted.fa,
                'md': fitted.md,
                'ad': fitted.ad,
                'rd': fitted.rd,
                'mk': fitted.mk(0, 3),
                'ak': fitted.ak(0, 3),
                'rk': fitted.rk(0, 3),
                'mkt': fitted.mkt(0, 3),
                'kfa': fitted.kfa
            }
        elif model == 'msdki':
            scalarData = {
                'eigenval': fitted_dki.evals,
                'eigenvec': fitted_dki.evecs,
                'msd': fitted.msd,
                'msk': fitted.msk
            }
        elif model == 'ivim':
            scalarData = {
                'S0': fitted.S0_predicted,
                'perfusion_frac': fitted.perfusion_fraction,
                'Dstar': fitted.D_star,
                'D': fitted.D
            }

        # saving outputs
        for scalar, val in scalarData.items():
            output_tensor_path = Path(self.output_dir).joinpath('tensor_{}.nii.gz'.format(scalar)).__str__()
            val = np.nan_to_num(np.asarray(val, dtype=np.float64))
            save_nifti(output_tensor_path, val.astype(np.float32), affine)
            self.addOutputFile(output_tensor_path, '{}_{}'.format(model.upper(), scalar.upper()))

        return None

    def writeNiftiInputs(self, stem):
        """Current image (after the previous modules) as NIfTI with FSL bvals/bvecs, and the mask as NIfTI (or None)"""
        out_dir = Path(self.output_dir)
        dwi_path = out_dir.joinpath(stem+'.nii.gz')
        self.image.writeImage(str(dwi_path), dest_type='nifti', dtype='float32')
        ## the DWI writer puts one gradient per line: rewrite them in the FSL layout (bvals 1xN, bvecs 3xN)
        bval_path, bvec_path = out_dir.joinpath(stem+'.bval'), out_dir.joinpath(stem+'.bvec')
        np.savetxt(str(bval_path), np.loadtxt(str(bval_path)).reshape(1,-1), fmt='%d')
        np.savetxt(str(bvec_path), np.loadtxt(str(bvec_path)).reshape(-1,3).T, fmt='%.8f')
        mask = self.loadMask()
        mask_path = None
        if mask is not None:
            mask_path = out_dir.joinpath(stem+'_mask.nii.gz')
            nib.save(nib.Nifti1Image(mask.astype(np.uint8), self.image.getAffineMatrixForNifti()), str(mask_path))
        return dwi_path, bval_path, bvec_path, mask_path

    def checkMRTRIX3(self, cmd='dwi2adc'):
        """Check if MRtrix3 is installed by verifying a command like 'dwi2adc'."""
        if shutil.which(cmd) is None:
            return False
        return True

    @measure_time
    def runMRTRIX3(self):
        mrtrix_checker = self.checkMRTRIX3()
        if not mrtrix_checker:
            logger(f"mrtrix3 is not installed, follow instructions on the next two lines", prep.Color.ERROR)
            logger(f"Conda Install: https://www.mrtrix.org/download/", prep.Color.INFO)
            logger(f"Binary Install: https://mrtrix.readthedocs.io/en/latest/installation/package_install.html", prep.Color.INFO)
            raise Exception("mrtrix3 (dwi2adc) is not installed")

        dwi_path, bval_path, bvec_path, _ = self.writeNiftiInputs('mrtrix_input')
        output_filename=Path(self.output_dir).joinpath('adc.nii.gz').__str__()
        command = ['dwi2adc', '-force', '-nthreads', str(self.num_threads), '-fslgrad', str(bvec_path), str(bval_path),
                   str(dwi_path), output_filename]
        logger("Running {}".format(' '.join(command)),prep.Color.PROCESS)
        value = subprocess.run(command, capture_output=True, text=True)
        if value.returncode != 0 or not Path(output_filename).exists():
            raise Exception(f"Error running {' '.join(command)}\n{value.stderr}")
        ## dwi2adc writes 2 volumes: S0 and ADC
        img = nib.load(output_filename)
        for idx, name in enumerate(['S0', 'ADC']):
            path = Path(self.output_dir).joinpath('adc_{}.nii.gz'.format(name.lower())).__str__()
            nib.save(nib.Nifti1Image(np.asarray(img.dataobj)[...,idx].astype(np.float32), img.affine), path)
            self.addOutputFile(path, 'MRTRIX3_{}'.format(name))
        return None

    @measure_time
    def runAMICO(self, optimizationMethod):
        import amico
        fitMethod = dipy_conversion['dti'].get(optimizationMethod, 'WLS')
        out_dir = Path(self.output_dir)
        ## AMICO reads files: the current image (after the previous modules), its gradients and the mask
        dwi_path, bval_path, bvec_path, mask_path = self.writeNiftiInputs('amico_input')
        scheme_path = out_dir.joinpath('amico_input.scheme')
        amico.setup()
        amico.util.fsl2scheme(str(bval_path), str(bvec_path), schemeFilename=str(scheme_path), bStep=100)
        results_path = out_dir.joinpath('AMICO')
        ae = amico.Evaluation(study_path=str(out_dir), subject='.', output_path=str(results_path))
        ae.set_config('DTI_fit_method', fitMethod)
        ae.set_config('nthreads', int(self.num_threads))
        ae.set_config('BLAS_nthreads', int(self.num_threads))
        ae.load_data(str(dwi_path), str(scheme_path), mask_filename=None if mask_path is None else str(mask_path),
                     b0_thr=self.baseline_threshold)
        ae.set_model('NODDI')
        ae.generate_kernels(ndirs=2000,regenerate=True)
        ae.load_kernels()
        ae.fit()
        ae.save_results()

        for name in ['NDI', 'ODI', 'FWF', 'dir']:
            path = results_path.joinpath('fit_{}.nii.gz'.format(name))
            if path.exists():
                self.addOutputFile(str(path), 'NODDI_{}'.format(name.upper()))
            else:
                logger('AMICO output {} not found'.format(path),prep.Color.WARNING)
        return None
