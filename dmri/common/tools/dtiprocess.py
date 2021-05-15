from dmri.common.tools.base import ExternalToolWrapper

class DTIProcess(ExternalToolWrapper):
    def __init__(self,*args,**kwargs):
        super().__init__(DTIProcess,*args,**kwargs)

    