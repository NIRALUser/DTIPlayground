

  
import dtiplayground.dmri.preprocessing as prep

import yaml
from pathlib import Path 

import dtiplayground.dmri.common.tools as tools 
from dtiplayground.dmri.common import measure_time
import shutil
import os 
import markdown
import pandas 

### utilities

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

class EDDYMOTION_Correct(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)
        global logger
        logger = self.logger.write

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
                return False, "Exception in finding FSL6 : {}".format(str(fslpath))
        else:
            return False, "Can't locate FSL" #test

    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    def process(self,*args,**kwargs): ## variables : self.global_variables, self.softwares, self.output_dir, self.config_dir, self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        gradient_indexes_to_remove=[]
        protocol_options=args[0]
        self.num_threads=protocol_options['software_info']['parameters']['num_max_threads']
        self.software_info=protocol_options['software_info']['softwares']
        susceptibility=False
        susceptibility_parameters=None
        self.qcReport = self.protocol['qcReport']
        if 'susceptibility_parameters' in inputParams:
            susceptibility=True
            susceptibility_parameters=inputParams['susceptibility_parameters']
        res=None
        if susceptibility:
            res=self.eddy(self.image,
                          outfilename=None,
                          params=susceptibility_parameters,
                          protocols=self.protocol)
        else:
            res=self.eddy(self.image,
                          outfilename=None,
                          params=None,
                          protocols=self.protocol)

        ## results
        self.result['output']['excluded_gradients_original_indexes']=self.image.convertToOriginalGradientIndex(gradient_indexes_to_remove)
        self.result['output']['success']=True
        return self.result

    def makeReport(self):
        super().makeReport()    
        path_qc_pdf = os.path.abspath(self.output_dir) + "/output_eddied.qc/qc.pdf"  
        if os.path.exists(path_qc_pdf):
            self.result['report']['path_qc_pdf']=path_qc_pdf   

        with open(os.path.abspath(self.output_dir) + '/report.md', 'a') as f:
            path_rms = self.output_dir + "/output_eddied.eddy_movement_rms"
            data_rms = pandas.read_csv(path_rms, sep = '  ', engine = 'python', usecols = [1])
            rmsLargerThan1 = data_rms[data_rms > 1.0].count()[0]
            rmsLargerThan2 = data_rms[data_rms > 2.0].count()[0]
            rmsLargerThan3 = data_rms[data_rms > 3.0].count()[0]
            ## second column of eddy_movement_rms: RMS movement relative to the previous volume
            f.write('* ' + str(rmsLargerThan1) + " gradients with RMS movement relative to the previous volume > 1 mm\n")
            f.write('* ' + str(rmsLargerThan2) + " gradients with RMS movement relative to the previous volume > 2 mm\n")
            f.write('* ' + str(rmsLargerThan3) + " gradients with RMS movement relative to the previous volume > 3 mm\n")
            qc = self.motionQC()
            if qc:
                f.write('* Framewise displacement: mean {} mm, max {} mm\n'.format(qc.get('mean_fd'), qc.get('max_fd')))
                f.write('* Maximum translation {} mm, rotation {} deg (relative to the first volume)\n'.format(qc.get('max_translation'), qc.get('max_rotation')))
                if 'outlier_slices' in qc:
                    f.write('* {} outlier slices replaced by eddy ({}% of the slices)\n'.format(qc['outlier_slices'], qc['outlier_slices_percent']))
                cnr = ['{} {}'.format(k.replace('_', ' '), v) for k, v in qc.items() if k.startswith(('snr_', 'cnr_'))]
                if cnr:
                    f.write('* Mean in the mask: ' + ', '.join(cnr) + '\n')
            f.seek(0)

        self.result['report']['csv_data']['rms_gt_1'] = int(rmsLargerThan1)
        self.result['report']['csv_data']['rms_gt_2'] = int(rmsLargerThan2)
        self.result['report']['csv_data']['rms_gt_3'] = int(rmsLargerThan3)
        self.result['report']['csv_data']['eddy_qc'] = qc
        with open(str(Path(self.output_dir).joinpath('result.yml')),'w') as f:
            yaml.dump(self.result,f)

    def motionQC(self):
        """Motion (per volume: EDDY_motion.tsv) and SNR/CNR summary (EDDY_QC.tsv) of the eddy outputs, {} without them."""
        from dtiplayground.dmri.preprocessing import qc_metrics
        output_dir = Path(self.output_dir)
        eddy_base = output_dir.joinpath('output_eddied')
        args = qc_metrics.eddy_arguments(eddy_base)
        bval_path = Path(args.get('bvals', str(output_dir.joinpath('output_eddied.bval'))))
        try:
            bvals = [float(b) for b in bval_path.read_text().split()]
            gradients = self.image.getGradients() if self.image is not None else []
            original = [g.get('original_index', i) for i, g in enumerate(gradients)]
            rows, qc = qc_metrics.eddy_motion(eddy_base, bvals, original if len(original) == len(bvals) else None)
            if rows is None:
                return {}
            b_range = self.protocol.get('bRange') or 50
            qc.update(qc_metrics.eddy_cnr(eddy_base, bvals, args.get('mask'), b0_threshold=100, b_range=b_range))
        except Exception as e:
            logger("Motion QC metrics could not be computed: {}".format(e), prep.Color.WARNING)
            return {}
        motion_path = qc_metrics.write_tsv(str(output_dir.joinpath('motion.tsv')), rows)
        qc_path = qc_metrics.write_tsv(str(output_dir.joinpath('eddy_qc.tsv')), [qc])
        self.addOutputFile(motion_path, 'EDDY_motion')
        self.addOutputFile(qc_path, 'EDDY_QC')
        return qc
        

