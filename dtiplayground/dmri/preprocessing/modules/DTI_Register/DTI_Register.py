  
import dtiplayground.dmri.preprocessing as prep
import yaml, os
from pathlib import Path
logger=prep.logger.write

import dtiplayground.dmri.common.tools as tools 

class DTI_Register(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)
        
    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        self.protocol['ANTsPath'] = self.protocol['ANTsPath'].replace('$ANTSDIR', self.softwares['ANTs']['path'])
        ## todos
        if 'reference_dti' in self.global_variables:
            ref_dti_path = Path(self.global_variables['reference_dti'])
            self.protocol['referenceImage'] = ref_dti_path.resolve().__str__()
        return self.protocol
        
    @prep.measure_time
    def process(self,*args,**kwargs): ## variables : self.global_variables, self.softwares, self.output_dir, self.config_dir, self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        protocol_options=args[0]
        self.num_threads=protocol_options['software_info']['parameters']['num_max_threads']
        self.baseline_threshold=protocol_options['baseline_threshold']

        # << TODOS>>
        self.dtiImagePath = None
        if 'dti_path' in self.global_variables:
            self.dtiImagePath=self.global_variables['dti_path']
        self.register(**self.protocol)

        logger(yaml.dump(self.image.information))
        self.result['output']['success']=True

        return self.result

    def register(self,**protocol):
        if protocol['method'] == 'ANTs':
            logger("ANTS is selected for the method",prep.Color.INFO)
            self.registerWithANTs(**protocol)
        else:
            logger("No method was selected, skipping the registration",prep.Color.WARNING)
        return True

    def registerWithANTs(self,**protocol):
        output_dir = Path(self.output_dir)
        refImagePath = self.protocol['referenceImage']
        if not Path(refImagePath).exists():
            logger("Reference image doesn't exist. Please check the file {} exists.".format(refImagePath),prep.Color.ERROR)
            raise Exception("File not found")
        inputImagePath = output_dir.joinpath('input.nrrd').__str__()
        registeredImagePath = output_dir.joinpath('registered_dti.nrrd').__str__()
        # outputImagePath = output_dir.joinpath('output.nrrd').__str__()
        displacementFieldPath = output_dir.joinpath('displacementField.nrrd').__str__()
        inv_displacementFieldPath = output_dir.joinpath('inverse_displacementField.nrrd').__str__()
        outputDirectory = output_dir.__str__()
        nbThreads = self.num_threads

        ANTsMethod = self.protocol['ANTsMethod']
        registrationType = self.protocol['registrationType']
        similarityMetric = self.protocol['similarityMetric']
        similarityParameter = self.protocol['similarityParameter']
        ANTSIterations = self.protocol['ANTsIterations']
        gaussianSigma = self.protocol['gaussianSigma']
        
        ## saving input
        if self.dtiImagePath is not None:
            inputImagePath = self.dtiImagePath
        else:
            self.writeImageWithOriginalSpace(inputImagePath,'nrrd',dtype='float')

        os.environ['ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS'] = str(nbThreads)
        ANTsPath=Path(protocol['ANTsPath']).joinpath('ANTS').__str__()
        logger("Executing DTI Reg for registration",prep.Color.PROCESS)
        args = ['--fixedVolume',refImagePath,
                '--movingVolume',inputImagePath,
                '--method',ANTsMethod,
                '--ANTSRegistrationType',registrationType,
                '--ANTSSimilarityMetric',similarityMetric,
                '--ANTSSimilarityParameter',str(similarityParameter),
                '--ANTSGaussianSigma',str(gaussianSigma),
                '--ANTSIterations',ANTSIterations,
                '--outputDisplacementField',displacementFieldPath,
                '--outputInverseDeformationFieldVolume', inv_displacementFieldPath,
                '--ANTSPath',ANTsPath,
                '--dtiprocessPath',self.softwares['dtiprocess']['path'],
                '--ResampleDTIPath',self.softwares['ResampleDTIlogEuclidean']['path'],
                '--ITKTransformToolsPath',self.softwares['ITKTransformTools']['path'],
                '--outputVolume', registeredImagePath]
                # '--outputFolder',outputDirectory]
        dtireg=tools.DTIReg(self.softwares['DTI-Reg']['path'])
        dtireg.dev_mode=True
        dtireg.execute_with_args(args)
        self.result['output']['displacement_field_path'] = displacementFieldPath
        self.result['output']['inverse_displacement_field_path'] = inv_displacementFieldPath
        self.result['output']['registered_dti_image'] = registeredImagePath
        self.addGlobalVariable('displacement_field_path',displacementFieldPath)
        self.addGlobalVariable('inverse_displacement_field_path',inv_displacementFieldPath)
        self.addGlobalVariable('registered_dti_path',registeredImagePath)
        self.addGlobalVariable('reference_dti_path',refImagePath)
        self.addGlobalVariable('dti_path',inputImagePath) #update dti_path with registered image

        # if self.protocol['useRegistered']:
        #    self.loadImage(registeredImagePath) 
        self.addOutputFile(registeredImagePath, 'DTI_Registered')
        self.addOutputFile(displacementFieldPath, 'DTI_DisplacementField')
        self.addOutputFile(inv_displacementFieldPath, 'DTI_Inverse_DisplacementField')

        #self.writeImageWithOriginalSpace(outputImagePath,'nrrd',dtype='float')
        return True 