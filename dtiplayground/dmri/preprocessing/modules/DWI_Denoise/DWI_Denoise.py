#   Denoising of the DWI with DIPY: Marchenko-Pastur PCA (MP-PCA, Veraart et al. 2016) or Patch2Self (Fadnavis et al.
#   2020). Both assume noise that is independent between voxels: use this module first, on the raw images, before
#   any interpolation (eddy, susceptibility correction, baseline averaging) and before GIBBS_Correct.

import copy
from pathlib import Path

import numpy as np
import yaml

import dtiplayground.dmri.preprocessing as prep
from dtiplayground.dmri.common import measure_time


PATCH2SELF_B0_THRESHOLD = 50 # b-values up to this are the b=0 volumes of Patch2Self (as in QSIPrep)


def auto_patch_radius(n_volumes):
    """Smallest patch radius whose patch has at least as many voxels as there are volumes (MP-PCA needs more
    samples than volumes to separate the noise eigenvalues)."""
    r = 1
    while (2 * r + 1) ** 3 < n_volumes:
        r += 1
    return r


class DWI_Denoise(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)
        global logger
        logger = self.logger.write

    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        return self.protocol

    def process(self,*args,**kwargs):
        super().process()
        opts=args[0]
        self.baseline_threshold=opts['baseline_threshold']
        method=self.protocol.get('method','mppca')
        output_dir=Path(self.output_dir)

        data=self.image.images
        gradients=self.image.getGradients()
        bvals=np.array([g['b_value'] for g in gradients],dtype=float)
        b0_threshold=max(bvals.min(),self.baseline_threshold)
        sigma=None
        if method=='mppca':
            radius=self.protocol.get('patchRadius',0) or auto_patch_radius(data.shape[-1])
            logger("MP-PCA denoising, patch radius {} ({} voxels, {} volumes) ...".format(radius,(2*radius+1)**3,data.shape[-1]),prep.Color.PROCESS)
            denoised,sigma=self.mppca(data,radius)
        elif method=='patch2self':
            model=self.protocol.get('patch2selfModel','ols')
            logger("Patch2Self denoising ({} regression) ...".format(model),prep.Color.PROCESS)
            denoised=self.patch2self(data,bvals,model,PATCH2SELF_B0_THRESHOLD)
        else:
            raise Exception("Unknown denoising method : {}".format(method))
        denoised=denoised.astype(np.float64)
        logger("Denoising completed",prep.Color.OK)

        qc=self.writeQC(data,denoised,sigma,bvals,b0_threshold,method)

        ## output image: a copy, the input image object belongs to the previous module
        image=copy.copy(self.image)
        image.information=copy.deepcopy(self.image.information)
        image.gradients=copy.deepcopy(self.image.gradients)
        image.images=denoised
        self.image=image
        ext='.nrrd' if self.image.image_type.lower()=='nrrd' else '.nii.gz'
        self.writeImageWithOriginalSpace(str(output_dir.joinpath('output'+ext)),dest_type=self.image.image_type,dtype='float32')

        self.result['output']['excluded_gradients_original_indexes']=[]
        self.result['output']['success']=True
        return self.result

    @measure_time
    def mppca(self,data,radius):
        from dipy.denoise.localpca import mppca
        return mppca(data,patch_radius=int(radius),return_sigma=True,suppress_warning=True)

    @measure_time
    def patch2self(self,data,bvals,model,b0_threshold):
        from dipy.denoise.patch2self import patch2self
        return patch2self(data,bvals,model=model,b0_threshold=b0_threshold,b0_denoising=True,
                          clip_negative_vals=False,shift_intensity=True)

    def writeQC(self,data,denoised,sigma,bvals,b0_threshold,method):
        """noise_sigma.nii.gz (MP-PCA) or noise_residual.nii.gz (Patch2Self: RMS over the volumes of the removed signal,
        as QSIPrep), denoise_qc.tsv (noise level in the brain) and denoise.png (before/after)."""
        from dtiplayground.dmri.preprocessing import qc_metrics
        from dipy.io.image import save_nifti
        output_dir=Path(self.output_dir)
        mask=qc_metrics.brain_mask(data,bvals,b0_threshold)
        b0=bvals<=b0_threshold
        residual=data-denoised
        qc={'denoise_method':method,
            ## standard deviation of what was removed, in the brain (b=0 and diffusion weighted volumes)
            'removed_std_b0':qc_metrics._round(residual[mask][:,b0].std(),3) if b0.any() else None,
            'removed_std_dwi':qc_metrics._round(residual[mask][:,~b0].std(),3) if (~b0).any() else None}
        affine=self.image.getAffineMatrixForNifti()
        if sigma is None:
            residual_rms=np.sqrt(np.mean(residual**2,axis=-1))
            residual_path=str(output_dir.joinpath('noise_residual.nii.gz'))
            save_nifti(residual_path,residual_rms.astype(np.float32),affine)
            self.addOutputFile(residual_path,'DWI_noise_residual')
            qc['noise_residual_rms']=qc_metrics._round(np.median(residual_rms[mask]),3)
        else:
            sigma_path=str(output_dir.joinpath('noise_sigma.nii.gz'))
            save_nifti(sigma_path,sigma.astype(np.float32),affine)
            self.addOutputFile(sigma_path,'DWI_noise_sigma')
            qc['noise_sigma']=qc_metrics._round(np.median(sigma[mask]),3)
            if b0.any():
                with np.errstate(invalid='ignore',divide='ignore'):
                    snr=data[...,b0].mean(axis=-1)[mask]/sigma[mask]
                qc['snr_b0_mppca']=qc_metrics._round(np.nanmedian(snr[np.isfinite(snr)]),2)
        qc_path=qc_metrics.write_tsv(str(output_dir.joinpath('denoise_qc.tsv')),[qc])
        self.addOutputFile(qc_path,'DENOISE_QC')
        try:
            qc_metrics.before_after_plot(str(output_dir.joinpath('denoise.png')),data,denoised,bvals,
                                         labels=('input','denoised','removed (denoised - input)'),
                                         title='Denoising ({})'.format(method))
        except Exception as e:
            logger("Denoising figure could not be made: {}".format(e),prep.Color.WARNING)
        return qc

    def makeReport(self):
        super().makeReport()
        from dtiplayground.dmri.preprocessing import qc_metrics
        output_dir=Path(self.output_dir)
        qc_path=output_dir.joinpath('denoise_qc.tsv')
        if not qc_path.exists():
            return
        qc={k:v for k,v in qc_metrics.read_tsv(str(qc_path))[0].items() if v!=''}
        for k in list(qc):
            if k!='denoise_method':
                qc[k]=float(qc[k])
        with open(str(output_dir.joinpath('report.md')),'a') as f:
            f.write('* Method: {}\n'.format(qc.get('denoise_method')))
            if 'noise_sigma' in qc:
                f.write('* Noise level (MP-PCA sigma, median in the brain): {}; b=0 SNR: {}\n'.format(qc['noise_sigma'],qc.get('snr_b0_mppca')))
            if 'noise_residual_rms' in qc:
                f.write('* Removed signal (RMS over the volumes, median in the brain): {}\n'.format(qc['noise_residual_rms']))
            f.write('* Standard deviation of the removed signal in the brain: b=0 {}, diffusion weighted {}\n\n'.format(qc.get('removed_std_b0'),qc.get('removed_std_dwi')))
            if output_dir.joinpath('denoise.png').exists():
                f.write("<img src='{}' width='560'>\n\n".format(output_dir.joinpath('denoise.png')))
        self.result['report']['csv_data']['denoise_qc']={k:v for k,v in qc.items() if k!='denoise_method'}
        with open(str(output_dir.joinpath('result.yml')),'w') as f:
            yaml.dump(self.result,f)
