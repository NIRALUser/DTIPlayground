from dmri.common.tools.base import ExternalToolWrapper

class ImageMath(ExternalToolWrapper):
    def __init__(self,binary_path):
        super().__init__(binary_path)

    def rescale(self,inputfile, outputfile , rescale=[0,10000]):
        self.setArguments([inputfile,'-outfile',outfile,'-rescale',",".join(rescale)])
        return self.execute()

    def normalize(self,inputfile,outputfile,referencefile):
        self.setArguments([inputfile,'-outfile',outputfile,'-matchHistogram',referencefile])
        return self.execute()

    def average(self,inputfile,outputfile,files_to_average:list):
        self.setArguments([inputfile,'-outfile',outputfile,'-avg']+files_to_average)
        return self.execute()




    