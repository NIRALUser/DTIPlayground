from dtiplayground.dmri.common.tools.base import ExternalToolWrapper

class DTIEstim(ExternalToolWrapper):
    def __init__(self,binary_path= None, **kwargs):
        super().__init__(binary_path, **kwargs)

    def estimate(self,dwi_path, output_path, options=[]):
        arguments=[]
        arguments+=['--dwi_image',dwi_path]
        arguments+=['--tensor_output',output_path]
        arguments+=options
        self.setArguments(arguments)
        return self.execute(arguments)
        