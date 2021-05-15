from dmri.common.tools.base import ExternalToolWrapper

class CropDTI(ExternalToolWrapper):
    def __init__(self,*args,**kwargs):
        super().__init__(CropDTI,*args,**kwargs)

    