### User defined methods
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

        b0idx=0
        res_index=[]
        for i,g in enumerate(grads):
            if b0idx+1 < len(bidx):
                if i>=bidx[b0idx+1]:
                    b0idx+=1 
            res_index.append(b0idx+1)
        res_str=" ".join(list(map(str,res_index)))
        open(index_filename,'w').write(res_str)
        return index_filename

    ### scripts

    @measure_time
    def eddy(self,image,outfilename,params, protocols): ## eddy with topup (susceptibility correction process is required before execution)

        output_dir=Path(self.output_dir)
        input_nifti=output_dir.joinpath('input.nii.gz').__str__()
        input_bvals=output_dir.joinpath('input.bval').__str__()
        input_bvecs=output_dir.joinpath('input.bvec').__str__()
        output_nifti=output_dir.joinpath('output.nii.gz').__str__()
        binary_mask=output_dir.joinpath('output_mask.nii.gz').__str__()
        ### conversion to nifti 
        if params is not None: ## if susceptibility parameters present
            input_nifti=params['image_path']
            input_bvals=params['image_bvals_path']
            input_bvecs=params['image_bvecs_path']
            binary_mask=params['mask_path']
        processed_nifti=output_dir.joinpath('output_eddied.nii.gz').__str__()
        processed_nifti_base=Path(processed_nifti).parent.joinpath(Path(processed_nifti).name.split('.')[0]).__str__()
        processed_nifti_nonneg=output_dir.joinpath('output_eddied_nonneg.nii.gz').__str__()
        processed_bvals=output_dir.joinpath('output_eddied.bval').__str__()
        processed_bvecs=output_dir.joinpath('output_eddied.bvec').__str__()
        output_nrrd=output_dir.joinpath('output.nrrd').__str__()
        quad_output_dir=output_dir.joinpath('output_eddied.qc').__str__()

        ### generate mask
        fsl=tools.FSL(self.software_info['FSL']['path'])
        fsl._set_num_threads(self.num_threads)
        fsl.setDevMode(True)

        ### acqp file writing
        acqp_filename=None
        index_filename=None
        topup_filename=None
        _average_path=output_dir.joinpath("_average.nii.gz").__str__()
        img=None
        if params is not None: ##susceptibility case
            acqp_filename=params['acqp_path']
            index_filename=self.make_index_new(self.image,params['index_path'])
            topup_filename=params['topup_path']
        else: # single eddy
            self.writeImageWithOriginalSpace(str(input_nifti),dest_type='nifti')
            img=self.loadImage(input_nifti)
            logger("Generating Mask : {}".format(binary_mask.__str__()))
            output=fsl.fslmaths_ops(input_nifti,_average_path,'mean')
            res=fsl.bet(str(input_nifti),str(output_nifti))
            ouput_nifti=Path(output_nifti).rename(output_dir.joinpath('temp.nii.gz').__str__())
            acqp_filename=self.make_acqp() 
            index_filename=self.make_index(self.image)
        ### eddy correction
        if not Path(processed_nifti).exists():
            if params is not None:
                logger("Computing eddy with susceptibility correction... ",prep.Color.PROCESS)
                res=fsl.eddy_openmp(imain=input_nifti,
                                mask=binary_mask,
                                acqp=acqp_filename,
                                index_file=index_filename,
                                bvals=input_bvals,
                                bvecs=input_bvecs,
                                out=processed_nifti_base, #basename
                                estimate_move_by_susceptibility=protocols['estimateMoveBySusceptibility'],
                                topup=topup_filename,
                                data_is_shelled=protocols['dataIsShelled'],
                                repol=protocols['interpolateBadData'],
                                b_range=protocols.get('bRange'))
            else:
                logger("Computing eddy ... ",prep.Color.PROCESS)
                res=fsl.eddy_openmp(imain=input_nifti,
                                mask=binary_mask,
                                acqp=acqp_filename,
                                index_file=index_filename,
                                bvals=input_bvals,
                                bvecs=input_bvecs,
                                out=processed_nifti_base,
                                estimate_move_by_susceptibility=False,
                                topup=None,
                                data_is_shelled=protocols['dataIsShelled'],
                                repol=protocols['interpolateBadData'],
                                b_range=protocols.get('bRange'))
        else:
            logger("Eddymotion corrected output exists: {}".format(processed_nifti),prep.Color.OK)
            self.image=self.loadImage(processed_nifti)
        shutil.copy(processed_nifti_base+".eddy_rotated_bvecs",processed_bvecs)
        shutil.copy(input_bvals,processed_bvals)

        img=self.loadImage(processed_nifti)
        if not Path(output_dir.joinpath("output_eddied_dev.nrrd")).exists():
            img.writeImage(Path(output_dir.joinpath("output_eddied_dev.nrrd")).__str__(),dest_type='nrrd')

        logger("Generating Non negative DWI...",prep.Color.PROCESS)
        nonneg_base=Path(processed_nifti_nonneg).name.split('.')[0]
        processed_nifti_nonneg_bvals=Path(processed_nifti_nonneg).parent.joinpath(nonneg_base+".bval").__str__()
        processed_nifti_nonneg_bvecs=Path(processed_nifti_nonneg).parent.joinpath(nonneg_base+".bvec").__str__()

        if not Path(processed_nifti_nonneg).exists():
            output=fsl.fslmaths_threshold(processed_nifti,processed_nifti_nonneg,0)
            shutil.copy(processed_bvals,processed_nifti_nonneg_bvals)
            shutil.copy(processed_bvecs,processed_nifti_nonneg_bvecs)

        img=self.loadImage(processed_nifti_nonneg)
        if not Path(output_dir.joinpath("output_eddied_nonneg_dev.nrrd")).exists():
            img.writeImage(Path(output_dir.joinpath("output_eddied_nonneg_dev.nrrd")).__str__(),dest_type='nrrd')

        if not Path(quad_output_dir).exists() and protocols['qcReport']:
            logger("Executing eddy_quad for quality assessment...",prep.Color.PROCESS)
            output=fsl.eddy_quad(
                        input_base=processed_nifti_base,
                        idx=index_filename,
                        par=acqp_filename,
                        mask=binary_mask,
                        bvals=processed_bvals)

        self.image=self.loadImage(processed_nifti_nonneg)
        self.image.image_type='nrrd'
        self.writeImageWithOriginalSpace(output_nrrd,'nrrd')
        return None

