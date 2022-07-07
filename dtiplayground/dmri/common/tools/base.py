
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
import dtiplayground.dmri.common 

logger=dtiplayground.dmri.common.logger.write

### decorators

def measure_time(func):  ## decorator
    def wrapper(*args,**kwargs):
        logger("[{}] begins ... ".format(func.__qualname__),dtiplayground.dmri.common.Color.DEV)
        bt=time.time()
        logger("{}".format(args))
        res=func(*args,**kwargs)
        et=time.time()-bt
        logger("[{}] Processed time : {:.2f}s".format(func.__qualname__,et),dtiplayground.dmri.common.Color.DEV)
        return res 
    return wrapper 

class ExternalToolWrapper(object):
    def __init__(self,binary_path = None, **kwargs):
        self.binary_path=binary_path
        self.arguments=[]
        self.dev_mode=False

    def setDevMode(self,tf:bool):
        self.dev_mode=tf 

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
        #output.check_returncode()
        return output ## output.returncode, output.stdout output.stderr, output.args, output.check_returncode()


    @measure_time
    def execute(self,arguments=None,stdin=None):
        command=self.getCommand()
        if arguments is not None: command=[self.binary_path]+arguments
        output=sp.run(command,capture_output=True,text=True,stdin=stdin)
        if self.dev_mode:
            logger("{}\n{} {}".format(output.args,output.stdout,output.stderr))
            output.check_returncode()
        return output  ## output.returncode, output.stdout output.stderr, output.args, output.check_returncode()
    
    @measure_time
    def execute_pipe(self,arguments=None,stdin=None):
        command=self.getCommand()
        if arguments is not None: command=[self.binary_path]+arguments
        if stdin is None:
            pipe_output=sp.Popen(command,stdout=sp.PIPE)
        else:
            pipe_output=sp.Popen(command,stdin=stdin,stdout=sp.PIPE)
        return pipe_output 