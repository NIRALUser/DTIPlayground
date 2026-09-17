  
import dtiplayground.dmri.preprocessing as prep
import yaml, os, re
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
        refImagePath = self.referenceImage()
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
        if self.protocol.get('registerMetrics', True) and self.dtiImagePath is not None:
            self.registerMetrics(inputImagePath, refImagePath, displacementFieldPath, tensorCorrection, nbThreads)
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

    def registerMetrics(self, inputImagePath, refImagePath, displacementFieldPath, tensorCorrection, nbThreads):
        """Apply the displacement field to the diffusion metrics in the folder of the input DTI that share its file name
        prefix (e.g. <scan>_dwi_QCed_ of <scan>_dwi_QCed_tensor.nrrd): tensor images are resampled log-Euclidean with
        reorientation like the DTI, scalar images with linear interpolation. Written as registered_<name>."""
        import SimpleITK as sitk
        import nrrd
        output_dir = Path(self.output_dir)
        source = Path(inputImagePath)
        prefix = source.name[:-len('tensor.nrrd')] if source.name.endswith('tensor.nrrd') else source.name.split('.')[0] + '_'
        exclude = [x.strip().lower() for x in str(self.protocol.get('metricExclude', 'mask') or '').split(',') if x.strip() != '']
        candidates = sorted(f for f in source.parent.iterdir()
                            if f.is_file() and f.name.startswith(prefix) and f != source and f.name.endswith(('.nrrd', '.nii.gz', '.nii')))
        field = None
        registered = {}
        for f in candidates:
            name = f.name[len(prefix):]
            if any(x in name.lower() for x in exclude):
                logger("Not registering {} (excluded: {})".format(f.name, ', '.join(exclude)),prep.Color.INFO)
                continue
            is_tensor = False
            if f.name.endswith('.nrrd'):
                header = nrrd.read_header(str(f))
                is_tensor = any(str(k).endswith('symmetric-matrix') for k in header.get('kinds', [])) or \
                    (header.get('dimension') == 4 and 6 in [int(x) for x in header.get('sizes', [])])
            output = output_dir.joinpath('registered_' + name).__str__()
            if not is_tensor:
                reader = sitk.ImageFileReader()
                reader.SetFileName(str(f))
                try:
                    reader.ReadImageInformation()
                except RuntimeError as e:
                    logger("Not registering {} (unreadable: {})".format(f.name, str(e).splitlines()[-1]),prep.Color.WARNING)
                    continue
                components = reader.GetNumberOfComponents()
                dimension = reader.GetDimension()
            if is_tensor:
                logger("Registering tensor image {}".format(f.name),prep.Color.PROCESS)
                resample = tools.ResampleDTIlogEuclidean(self.softwares['ResampleDTIlogEuclidean']['path'])
                resample.dev_mode = True
                resample.execute([str(f), output, '-R', refImagePath, '--correctionType', tensorCorrection,
                                  '-D', displacementFieldPath, '--deformationFieldType', 'displacement',
                                  '-n', str(nbThreads)])
            elif dimension == 3 and components == 1:
                if reader.GetPixelID() not in (sitk.sitkFloat32, sitk.sitkFloat64):
                    logger("Not registering {} (integer image, e.g. a label map)".format(f.name),prep.Color.INFO)
                    continue
                logger("Registering scalar image {}".format(f.name),prep.Color.PROCESS)
                if field is None:
                    field_image = sitk.Cast(sitk.ReadImage(displacementFieldPath), sitk.sitkVectorFloat64)
                    reference = sitk.Image(field_image.GetSize(), sitk.sitkFloat32)
                    reference.CopyInformation(field_image)
                    field = sitk.DisplacementFieldTransform(field_image)
                image = sitk.ReadImage(str(f), sitk.sitkFloat32)
                sitk.WriteImage(sitk.Resample(image, reference, field, sitk.sitkLinear, 0.0), output, True)
            else:
                logger("Not registering {} (neither a scalar nor a tensor image: {} components)".format(f.name, components),prep.Color.INFO)
                continue
            registered[name] = output
            self.addOutputFile(output, 'Registered_' + name.split('.')[0])
        self.result['output']['registered_metric_paths'] = registered
        self.addGlobalVariable('registered_metric_paths', registered)
        logger("Registered {} diffusion metric images of {}".format(len(registered), source.parent),prep.Color.OK)
        return registered

    def referenceImage(self):
        """Fixed image of the registration: the mean tensor of the age appropriate bin of the normative model when one is
        given (referenceNormativeModel, a folder written by 'dmrifiberprofile qc-registration --build-normative' with a
        <bin>/DTI_mean.nrrd per age bin), otherwise the reference image of the protocol."""
        ## the protocol wins; global variables (dmriprep run -g reference_dti ... ) are the fallback, so the module can be
        ## run with default protocols from the command line
        refImagePath = self.protocol['referenceImage'] or self.global_variables.get('reference_dti')
        model = self.protocol.get('referenceNormativeModel') or self.global_variables.get('reference_normative_model')
        if model is not None and str(model).strip() != '':
            mean = self.normativeMean(Path(str(model)))
            if mean is not None:
                refImagePath = mean
        if refImagePath is None or not Path(refImagePath).exists():
            logger("Reference image doesn't exist. Please check the file {} exists.".format(refImagePath),prep.Color.ERROR)
            raise Exception("File not found")
        logger("Reference (fixed) image : {}".format(refImagePath),prep.Color.INFO)
        return str(refImagePath)

    def normativeMean(self, model_dir):
        """<bin>/DTI_mean.nrrd of the age bin of this subject, None (with a warning) if it can't be determined."""
        import json
        manifest = model_dir.joinpath('manifest.json')
        if not manifest.exists():
            logger("Normative model {} has no manifest.json, using the reference image".format(model_dir),prep.Color.WARNING)
            return None
        bins = json.load(open(manifest)).get('bins', [])
        age = self.subjectAge()
        if age is None:
            logger("No age for this image (protocol 'age' or 'ageRegex' on the image path), using the reference image",prep.Color.WARNING)
            return None
        ranges = []
        for b in bins:
            lo, _, hi = str(b).rstrip('m').partition('-')
            try:
                ranges.append((float(lo), float(hi), b))
            except ValueError:
                logger("Ignoring age bin {} of {} (not '<from>-<to>m')".format(b, model_dir),prep.Color.WARNING)
        if len(ranges) == 0:
            logger("Normative model {} has no age bins, using the reference image".format(model_dir),prep.Color.WARNING)
            return None
        ranges.sort()
        ranges[-1] = (ranges[-1][0], float('inf'), ranges[-1][2])  ## the oldest bin is open ended
        label = next((b for lo, hi, b in ranges if lo <= age <= hi), None)
        if label is None:  ## between two bins (e.g. 3.5 with bins 0-3 and 4-9) : the closest one
            lo, hi, label = min(ranges, key=lambda r: min(abs(age - r[0]), abs(age - r[1])))
            logger("Age {} is between the bins of {} ({}), using the closest bin {}".format(age, model_dir, ', '.join(b for _, _, b in ranges), label),prep.Color.WARNING)
        mean = model_dir.joinpath(label).joinpath('DTI_mean.nrrd')
        if not mean.exists():
            logger("Normative model has no mean tensor {}, using the reference image".format(mean),prep.Color.WARNING)
            return None
        logger("Age {} : registering to the mean tensor of bin {} of the normative model".format(age, label),prep.Color.INFO)
        return str(mean)

    def subjectAge(self):
        """Age of this image: the protocol 'age', otherwise 'ageRegex' (group 1, in the same unit as the bins) matched on
        the path of the input DTI or of the source image."""
        age = self.protocol.get('age') or self.global_variables.get('age')
        if age is not None and str(age).strip() != '':
            return float(age)
        pattern = self.protocol.get('ageRegex')
        if pattern is None or str(pattern).strip() == '':
            return None
        paths = [self.dtiImagePath, getattr(self.image, 'filename', None), str(self.output_dir)]
        for path in [p for p in paths if p]:
            match = re.search(str(pattern), str(path))
            if match:
                return float(match.group(1))
        return None
