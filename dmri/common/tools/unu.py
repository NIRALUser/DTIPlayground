from dmri.common.tools.base import ExternalToolWrapper

class UNU(ExternalToolWrapper):
    def __init__(self,*args,**kwargs):
        super().__init__(UNU,*args,**kwargs)

    