from dmri.common.tools.base import ExternalToolWrapper

class BRAINSFit(ExternalToolWrapper):
    def __init__(self,*args,**kwargs):
        super().__init__(BRAINSFit,*args,**kwargs)

    