from dtiplayground.dmri.common.tools.base import ExternalToolWrapper

class ITKTransformTools(ExternalToolWrapper):
    def __init__(self,binary_path= None, **kwargs):
        super().__init__(binary_path, **kwargs)

    