
#
#   common/tools/base.py 
#   2021-05-10
#   Written by SK Park, NIRAL, UNC
#
#   External tool wrapper base class
#



from pathlib import Path 
import subprocess as sp


class ExternalToolWrapper(object):
    def __init__(self,*args,**argv):
        self.path=None
        self.arguments=[]

    def __str__(self):
        return " ".join(self.getCommand())

    def setPath(self,path : str):
        assert(Path(path).exists())
        self.path=str(path)

    def getPath(self):
        assert(self.path is not None)
        return self.path

    def setArguments(self,args_list:list):
        self.arguments=args_list 

    def getArguments(self):
        return self.arguments 

    def setArgumentsString(self, args_str:str):
        self.arguments=args_str.split()

    def getCommand(self):
        return [self.getPath()]+self.arguments 

    def executeWithArgumentString(self,arguments:str):
        args_list=arguments.split()
        command=[self.getPath()]+self.arguments 
        output=sp.run(command,capture_output=True,text=True)
        return output ## output.returncode, output.stdout output.stderr, output.args, output.check_returncode()

    def execute(self):
        command=self.getCommand()
        output=sp.run(command,capture_output=True,text=True)
        return output  ## output.returncode, output.stdout output.stderr, output.args, output.check_returncode()

