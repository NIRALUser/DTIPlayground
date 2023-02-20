from dtiplayground.dmri.common.tools.base import ExternalToolWrapper

class ImageMath(ExternalToolWrapper):
    def __init__(self,binary_path= None, **kwargs):
        super().__init__(binary_path, **kwargs)
        self.binary_path=None
        if binary_path is not None:
            self.binary_path=binary_path
        elif 'softwares' in kwargs:
            self.binary_path=kwargs['softwares']['ImageMath']['path']

    def rescale(self,inputfile, outputfile , rescale=[0,10000]):
        rescale_str = ",".join(list(map(str,rescale)))
        arguments=[inputfile,'-outfile',outputfile,'-rescale',rescale_str]
        self.setArguments(arguments)
        return self.execute(arguments)

    def normalize(self,inputfile,outputfile,referencefile):
        arguments=[inputfile,'-outfile',outputfile,'-matchHistogram',referencefile]
        self.setArguments(arguments)
        return self.execute(arguments)

    def average(self,inputfile,outputfile,files_to_average:list):
        arguments=[inputfile,'-outfile',outputfile,'-avg']+files_to_average
        self.setArguments(arguments)
        return self.execute(arguments)




    