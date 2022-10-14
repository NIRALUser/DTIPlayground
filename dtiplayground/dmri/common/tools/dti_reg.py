from dtiplayground.dmri.common.tools.base import ExternalToolWrapper

class DTIReg(ExternalToolWrapper):
    def __init__(self,binary_path= None, **kwargs):
        super().__init__(binary_path, **kwargs)

    def execute_with_args(self,args,**kwargs):
        self.setArguments(args)
        return self.execute(args)

    def compute_global_deformation_fields(self,
                                            fixed_volume,
                                            moving_volume,
                                            scalar_measurement,
                                            output_displacement_field,
                                            output_inverse_displacementField,
                                            output_volume,
                                            initial_affine,
                                            brains_transform,
                                            ants_outbase,
                                            program_paths:list,
                                            dti_reg_options:list,
                                            options=[]):

        arguments=[
            '--fixedVolume', fixed_volume,
            '--movingVolume', moving_volume,
            '--scalarMeasurement', scalar_measurement,
            '--outputDisplacementField', output_displacement_field,
            '--outputInverseDeformationFieldVolume', output_inverse_displacementField,
            '--outputVolume', output_volume,
            '--ProgramsPathsVector', ",".join(program_paths)
        ]
        m_DTIRegOptions=dti_reg_options 

        if m_DTIRegOptions[0]=="BRAINS":
          options+=["--method","useScalar-BRAINS"]
          if m_DTIRegOptions[1]=="GreedyDiffeo (SyN)":
            options+=["--BRAINSRegistrationType","GreedyDiffeo"]
          elif m_DTIRegOptions[1]=="SpatioTempDiffeo":
            options+=["--BRAINSRegistrationType","SpatioTempDiffeo"]
          else:
            options+=["--BRAINSRegistrationType",m_DTIRegOptions[1]]
          options += ["--BRAINSnumberOfPyramidLevels",str(m_DTIRegOptions[3])]
          options += ["--BRAINSarrayOfPyramidLevelIterations",str(m_DTIRegOptions[4])]
          if m_DTIRegOptions[2]=="Use computed affine transform":
            options+=["--initialAffine",initial_affine]
          else:
            options +=["--BRAINSinitializeTransformMode",str(m_DTIRegOptions[2])]
          #BRAINSTempTfm = FinalResampPath.joinpath("First_Resampling/" + case_id + "_" + scalar_measurement_type + "_AffReg.txt").__str__()
          options +=["--outputTransform", brains_transform]

        if m_DTIRegOptions[0]=="ANTS":
          options+=["--method","useScalar-ANTS"]
          if m_DTIRegOptions[1]=="GreedyDiffeo (SyN)":
            options+=["--ANTSRegistrationType","GreedyDiffeo"]
          elif m_DTIRegOptions[1]=="SpatioTempDiffeo (SyN)":
            options+=["--ANTSRegistrationType","SpatioTempDiffeo"]
          else:
            options+=["--ANTSRegistrationType",m_DTIRegOptions[1]]
          options+=["--ANTSTransformationStep",str(m_DTIRegOptions[2])]
          options+=["--ANTSIterations",str(m_DTIRegOptions[3])]
          if m_DTIRegOptions[4]=="Cross-Correlation (CC)" :
            options+=["--ANTSSimilarityMetric","CC"]
          elif m_DTIRegOptions[4]=="Mutual Information (MI)" :
            options+=["--ANTSSimilarityMetric","MI"]
          elif m_DTIRegOptions[4]=="Mean Square Difference (MSQ)":
            options+=["--ANTSSimilarityMetric","MSQ"]
          options+=["--ANTSSimilarityParameter",m_DTIRegOptions[5]]
          options+=["--ANTSGaussianSigma",str(m_DTIRegOptions[6])]
          if m_DTIRegOptions[7]=="1":
            options+=["--ANTSGaussianSmoothingOff"]

          options+=["--initialAffine",initial_affine]
          options+=["--ANTSUseHistogramMatching"]
          #ANTSTempFileBase = FinalResampPath.joinpath("First_Resampling/" + case_id + "_" + scalar_measurement_type + "_").__str__()
          options+=["--ANTSOutbase",ants_outbase]

        arguments+=options 
        self.setArguments(arguments)
        return self.execute(arguments)
