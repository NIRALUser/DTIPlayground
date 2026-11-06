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

FIT_QC_FILES = ('fit_qc.tsv', 'fit.tsv', 'fit_carpet.png') # summary, per volume, slice x volume correlation


from dtiplayground.dmri.common.dwi import write_tensor_nrrd  # noqa: E402  (kept importable from here)


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
        for name in FIT_QC_FILES: ## computed again (makeReport) for this run
            Path(self.output_dir).joinpath(name).unlink(missing_ok=True)
        res=self.runDTI(method=self.protocol['method'],
                        optimizationMethod=self.protocol['optimizationMethod'],
                        correctionMethod=self.protocol['correctionMethod'])
        self.result['output']['success']=True
        return self.result

    def makeReport(self):
        super().makeReport()
        qc = self.fitQC()
        if not qc:
            return
        with open(str(Path(self.output_dir).joinpath('report.md')), 'a') as f:
            f.write('* Tensor fit (WLS) of each volume: R2 mean {} (min {}), correlation mean {} (min {})\n'
                    .format(qc['fit_r2_mean'], qc['fit_r2_min'], qc['fit_corr_mean'], qc['fit_corr_min']))
            f.write('* {}% of the mask voxels left out (a non-positive value in some volume, or a degenerate fit)\n'.format(qc.get('fit_excluded_voxels_percent')))
            f.write('* {} poorly fitted slices (slice R2 far below that of the same slice in the other volumes of the shell)\n\n'.format(qc['poor_fit_slices']))
            f.write("<img src='{}' width='640'>\n\n".format(Path(self.output_dir).joinpath('fit_carpet.png')))
        self.result['report']['csv_data']['fit_qc'] = qc
        with open(str(Path(self.output_dir).joinpath('result.yml')),'w') as f:
            yaml.dump(self.result,f)

    def fitQC(self):
        """Agreement of each volume and slice with the prediction of a WLS tensor fit (fit_qc.tsv summary,
        fit.tsv per volume, fit_carpet.png), computed once per run of the module. {} if it fails."""
        from dtiplayground.dmri.preprocessing import qc_metrics
        out = Path(self.output_dir)
        paths = [out.joinpath(n) for n in FIT_QC_FILES]
        try:
            if not all(p.exists() for p in paths):
                logger("Tensor fit QC ...", prep.Color.PROCESS)
                ## the volumes of the fit (maxBValue): the shells left out would look poorly fitted
                use, _ = self.fitVolumes()
                gradients = [g for g, u in zip(self.image.getGradients(), use) if u]
                bvals = np.array([g['b_value'] for g in gradients], dtype=float)
                bvecs = np.array([g['unit_gradient'] for g in gradients], dtype=float)
                data = self.image.images[..., use]
                mask = None
                mask_path = self.result['output'].get('global_variables', {}).get('mask_path')
                if mask_path and Path(mask_path).exists():
                    mask = np.squeeze(DWI(mask_path).images) > 0
                if mask is None or mask.shape != data.shape[:3]:
                    from dipy.segment.mask import median_otsu
                    b0 = data[..., bvals <= max(min(bvals), 50)].mean(axis=-1)
                    _, mask = median_otsu(b0, median_radius=2, numpass=1)
                b0_threshold = min(max(min(bvals), 50), 199)
                rows, qc, slice_r2, poor = qc_metrics.tensor_fit(data, bvals, bvecs, mask, b0_threshold=b0_threshold)
                original = [g.get('original_index', i) for i, g in enumerate(gradients)]
                for r in rows:
                    r['original_index'] = original[r['volume']]
                qc_metrics.write_tsv(str(paths[1]), rows, ['volume', 'original_index', 'bval', 'fit_r2', 'fit_corr', 'poor_fit_slices'])
                qc_metrics.carpet_plot(str(paths[2]), slice_r2, poor, bvals, [r['fit_r2'] for r in rows],
                                       title='Tensor fit: R2 per volume and per slice (circles: poorly fitted slices)')
                qc_metrics.write_tsv(str(paths[0]), [qc])
            qc = {k: (int(v) if k == 'poor_fit_slices' else float(v)) for k, v in qc_metrics.read_tsv(str(paths[0]))[0].items() if v != ''}
        except Exception as e:
            logger("Tensor fit QC could not be computed: {}".format(e), prep.Color.WARNING)
            return {}
        for p, postfix in zip(paths, ('DTI_fit_QC', 'DTI_fit', 'DTI_fit_carpet')):
            self.addOutputFile(str(p), postfix)
        return qc


