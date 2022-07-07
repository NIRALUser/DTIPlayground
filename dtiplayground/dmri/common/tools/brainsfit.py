from dtiplayground.dmri.common.tools.base import ExternalToolWrapper

class BRAINSFit(ExternalToolWrapper):
    def __init__(self,binary_path= None, **kwargs):
        super().__init__(binary_path, **kwargs)

    
    def affine_registration(self,
                            fixed_path,
                            moving_path,
                            output_path,
                            output_transform_path,
                            initial_transform_path,
                            transform_mode):
        arguments=['--fixedVolume',fixed_path,
                           '--movingVolume',moving_path,
                           '--useAffine',
                           '--outputVolume',output_path,
                           '--outputTransform',output_transform_path
                           ]
        if initial_transform_path is None:
            arguments+=['--initializeTransformMode', transform_mode]
        else:
            arguments+=['--initialTransform',initial_transform_path]
        self.setArguments(arguments)
        return self.execute(arguments)
