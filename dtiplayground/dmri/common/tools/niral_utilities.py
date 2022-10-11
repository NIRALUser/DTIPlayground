from dtiplayground.dmri.common.tools.base import ExternalToolWrapper
from dtiplayground.dmri.common import measure_time 
import dtiplayground.dmri.common
from pathlib import Path 
import subprocess as sp
import os 

class NIRALUtilities(ExternalToolWrapper):
    def __init__(self,binary_path= None, **kwargs): ## binary_path in this class is binary dir  
        super().__init__(binary_path, **kwargs)
        self.binary_path=None
        if binary_path is not None:
            self.binary_path=binary_path
        elif 'softwares' in kwargs:
            self.binary_path=kwargs['softwares']['niral_utilities']['path']

        self.dev_mode=False

    def polydatatransform(self,arguments: list):
        binary_name='polydatatransform'
        self.setArguments(arguments)
        return self.execute(binary_name,arguments)    

    def polydatamerge(self,arguments: list):
        binary_name='polydatamerge'
        self.setArguments(arguments)
        return self.execute(binary_name,arguments)    

    @measure_time
    def execute(self,binary_name,arguments=None,stdin=None):
        binary=Path(self.binary_path).joinpath(binary_name).__str__()
        command=[binary]+self.getArguments()
        if arguments is not None: command=[binary]+arguments
        self.logger.write("{}".format(command))
        output=sp.run(command,capture_output=True,text=True,stdin=stdin)
        if self.dev_mode:
            self.logger.write("{}\n{} {}".format(output.args,output.stdout,output.stderr))
            output.check_returncode()
        return output  ## output.returncode, output.stdout output.stderr, output.args, output.check_returncode()

    @measure_time
    def execute_pipe(self,binary_name,stdin=None):
        binary=Path(self.binary_path).joinpath(binary_name).__str__()
        command=[binary]+self.getArguments()
        if arguments is not None: command=[binary]+arguments
        self.logger.write("{}".format(command))
        if stdin is None:
            pipe_output=sp.Popen(command,stdout=sp.PIPE)
        else:
            pipe_output=sp.Popen(command,stdin=stdin,stdout=sp.PIPE)
        return pipe_output 