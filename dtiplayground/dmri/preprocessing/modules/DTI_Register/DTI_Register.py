  
import dtiplayground.dmri.preprocessing as prep
import yaml, os, re
from pathlib import Path

import numpy as np

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
        ## a tensor given as input image is registered; otherwise dti_path (e.g. from DTI_Estimate)
        self.dtiImagePath = None
        if self.isTensorImage(getattr(self.image, 'filename', None)):
            self.dtiImagePath=str(self.image.filename)
            logger("Input image is a diffusion tensor, registering it directly : {}".format(self.dtiImagePath),prep.Color.INFO)
        elif 'dti_path' in self.global_variables:
            self.dtiImagePath=self.global_variables['dti_path']
        self.register(**self.protocol)

        logger(yaml.dump(self.image.information))
        self.result['output']['success']=True

        return self.result

    @staticmethod
    def isTensorImage(path):
        """True if path is a NRRD file with a tensor axis (kinds 3D-symmetric-matrix, 3D-masked-symmetric-matrix or 3D-matrix)."""
        if path is None or not str(path).lower().endswith(('.nrrd', '.nhdr')) or not Path(path).is_file():
            return False
        with open(path, 'rb') as f:
            for line in f:
                line = line.decode('latin-1').strip()
                if line == '':
                    break
                if line.lower().startswith('kinds:'):
                    return any(k in ('3d-symmetric-matrix', '3d-masked-symmetric-matrix', '3d-matrix') for k in line.lower().split()[1:])
        return False

    def register(self,**protocol):
        if protocol['method'] == 'ANTs':
            logger("ANTS is selected for the method",prep.Color.INFO)
            self.registerWithANTs(**protocol)
        elif protocol['method'] == 'TensorSVF':
            logger("TensorSVF (diffeomorphic tensor registration) is selected for the method",prep.Color.INFO)
            self.registerWithTensorSVF(**protocol)
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
        sourceImagePath = inputImagePath  # the diffusion metrics are in its folder
        initialAffinePath = self.initialAffine(refImagePath, inputImagePath, scalarMeasurement, tensorCorrection, nbThreads)
        inputImagePath = self.flipTensor(inputImagePath, refImagePath, initialAffinePath)
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
        self.finishRegistration(sourceImagePath, inputImagePath, refImagePath, registeredImagePath, displacementFieldPath,
                                inv_displacementFieldPath, tensorCorrection, nbThreads)
        return True

    def finishRegistration(self, sourceImagePath, inputImagePath, refImagePath, registeredImagePath, displacementFieldPath,
                           inv_displacementFieldPath, tensorCorrection, nbThreads):
        """Outputs, global variables and the registration of the diffusion metrics (both methods)."""
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
            self.registerMetrics(sourceImagePath, refImagePath, displacementFieldPath, tensorCorrection, nbThreads)
        self.addOutputFile(displacementFieldPath, 'DTI_DisplacementField')
        self.addOutputFile(inv_displacementFieldPath, 'DTI_Inverse_DisplacementField')

        #self.writeImageWithOriginalSpace(outputImagePath,'nrrd',dtype='float')
        return True

    def registerWithTensorSVF(self,**protocol):
        """Diffeomorphic registration of the tensors (common/tensor_registration.py): initial affine, correction of the
        tensor frame (tensorFlip, 'rotation' recommended), then a stationary velocity field optimised on the orientation
        and shape of the tensors (normalised deviatoric part of the log tensors, finite strain reorientation), plus a
        free water term when a free water fraction map of the DTI and a reference mean map are available
        (multi-shell data); PyTorch on the GPU when available, otherwise on the CPU."""
        from dtiplayground.dmri.common import tensor_registration
        output_dir = Path(self.output_dir)
        refImagePath = self.referenceImage()
        inputImagePath = output_dir.joinpath('input.nrrd').__str__()
        nbThreads = self.num_threads
        scalarMeasurement = self.protocol.get('scalarMeasurement', 'FA')
        tensorCorrection = self.protocol.get('tensorCorrection', 'abs')
        if self.dtiImagePath is not None:
            inputImagePath = self.dtiImagePath
        else:
            self.writeImageWithOriginalSpace(inputImagePath,'nrrd',dtype='float')
        os.environ['ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS'] = str(nbThreads)
        sourceImagePath = inputImagePath
        initialAffinePath = self.initialAffine(refImagePath, inputImagePath, scalarMeasurement, tensorCorrection, nbThreads)
        if initialAffinePath is None:
            logger("TensorSVF without an initial affine transform: the DTI must already be roughly aligned with the reference",prep.Color.WARNING)
        inputImagePath = self.flipTensor(inputImagePath, refImagePath, initialAffinePath)

        movingFW, referenceFW = self.freeWaterMaps(sourceImagePath, refImagePath)
        params = dict(w_reg=float(self.protocol.get('tensorRegRegularization', 0.15)),
                      smooth=float(self.protocol.get('tensorRegSmoothing', 0.5)),
                      levels=self.intList(self.protocol.get('tensorRegLevels', '4x2x1')),
                      iters=self.intList(self.protocol.get('tensorRegIterations', '200x150x100')),
                      w_fw=float(self.protocol.get('freeWaterWeight', 1.0)) if movingFW else 0.0)
        if len(params['levels']) != len(params['iters']):
            raise Exception("tensorRegLevels ({}) and tensorRegIterations ({}) need the same number of levels".format(
                self.protocol.get('tensorRegLevels'), self.protocol.get('tensorRegIterations')))
        referenceFA = Path(refImagePath).parent.joinpath('FA_mean.nii.gz')
        result = tensor_registration.register(
            refImagePath, inputImagePath, initialAffinePath, output_dir, self.softwares['ResampleDTIlogEuclidean']['path'],
            reference_fa=str(referenceFA) if referenceFA.exists() else None, reference_fw=referenceFW, moving_fw=movingFW,
            params=params, device=self.protocol.get('tensorRegDevice', 'auto'), threads=nbThreads,
            correction=tensorCorrection, log=lambda m: logger(m, prep.Color.PROCESS))
        self.result['output']['tensor_registration'] = result['summary']
        if result['summary']['jacobian_nonpositive'] > 0:
            logger("The deformation folds in {} voxels (Jacobian <= 0); consider a larger tensorRegRegularization".format(
                result['summary']['jacobian_nonpositive']),prep.Color.WARNING)
        self.finishRegistration(sourceImagePath, inputImagePath, refImagePath, result['registered_dti'],
                                result['displacement_field'], result['inverse_displacement_field'], tensorCorrection, nbThreads)
        return True

    @staticmethod
    def intList(value):
        return [int(x) for x in re.split(r'[x,\s]+', str(value).strip()) if x != '']

    FREE_WATER_MAPS = {'FWf': 'FWF_mean', 'NODDI_FWF': 'NODDI_FWF_mean'}  # map of the DTI -> reference mean map

    def freeWaterMaps(self, sourceImagePath, refImagePath):
        """(free water map of the DTI, reference mean map) of the free water term, or (None, None) for a registration
        of the tensors only. freeWater: auto (the FW-tensor fraction <prefix>FWf, else the NODDI fraction
        <prefix>NODDI_FWF, in the folder of the input DTI, each with its reference mean map FWF_mean / NODDI_FWF_mean in
        the folder of the reference tensor, i.e. the age bin of the normative model), FWf, NODDI_FWF, or none;
        freeWaterImage and referenceFreeWater give the maps explicitly."""
        mode = str(self.protocol.get('freeWater') or 'auto').strip()
        if mode.lower() == 'none':
            logger("Free water term off (freeWater none): registering the tensors only",prep.Color.INFO)
            return None, None
        explicit, explicit_ref = self.protocol.get('freeWaterImage'), self.protocol.get('referenceFreeWater')
        source = Path(sourceImagePath)
        prefix = source.name[:-len('tensor.nrrd')] if source.name.endswith('tensor.nrrd') else source.name.split('.')[0] + '_'
        kinds = list(self.FREE_WATER_MAPS) if mode.lower() == 'auto' else [mode]
        for kind in kinds:
            if kind not in self.FREE_WATER_MAPS:
                raise Exception("Unknown freeWater {} (auto, FWf, NODDI_FWF or none)".format(mode))
            moving = explicit or next((str(source.parent.joinpath(prefix + kind + ext)) for ext in ('.nii.gz', '.nii', '.nrrd')
                                       if source.parent.joinpath(prefix + kind + ext).exists()), None)
            reference = explicit_ref or next((str(Path(refImagePath).parent.joinpath(self.FREE_WATER_MAPS[kind] + ext))
                                              for ext in ('.nii.gz', '.nii', '.nrrd')
                                              if Path(refImagePath).parent.joinpath(self.FREE_WATER_MAPS[kind] + ext).exists()), None)
            for path in (explicit, explicit_ref):
                if path and not Path(path).exists():
                    raise Exception("Free water map {} doesn't exist".format(path))
            if moving and reference:
                logger("Free water term: {} with the reference {}".format(moving, reference),prep.Color.INFO)
                self.result['output']['free_water_map'] = moving
                return moving, reference
            if mode.lower() != 'auto':
                raise Exception("freeWater {}: no {} (map of the DTI: {}, reference map: {})".format(
                    mode, kind, moving or 'not found', reference or 'not found'))
        logger("No free water fraction map of the DTI with a reference mean map (single shell data?): registering the tensors only",prep.Color.INFO)
        return None, None

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

    def flipTensor(self, inputImagePath, refImagePath, initialAffinePath):
        """Correction of the tensor frame applied before the registration (tensorFlip, or the global variable
        tensor_flip; when neither is set, rotation, or auto without an initial affine): rotation (see
        rotateTensorFrame), none, explicit axes to flip (e.g. 'x' or 'x,z'), 'voxel' (components in the frame of the voxel
        axes, rotated into the space of the header; with flips e.g. 'voxel,x'), or auto: the correction with the best
        agreement of the principal directions with the reference after the initial affine transform (computed from the
        scalar image, which the correction doesn't change), or with the best coherence of the principal directions along
        the tracts without an initial affine. Returns the path of the DTI to register (input_flipped.nrrd if corrected)."""
        from dtiplayground.dmri.fiberprofile.analysis import detect_flip, flip_tensor
        mode = str(self.protocol.get('tensorFlip') or self.global_variables.get('tensor_flip') or '').strip().lower()
        if mode == '':  # default: rotation, which needs the initial affine; auto (coherence along the tracts) without one
            mode = 'rotation' if initialAffinePath is not None else 'auto'
            logger("tensorFlip not set: using {}".format(mode),prep.Color.INFO)
        self.tensorCorrection = None
        self.tensorRotation = None
        for stale in list(Path(self.output_dir).glob('input_flipped*')) + list(Path(self.output_dir).glob('flipped_*')):  # files of a previous corrected run
            stale.unlink()
        if mode == 'none':
            self.checkResidualRotation(inputImagePath, refImagePath, initialAffinePath, 'none')
            return inputImagePath
        if mode == 'rotation':
            return self.rotateTensorFrame(inputImagePath, refImagePath, initialAffinePath)
        if mode == 'auto':
            fa_min = float(self.protocol.get('tensorFlipFAThreshold', 0.3))
            transform = None
            if initialAffinePath is not None:
                try:
                    transform = detect_flip.read_itk_affine(initialAffinePath)
                except (ValueError, OSError) as e:
                    logger("Initial affine not usable for the flip detection ({}), using the coherence only".format(e),prep.Color.WARNING)
            logger("Detecting the correction of the tensor frame ({})".format(
                "agreement with the reference after the initial affine" if transform is not None else "coherence along the tracts"),prep.Color.PROCESS)
            try:
                rows, best, by_coherence = detect_flip.detect_flip(inputImagePath, refImagePath if transform is not None else None, fa_min, transform)
            except detect_flip.NotAlignedError as e:
                logger("The initial affine doesn't align the DTI with the reference ({}); using the coherence only".format(e),prep.Color.WARNING)
                transform = None
                rows, best, by_coherence = detect_flip.detect_flip(inputImagePath, None, fa_min, None)
            for r in rows:
                if r['same_as'] == '':
                    logger("  {:12s} coherence {:.4f}{}".format(r['correction'], r['coherence'],
                           '  angle to the reference {:.1f} deg'.format(r['angle']) if transform is not None else ''),prep.Color.INFO)
            if transform is not None and best != by_coherence:
                logger("Correction by the reference ({}) and by the coherence ({}) disagree; using {}".format(best, by_coherence, best),prep.Color.WARNING)
            correction = best
        else:
            correction = flip_tensor.correction_name(*flip_tensor.parse_correction(mode))
        self.result['output']['tensor_flip'] = correction
        self.addGlobalVariable('tensor_flip_applied', correction)
        self.checkResidualRotation(inputImagePath, refImagePath, initialAffinePath, correction)
        if correction == 'none':
            logger("Tensor frame not corrected",prep.Color.OK)
            return inputImagePath
        self.tensorCorrection = correction
        flipped = Path(self.output_dir).joinpath('input_flipped.nrrd').__str__()
        flip_tensor.reorient_tensor_file(inputImagePath, flipped, correction)
        logger("Corrected the tensor frame ({}) before the registration: {}".format(correction, flipped),prep.Color.OK)
        self.addOutputFile(flipped, 'DTI_Flipped')
        return flipped

    def checkResidualRotation(self, inputImagePath, refImagePath, initialAffinePath, correction):
        """Warn when the tensor frame, after the flip correction, is still rotated against the reference (by more than
        frame_align.RESIDUAL_WARN_DEG): a rotation no flip corrects, which tensorFlip 'rotation' removes. Needs the
        initial affine; never stops the registration."""
        from dtiplayground.dmri.fiberprofile.analysis import detect_flip, frame_align
        if initialAffinePath is None:
            return None
        fa_min = float(self.protocol.get('tensorFlipFAThreshold', 0.3))
        try:
            transform = detect_flip.read_itk_affine(initialAffinePath)
            if correction == 'none':  # not corrected: a flip may fit better, and a rotation is only measured from the right flip
                rows, best, _ = detect_flip.detect_flip(inputImagePath, refImagePath, fa_min, transform)
                if best != 'none':
                    angle = {row['correction']: row['angle'] for row in rows}
                    logger("The tensor frame correction '{}' fits the reference better than none ({:.1f} vs {:.1f} deg): "
                           "set tensorFlip auto, {} or rotation".format(best, angle[best], angle['none'], best),prep.Color.WARNING)
                    self.result['output']['tensor_flip_suggested'] = best
                    return None
            r = frame_align.residual_rotation_file(inputImagePath, refImagePath, transform, correction, fa_ref=fa_min)
        except Exception as e:
            logger("Residual rotation of the tensor frame not measured ({})".format(e),prep.Color.WARNING)
            return None
        self.result['output']['tensor_frame_residual_deg'] = r['rotation_deg']
        if r['warn']:
            logger(frame_align.residual_message(r, correction),prep.Color.WARNING)
        else:
            logger("Residual rotation of the tensor frame: {:.1f} deg".format(r['rotation_deg']),prep.Color.OK)
        return r

    def rotateTensorFrame(self, inputImagePath, refImagePath, initialAffinePath):
        """tensorFlip 'rotation': the rotation of the tensor frame (any rotation, flips included) that best aligns the
        principal directions of the DTI with those of the reference in white matter after the initial affine transform
        (frame_align.py: the 24 axis permutations and flips, then a continuous refinement). Written as
        input_flipped.nrrd when it differs from the identity by more than 1 degree."""
        import json
        from scipy.spatial.transform import Rotation
        from dtiplayground.dmri.fiberprofile.analysis import detect_flip, frame_align
        if initialAffinePath is None:
            logger("tensorFlip 'rotation' needs an initial affine transform (initialAffine BRAINSFit or file)",prep.Color.ERROR)
            raise Exception("No initial affine for the tensor frame rotation")
        fa_min = float(self.protocol.get('tensorFlipFAThreshold', 0.3))
        logger("Estimating the rotation of the tensor frame (agreement with the reference after the initial affine)",prep.Color.PROCESS)
        try:
            r = frame_align.estimate(inputImagePath, refImagePath, detect_flip.read_itk_affine(initialAffinePath), fa_ref=fa_min)
        except detect_flip.NotAlignedError as e:
            logger("Tensor frame not rotated: {}".format(e),prep.Color.WARNING)
            self.result['output']['tensor_flip'] = 'none'
            self.addGlobalVariable('tensor_flip_applied', 'none')
            return inputImagePath
        json.dump(r, open(Path(self.output_dir).joinpath('tensor_frame_rotation.json'), 'w'), indent=1)
        logger("  angle to the reference {:.1f} deg as is, {:.1f} deg after the best flip/axis swap, {:.1f} deg after the "
               "rotation ({:.1f} deg from the flip, {:.1f} deg in total)".format(r['angle_identity'], r['angle_discrete'],
               r['angle_rotation'], r['refine_deg'], r['total_deg']),prep.Color.INFO)
        R = np.asarray(r['R'])
        self.result['output']['tensor_flip'] = 'rotation'
        self.result['output']['tensor_frame_rotation'] = r['R']
        self.addGlobalVariable('tensor_flip_applied', 'rotation')
        if np.degrees(Rotation.from_matrix(R).magnitude()) < 1.0 or r['angle_identity'] - r['angle_rotation'] < 0.1:
            logger("Tensor frame not corrected (rotation below 1 deg or no gain)",prep.Color.OK)
            return inputImagePath
        self.tensorRotation = R
        flipped = Path(self.output_dir).joinpath('input_flipped.nrrd').__str__()
        frame_align.rotate_tensor_file(inputImagePath, flipped, R)
        logger("Rotated the tensor frame before the registration: {}".format(flipped),prep.Color.OK)
        self.addOutputFile(flipped, 'DTI_Flipped')
        return flipped

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
                tensor_path = str(f)
                if getattr(self, 'tensorCorrection', None):  # same frame as the DTI
                    from dtiplayground.dmri.fiberprofile.analysis import flip_tensor
                    tensor_path = output_dir.joinpath('flipped_' + name).__str__()
                    flip_tensor.reorient_tensor_file(str(f), tensor_path, self.tensorCorrection)
                elif getattr(self, 'tensorRotation', None) is not None:
                    from dtiplayground.dmri.fiberprofile.analysis import frame_align
                    tensor_path = output_dir.joinpath('flipped_' + name).__str__()
                    frame_align.rotate_tensor_file(str(f), tensor_path, self.tensorRotation)
                resample = tools.ResampleDTIlogEuclidean(self.softwares['ResampleDTIlogEuclidean']['path'])
                resample.dev_mode = True
                resample.execute([tensor_path, output, '-R', refImagePath, '--correctionType', tensorCorrection,
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
            logger("No age for this image (protocol 'age', 'ageCSV', 'ageRegex' on the image path or 'ageFallback'), using the reference image",prep.Color.WARNING)
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
        label = next((b for lo, hi, b in ranges if lo <= age < hi + 1), None)  ## lo-hi: from lo up to hi + 1 months
        if label is None:  ## between two bins (e.g. 4.5 with bins 0-3 and 6-9) : the closest one
            lo, hi, label = min(ranges, key=lambda r: min(abs(age - r[0]), abs(age - r[1])))
            logger("Age {} is between the bins of {} ({}), using the closest bin {}".format(age, model_dir, ', '.join(b for _, _, b in ranges), label),prep.Color.WARNING)
        mean = model_dir.joinpath(label).joinpath('DTI_mean.nrrd')
        if not mean.exists():
            logger("Normative model has no mean tensor {}, using the reference image".format(mean),prep.Color.WARNING)
            return None
        logger("Age {} : registering to the mean tensor of bin {} of the normative model".format(age, label),prep.Color.INFO)
        return str(mean)

    def ageOption(self, name):
        """An age option: the protocol value (ageCSV, ageColumn, ...), else the global variable of 'dmriprep run -g' of
        the same name or in snake case (age_csv, age_column, ...); None when neither is set. ageUnits is taken from the
        global variable first, as the protocol always has a value (months)."""
        snake = re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower().replace('_c_s_v', '_csv')
        gvars = getattr(self, 'global_variables', None) or {}
        values = [self.protocol.get(name), gvars.get(name), gvars.get(snake)]
        if name == 'ageUnits':
            values = values[1:] + values[:1]
        return next((v for v in values if v is not None and str(v).strip() != ''), None)

    def subjectAge(self):
        """Age of this image, in the unit of the age bins (months): the protocol 'age' (or the global variable),
        otherwise the row of this scan in 'ageCSV', otherwise 'ageRegex' (group 1) matched on the path of the input
        DTI or of the source image, otherwise 'ageFallback' (or the global variable age_fallback, in ageUnits as the ages of
        ageCSV), with a warning."""
        age = self.ageOption('age')
        if age is not None:
            return float(age)
        age = self.ageFromTable()
        if age is not None:
            return age
        age = self.ageFromPath()
        if age is not None:
            return age
        fallback = self.ageOption('ageFallback')
        if fallback is None:
            return None
        from dtiplayground.dmri.common.age_table import AGE_UNIT_TO_MONTHS
        units = str(self.ageOption('ageUnits') or 'months').strip().lower()
        if units not in AGE_UNIT_TO_MONTHS:
            logger("ageUnits {} is unknown ({}), ageFallback ignored".format(units, ', '.join(AGE_UNIT_TO_MONTHS)),prep.Color.WARNING)
            return None
        try:
            value = float(fallback)
        except (TypeError, ValueError):
            logger("ageFallback {} is not a number, ignored".format(fallback),prep.Color.WARNING)
            return None
        if not value >= 0:
            logger("ageFallback {} is negative, ignored".format(fallback),prep.Color.WARNING)
            return None
        months = value * AGE_UNIT_TO_MONTHS[units]
        unit_note = "" if units == 'months' else " ({:g} {})".format(value, units)
        logger("No age for this image (ageCSV, ageRegex), using the fallback age {:g} month(s){} (ageFallback)".format(months, unit_note),prep.Color.WARNING)
        return months

    def ageFromPath(self):
        """'ageRegex' (group 1) matched on the path of the input DTI or of the source image, None without a match."""
        pattern = self.protocol.get('ageRegex')
        if pattern is None or str(pattern).strip() == '':
            return None
        for path in [p for p in self.agePaths() if p]:
            match = re.search(str(pattern), str(path))
            if match:
                try:
                    return float(match.group(1))
                except (IndexError, ValueError):
                    return None
        return None

    def agePaths(self):
        """Where the subject, the session and the age are looked for."""
        return [self.dtiImagePath, getattr(self.image, 'filename', None), str(self.output_dir)]

    def subjectSession(self):
        """(subject, session) of this image from its path, e.g. sub-1234/ses-012m or sub-1234_ses-012m_dwi.nrrd, else
        the IBIS organization .../999434/VSA-CVD/... (subject 999434, session SA-CVD). Either is None when the path
        doesn't have it."""
        from dtiplayground.dmri.common.age_table import subject_session_from_path
        return subject_session_from_path(*self.agePaths())

    def ageFromTable(self):
        """Age of this scan from the protocol 'ageCSV' (the table of 'qc-registration --age-csv'), None when there is
        no table, no subject in the path or no row for it."""
        path = self.ageOption('ageCSV')
        if path is None:
            return None
        if not Path(str(path)).exists():
            logger("Age table {} doesn't exist, falling back to ageRegex".format(path), prep.Color.WARNING)
            return None
        from dtiplayground.dmri.common.age_table import age_from_table, load_age_table
        subject, session = self.subjectSession()
        if subject is None:
            logger("No sub-<id> nor IBIS <6 digit id>/V<visit> folders in the path of this image: the age table {} "
                   "can't be used".format(path),
                   prep.Color.WARNING)
            return None
        try:
            table = load_age_table(str(path), self.ageOption('ageUnits') or 'months', self.ageOption('ageColumn'),
                                   self.ageOption('ageSubjectColumn'), self.ageOption('ageSessionColumn'))
        except Exception as e:
            logger("Age table {} could not be read ({}), falling back to ageRegex".format(path, e), prep.Color.WARNING)
            return None
        age = age_from_table(subject, session, table)
        if age is None:
            logger("No age in {} for subject {}, session {}, falling back to ageRegex".format(path, subject, session),
                   prep.Color.WARNING)
            return None
        logger("Age of subject {}, session {} from {}: {} month(s)".format(subject, session, path, age), prep.Color.INFO)
        return float(age)
