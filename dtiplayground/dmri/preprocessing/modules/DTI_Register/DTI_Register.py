  
import dtiplayground.dmri.preprocessing as prep
import yaml, os
from pathlib import Path

import dtiplayground.dmri.common.tools as tools 

class DTI_Register(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)
        global logger
        logger = self.logger.write

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
        transformationStep = self.protocol.get('ANTsTransformationStep', 0.25)
        useHistogramMatching = self.protocol.get('ANTsUseHistogramMatching', True)
        scalarMeasurement = self.protocol.get('scalarMeasurement', 'FA')
        tensorCorrection = self.protocol.get('tensorCorrection', 'abs')
        
        ## saving input
        if self.dtiImagePath is not None:
            inputImagePath = self.dtiImagePath
        else:
            self.writeImageWithOriginalSpace(inputImagePath,'nrrd',dtype='float')

        os.environ['ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS'] = str(nbThreads)
        ANTsPath=Path(protocol['ANTsPath']).joinpath('ANTS').__str__()
        WarpImageMultiTransformPath=Path(protocol['ANTsPath']).joinpath('WarpImageMultiTransform').__str__()
        initialAffinePath = self.initialAffine(refImagePath, inputImagePath, scalarMeasurement, tensorCorrection, nbThreads)
        logger("Executing DTI Reg for registration",prep.Color.PROCESS)
        args = ['--fixedVolume',refImagePath,
                '--movingVolume',inputImagePath,
                '--method',ANTsMethod,
                '--scalarMeasurement',scalarMeasurement,
                '--correction',tensorCorrection,
                '--ANTSRegistrationType',registrationType,
                '--ANTSSimilarityMetric',similarityMetric,
                '--ANTSSimilarityParameter',str(similarityParameter),
                '--ANTSGaussianSigma',str(gaussianSigma),
                '--ANTSTransformationStep',str(transformationStep),
                '--ANTSIterations',ANTSIterations,
                '--outputDisplacementField',displacementFieldPath,
                '--outputInverseDeformationFieldVolume', inv_displacementFieldPath,
                '--ANTSPath',ANTsPath,
                '--WarpImageMultiTransformPath',WarpImageMultiTransformPath,
                '--dtiprocessPath',self.softwares['dtiprocess']['path'],
                '--ResampleDTIPath',self.softwares['ResampleDTIlogEuclidean']['path'],
                '--ITKTransformToolsPath',self.softwares['ITKTransformTools']['path'],
                '--numberOfThreads',str(nbThreads),
                '--outputVolume', registeredImagePath]
                # '--outputFolder',outputDirectory]
        if useHistogramMatching:
            args += ['--ANTSUseHistogramMatching']
        if initialAffinePath is not None:
            args += ['--initialAffine', initialAffinePath]
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

    def initialAffine(self, refImagePath, inputImagePath, scalarMeasurement, tensorCorrection, nbThreads):
        """Initial affine transform (fixed = reference, moving = DTI) given by the protocol: computed with BRAINSFit from
        the scalar images of the tensors, read from initialAffineFile, or None."""
        mode = self.protocol.get('initialAffine', 'BRAINSFit')
        if mode == 'none':
            return None
        if mode == 'file':
            path = self.protocol.get('initialAffineFile')
            if path is None or not Path(path).exists():
                logger("Initial affine file doesn't exist: {}".format(path),prep.Color.ERROR)
                raise Exception("File not found")
            self.addGlobalVariable('initial_affine_path', str(path))
            return str(path)
        if mode != 'BRAINSFit':
            raise Exception("Unknown initialAffine: {} (BRAINSFit, file or none)".format(mode))

        output_dir = Path(self.output_dir)
        scalar_option = {'FA': '-f', 'MD': '-m'}[scalarMeasurement]
        dtiprocess = tools.DTIProcess(self.softwares['dtiprocess']['path'])
        dtiprocess.dev_mode = True
        scalar_paths = []
        for name, dti in [('reference', refImagePath), ('input', inputImagePath)]:
            scalar_path = output_dir.joinpath('{}_{}.nrrd'.format(name, scalarMeasurement)).__str__()
            logger("Computing {} of the {} DTI for the initial affine registration".format(scalarMeasurement, name),prep.Color.PROCESS)
            dtiprocess.execute(['--dti_image', dti, scalar_option, scalar_path, '--correction', tensorCorrection])
            scalar_paths.append(scalar_path)

        affinePath = output_dir.joinpath('initialAffine.txt').__str__()
        transforms = ','.join(t.strip() for t in str(self.protocol.get('BRAINSFitTransforms', 'Rigid,Affine')).split(',') if t.strip() != '')
        args = ['--fixedVolume', scalar_paths[0],
                '--movingVolume', scalar_paths[1],
                '--transformType', transforms,
                '--initializeTransformMode', str(self.protocol.get('BRAINSFitInitializeTransformMode', 'useCenterOfHeadAlign')),
                '--samplingPercentage', str(self.protocol.get('BRAINSFitSamplingPercentage', 0.5)),
                '--outputTransform', affinePath,
                '--outputVolume', output_dir.joinpath('initialAffine_{}.nrrd'.format(scalarMeasurement)).__str__(),
                '--numberOfThreads', str(nbThreads)]
        logger("Executing BRAINSFit for the initial affine registration ({})".format(transforms),prep.Color.PROCESS)
        brainsfit = tools.BRAINSFit(self.softwares['BRAINSFit']['path'])
        brainsfit.dev_mode = True
        brainsfit.execute(args)
        self.result['output']['initial_affine_path'] = affinePath
        self.addGlobalVariable('initial_affine_path', affinePath)
        self.addOutputFile(affinePath, 'DTI_InitialAffine')
        return affinePath