### User defined methods

    def fitVolumes(self, gradients=None):
        """Volumes of the tensor fit (qc_metrics.select_shells with the protocol maxBValue, default 1600), as a
        boolean array, with a description for the log. The limit is passed on to BRAIN_Tractography (global variable
        dti_max_bvalue), so that its tensor fit uses the same shells."""
        from dtiplayground.dmri.preprocessing import qc_metrics
        gradients = self.image.getGradients() if gradients is None else gradients
        limit = self.protocol.get('maxBValue', 1600)
        use, description, warning = qc_metrics.select_shells([g['b_value'] for g in gradients], limit)
        if warning:
            logger(warning, prep.Color.WARNING)
        return use, description

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
        use, description = self.fitVolumes()
        logger("Tensor fit on {}".format(description),prep.Color.INFO)
        self.result['output']['fit_volumes'] = description
        data = self.image.images[..., use]
        affine = self.image.getAffineMatrixForNifti()
        bvals= np.array(list(map(lambda x: x['b_value'], self.image.getGradients())))[use]
        b0=min(bvals)
        bvecs= np.array(list(map(lambda x: x['unit_gradient'], self.image.getGradients())))[use]
        gtab = gradient_table(bvals,bvecs=bvecs,b0_threshold=min(max(b0,50),199))
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
            fitted = dti_fit.fit(data,mask=mask)
            logger("Fitting completed",prep.Color.OK)
        except ValueError as e:
            logger("Mask is not the same shape as data.",prep.Color.ERROR)
            raise ValueError


        ## convert 3x3 symmetric matrices (X,Y,Z,3,3) to xx,xy,xz,yy,yz,zz vectors (X,Y,Z,6), in the frame of the
        ## gradients used for the fit (the measurement frame of the image, written in the header)
        logger("Reducing 3x3 symmetric matrix to vector")
        quad_form = fitted.quadratic_form
        new_quadform = np.stack([quad_form[...,i,j] for i,j in [(0,0),(0,1),(0,2),(1,1),(1,2),(2,2)]], axis=-1)
        new_quadform[np.isnan(new_quadform)] = 0

        temp_dti_image = DWI()
        temp_dti_image.copyFrom(self.image, image=False, gradients=False)
        temp_dti_image.setImage(new_quadform,modality='DTI', kinds=['space','space','space','3D-symmetric-matrix'])
        dti_filename=Path(self.output_dir).joinpath('tensor.nrrd').__str__()
        sp_dir=self.getSourceImageInformation()['space']
        temp_dti_image.setSpaceDirection(target_space=sp_dir)
        write_tensor_nrrd(temp_dti_image, dti_filename)
        self.addOutputFile(dti_filename, 'DTI')
        self.addGlobalVariable('dti_path',dti_filename)
        self.addGlobalVariable('dti_max_bvalue', self.protocol.get('maxBValue', 1600))
        self.writeScalarMaps(fitted.evals, fitted.evecs, affine)
        return None

    def writeScalarMaps(self, evals, evecs, affine):
        """The maps of the tensor (eigenvalues, eigenvectors, FA, colour FA, MD, AD, RD) as tensor_<map>.nii.gz,
        outputs DTI_<MAP>; *evals* (x, y, z, 3) in decreasing order, *evecs* (x, y, z, 3, 3) with the eigenvectors as
        columns, as dipy's TensorFit."""
        evals = np.nan_to_num(np.asarray(evals, dtype=np.float64))
        evecs = np.nan_to_num(np.asarray(evecs, dtype=np.float64))
        fa = np.nan_to_num(dti.fractional_anisotropy(evals))
        scalarData={
            'eigenval': evals,
            'eigenvec': evecs,
            'fa': fa,
            'cfa': dti.color_fa(fa, evecs),
            'md': dti.mean_diffusivity(evals),
            'ad': dti.axial_diffusivity(evals),
            'rd': dti.radial_diffusivity(evals)
        }
        for scalar, val in scalarData.items():
            output_tensor_path = Path(self.output_dir).joinpath('tensor_{}.nii.gz'.format(scalar)).__str__()
            val = np.nan_to_num(np.asarray(val))
            save_nifti(output_tensor_path, val.astype(np.float32), affine)
            self.addOutputFile(output_tensor_path, 'DTI_{}'.format(scalar.upper()))

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
        use, description = self.fitVolumes()
        logger("Tensor fit on {}".format(description),prep.Color.INFO)
        self.result['output']['fit_volumes'] = description
        if not use.all():
            temp_dti_image.deleteGradients([i for i in range(len(use)) if not use[i]])
        dtiestim=tools.DTIEstim(self.software_info['dtiestim']['path'])
        input_image_path = Path(self.output_dir).joinpath('input.nrrd').__str__()
        output_tensor_path = Path(self.output_dir).joinpath('tensor.nrrd').__str__()
        sp_dir=self.getSourceImageInformation()['space']
        temp_dti_image.setSpaceDirection(target_space=sp_dir)
        temp_dti_image.writeImage(str(input_image_path),dest_type='nrrd')
        options = [ '-m',fitMethod,
                    '--correction', correctionMethod]
        ## the brain mask of BRAIN_Mask, as the dipy method uses it: the only mask (-t 0: no additional threshold of
        ## the baseline); without one, dtiestim masks with an Otsu threshold of the baseline
        mask_path = self.global_vars.get('mask_path')
        if mask_path and Path(mask_path).exists():
            options += ['-M', str(mask_path), '-t', '0']
            logger('Mask file found : {} (dtiestim -M, no baseline threshold)'.format(mask_path),prep.Color.OK)
        else:
            logger('No brain mask (BRAIN_Mask): dtiestim masks the image with an Otsu threshold of the baseline',prep.Color.WARNING)

        dtiestim.estimate(input_image_path, output_tensor_path,options)
        ## dtiestim writes the components in the frame of the voxel axes with a header that implies the space of the
        ## image: rotate them into that space (a no-op for axis-aligned images with positive LPS directions)
        from dtiplayground.dmri.fiberprofile.analysis import flip_tensor
        flip_tensor.reorient_tensor_file(output_tensor_path, output_tensor_path, 'voxel')
        logger("Tensor components rotated from the voxel frame into the space of the image",prep.Color.INFO)
        self.addOutputFile(output_tensor_path, 'DTI')
        self.addGlobalVariable('dti_path',output_tensor_path)
        self.addGlobalVariable('dti_max_bvalue', self.protocol.get('maxBValue', 1600))
        ## the maps (FA, MD, AD, RD, eigenvalues, eigenvectors and colour FA, in the space of the image) from the tensor,
        ## as the dipy method writes them
        import nrrd
        from dtiplayground.dmri.fiberprofile.analysis.flip_tensor import tensor_axis
        components, header = nrrd.read(output_tensor_path)
        axis, kind = tensor_axis(components, header)
        components = np.moveaxis(components, axis, -1).astype(np.float64)
        if components.shape[-1] == 7:  # 3D-masked-symmetric-matrix: confidence first
            components = components[..., 1:]
        params = dti.eig_from_lo_tri(components[..., [0, 1, 3, 2, 4, 5]])  # lower triangular: xx, xy, yy, xz, yz, zz
        evals, evecs = params[..., :3], params[..., 3:].reshape(params.shape[:-1] + (3, 3))
        logger("Tensor maps (FA, MD, AD, RD, eigenvalues, eigenvectors, colour FA) computed from the tensor",prep.Color.INFO)
        self.writeScalarMaps(evals, evecs, self.image.getAffineMatrixForNifti())
        return None