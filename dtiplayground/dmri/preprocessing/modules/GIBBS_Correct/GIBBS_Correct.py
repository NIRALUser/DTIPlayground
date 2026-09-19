#   Gibbs ringing removal with DIPY (local subvoxel shifts, Kellner et al. 2016; the method of MRtrix mrdegibbs), slice by
#   slice in the plane of acquisition. Meant for full Fourier acquisitions; with partial Fourier it removes only part
#   of the ringing. Use it after DWI_Denoise and before any interpolation (eddy, susceptibility correction).

import copy
from pathlib import Path

import numpy as np
import yaml

import dtiplayground.dmri.preprocessing as prep
from dtiplayground.dmri.common import measure_time


class GIBBS_Correct(prep.modules.DTIPrepModule):
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
        num_threads=int(opts['software_info']['parameters'].get('num_max_threads',1) or 1)
        slice_axis=int(self.protocol.get('sliceAxis',2))
        n_points=int(self.protocol.get('nPoints',3))
        output_dir=Path(self.output_dir)

        data=self.image.images
        bvals=np.array([g['b_value'] for g in self.image.getGradients()],dtype=float)
        logger("Gibbs ringing removal, slice axis {}, {} points, {} processes ...".format(slice_axis,n_points,num_threads),prep.Color.PROCESS)
        corrected=self.gibbs(data,slice_axis,n_points,num_threads)
        logger("Gibbs ringing removal completed",prep.Color.OK)

        self.writeQC(data,corrected,bvals,slice_axis)

        ## output image: a copy, the input image object belongs to the previous module
        image=copy.copy(self.image)
        image.information=copy.deepcopy(self.image.information)
        image.gradients=copy.deepcopy(self.image.gradients)
        image.images=corrected
        self.image=image
        ext='.nrrd' if self.image.image_type.lower()=='nrrd' else '.nii.gz'
        self.writeImageWithOriginalSpace(str(output_dir.joinpath('output'+ext)),dest_type=self.image.image_type,dtype='float32')

        self.result['output']['excluded_gradients_original_indexes']=[]
        self.result['output']['success']=True
        return self.result

    @measure_time
    def gibbs(self,data,slice_axis,n_points,num_threads):
        from dipy.denoise.gibbs import gibbs_removal
        return np.asarray(gibbs_removal(data.astype(np.float64),slice_axis=slice_axis,n_points=n_points,inplace=False,
                                        num_processes=num_threads),dtype=np.float64)

    def writeQC(self,data,corrected,bvals,slice_axis):
        """gibbs_qc.tsv (size of the correction in the brain) and gibbs.png (before/after)."""
        from dtiplayground.dmri.preprocessing import qc_metrics
        output_dir=Path(self.output_dir)
        b0_threshold=max(bvals.min(),self.baseline_threshold)
        mask=qc_metrics.brain_mask(data,bvals,b0_threshold)
        change=np.abs(corrected-data)[mask]
        qc={'gibbs_mean_abs_change_percent':qc_metrics._round(100.0*change.mean()/max(np.abs(data[mask]).mean(),1e-12),3)}
        qc_path=qc_metrics.write_tsv(str(output_dir.joinpath('gibbs_qc.tsv')),[qc])
        self.addOutputFile(qc_path,'GIBBS_QC')
        try:
            qc_metrics.before_after_plot(str(output_dir.joinpath('gibbs.png')),data,corrected,bvals,
                                         labels=('input','corrected','removed (corrected - input)'),
                                         title='Gibbs ringing removal',slice_axis=slice_axis)
        except Exception as e:
            logger("Gibbs figure could not be made: {}".format(e),prep.Color.WARNING)
        return qc

    def makeReport(self):
        super().makeReport()
        from dtiplayground.dmri.preprocessing import qc_metrics
        output_dir=Path(self.output_dir)
        qc_path=output_dir.joinpath('gibbs_qc.tsv')
        if not qc_path.exists():
            return
        qc={k:float(v) for k,v in qc_metrics.read_tsv(str(qc_path))[0].items() if v!=''}
        with open(str(output_dir.joinpath('report.md')),'a') as f:
            f.write('* Mean absolute change in the brain: {}% of the mean intensity\n\n'.format(qc.get('gibbs_mean_abs_change_percent')))
            if output_dir.joinpath('gibbs.png').exists():
                f.write("<img src='{}' width='560'>\n\n".format(output_dir.joinpath('gibbs.png')))
        self.result['report']['csv_data']['gibbs_qc']=qc
        with open(str(output_dir.joinpath('result.yml')),'w') as f:
            yaml.dump(self.result,f)
