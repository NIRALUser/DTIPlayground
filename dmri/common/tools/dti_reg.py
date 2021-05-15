from dmri.common.tools.base import ExternalToolWrapper

class DTIReg(ExternalToolWrapper):
    def __init__(self,*args,**kwargs):
        super().__init__(DTIReg,*args,**kwargs)

    