
#
#   common/tools/base.py 
#   2021-05-10
#   Written by SK Park, NIRAL, UNC
#
#   External tool wrapper base class
#

import sys
import time
from pathlib import Path 
import subprocess as sp
import dmri.common 

logger=dmri.common.logger.write

### decorators

def measure_time(func):  ## decorator
    def wrapper(*args,**kwargs):
        logger("[{}] begins ... ".format(func.__qualname__),dmri.common.Color.DEV)
        bt=time.time()
        logger("{}".format(args))
        res=func(*args,**kwargs)
        et=time.time()-bt
        logger("[{}] Processed time : {:.2f}s".format(func.__qualname__,et),dmri.common.Color.DEV)
        return res 
    return wrapper 

class ExternalToolWrapper(object):
    def __init__(self,binary_path):
        self.binary_path=binary_path
        self.arguments=[]

    def setPath(self,binary_path : str):
        assert(Path(binary_path).exists())
        self.binary_path=str(binary_path)

    def getPath(self):
        assert(self.binary_path is not None)
        return self.binary_path

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
        output.check_returncode()
        return output ## output.returncode, output.stdout output.stderr, output.args, output.check_returncode()


    @measure_time
    def execute(self,stdin=None):
        command=self.getCommand()
        output=sp.run(command,capture_output=True,text=True,stdin=stdin)
        #logger("{}\n{} {}".format(output.args,output.stdout,output.stderr))
        output.check_returncode()
        return output  ## output.returncode, output.stdout output.stderr, output.args, output.check_returncode()
    
    @measure_time
    def execute_pipe(self,stdin=None):
        command=self.getCommand()
        if stdin is None:
            pipe_output=sp.Popen(command,stdout=sp.PIPE)
        else:
            pipe_output=sp.Popen(command,stdin=stdin,stdout=sp.PIPE)
        return pipe_output 