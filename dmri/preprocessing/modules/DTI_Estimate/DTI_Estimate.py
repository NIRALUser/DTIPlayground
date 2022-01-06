  
import dmri.preprocessing as prep
from dmri.common import measure_time
import dmri.common.tools as tools 
import yaml
from pathlib import Path

import numpy as np
import dipy.reconst.dti as dti
from dipy.core.gradients import gradient_table
import dipy.denoise.noise_estimate as ne
from dipy.io.image import save_nifti

logger=prep.logger.write


class DTI_Estimate(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir)
        
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
        bvecs= np.array(list(map(lambda x: x['unit_gradient'], self.image.getGradients())))
        gtab = gradient_table(bvals,bvecs)
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

        
        # fitting and estimation of scalars

        dti_fit = dti.TensorModel(gtab,fit_method=fitMethod,**kwargs)
        logger("Running with {}, {}".format(fitMethod, kwargs),prep.Color.PROCESS)
        fitted = dti_fit.fit(data)
        logger("Fitting completed",prep.Color.OK)

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
        fitMethod="lls"
        try:
            fitMethod=optionmap[optimizationMethod]
        except:
            fitMethod="lls"
            logger("WARNING: The method {} is not available with the method. Changing it to {}.".format(optimizationMethod,fitMethod), prep.Color.WARNING)


        dtiestim=tools.DTIEstim(self.software_info['dtiestim']['path'])
        input_image_path = Path(self.output_dir).joinpath('input.nrrd').__str__()
        output_tensor_path = Path(self.output_dir).joinpath('tensor.nrrd').__str__()
        self.writeImage(str(input_image_path),dest_type='nrrd')

        options = [ '-m',fitMethod,
                    '--correction', correctionMethod]

        dtiestim.estimate(input_image_path, output_tensor_path,options)
        self.addOutputFile(output_tensor_path, 'DTI')
        return None