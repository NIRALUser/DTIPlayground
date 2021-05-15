from dmri.common.tools.base import ExternalToolWrapper

class GreedyAtlas(ExternalToolWrapper):
    def __init__(self,*args,**kwargs):
        super().__init__(GreedyAtlas,*args,**kwargs)

    