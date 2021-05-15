from dmri.common.tools.base import ExternalToolWrapper

class ImageMath(ExternalToolWrapper):
    def __init__(self,*args,**kwargs):
        super().__init__(ImageMath,*args,**kwargs)

    