from dmri.common.tools.base import ExternalToolWrapper

class DTIAverage(ExternalToolWrapper):
    def __init__(self,*args,**kwargs):
        super().__init__(DTIAverage,*args,**kwargs)

    