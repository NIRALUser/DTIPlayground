
# from .. import io as dwiio
import yaml, inspect
from pathlib import Path 
import dtiprep 
logger=dtiprep.logger.write


class DTIPrepModule:
    def __init__(self,*args, **kwargs):
        self.name=self.__class__.__name__
        self.image=None
        self.protocol=None
        self.result_history=None
        self.result={
            "module_name" : None,
            "input" : None,
            "output": {
                "image_path" : None, #output image path (string)
                "success" : False,  
                "parameters" : {}
            }
        }
        ##
        self.template=None

        ## loading template file (yml)
        self.loadTemplate()

    def initialize(self,result_history):
        self.result_history=result_history
        inputpath=Path(self.result_history[0]["output"]["image_path"]).absolute()
        self.result={  ### use this to pass the result (protocol class just appends those object)
            "module_name" : self.name,
            #"protocol" : self.getProtocol(),
            "input" : self.result_history[-1]["output"],
            "output" :{
                "image_path" : str(Path(inputpath).parent.joinpath(inputpath.stem+'_'+self.name + inputpath.suffix)), #output image path (string)
                "success" : False,  
                "parameters" : {}
            }
        }
        
    def getPreviousResult(self):
        return self.result_history[-1]

    def loadTemplate(self):
        modulepath=inspect.getfile(self.__class__)
        template_filename=Path(modulepath).parent.joinpath(self.name+".yml")
        self.template=yaml.safe_load(open(template_filename,'r'))

    def setImage(self, image ):
        self.image=image

    def setProtocol(self,protocols):
        self.protocol=protocols[self.name]

    def getProtocol(self):
        return self.protocol

    def generateDefaultProtocol(self):
        self.protocol={}
        for k,v in self.template['protocol'].items():
                self.protocol[k]=v['default_value']
        return self.protocol
    
    def process(self,*args,**kwargs): ## returns new result array (User implementation), returns output result
        pass

    def run(self,*args,**kwargs): #wrapper 

        try:
            self.process(*args,**kwargs)['output']
        except Exception as e:
            logger("Exception occurred in {}.run() : {}".format(self.name,str(e)))
            traceback.print_exc()
            self.result["output"]["success"]=False
        finally:
            return self.result["output"]["success"]

    def getResult(self):
        return self.result_history+[self.result]