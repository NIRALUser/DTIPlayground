from dtiplayground.dmri.common.tools.base import ExternalToolWrapper

class ImageMath(ExternalToolWrapper):
    def __init__(self,binary_path):
        super().__init__(binary_path)

    def rescale(self,inputfile, outputfile , rescale=[0,10000]):
        arguments=[inputfile,'-outfile',outfile,'-rescale',",".join(rescale)]
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




    