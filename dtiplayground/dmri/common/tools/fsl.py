from dtiplayground.dmri.common.tools.base import ExternalToolWrapper
from dtiplayground.dmri.common import measure_time 
import dtiplayground.dmri.common
from pathlib import Path 
import subprocess as sp
import os 

logger=dtiplayground.dmri.common.logger.write

class FSL(ExternalToolWrapper):
    def __init__(self,binary_path= None, **kwargs): ## binary_path in this class is binary dir e.g. $FSLHOME 
        self.binary_path=binary_path
        self.arguments=[]
        self.fslhome=binary_path
        # self.num_threads=4
        self.dev_mode=False
        os.environ['FSLDIR']=self.fslhome 
        os.environ['FSLOUTPUTTYPE']="NIFTI_GZ"
        # os.environ['OMP_NUM_THREADS']=str(self.num_threads)

    def _set_num_threads(self,nth):
        self.num_threads=nth 
        os.environ['OMP_NUM_THREADS']=str(self.num_threads)

    def fslmaths_ops(self,input_file,output_file,operation):
        binary_name='fslmaths'
        arguments=[
                input_file,
                "-T{}".format(operation),
                output_file
        ]
        self.setArguments(arguments)
        return self.execute(binary_name,arguments)    

    def fslmaths_threshold(self,input_file,output_file,threshold=0):
        binary_name='fslmaths'
        arguments=[
                input_file,
                "-thr",
                "{}".format(threshold),
                output_file
        ]
        self.setArguments(arguments)
        return self.execute(binary_name,arguments)    

    def eddy_quad(self,
                  input_base,  #input base is path+file name without extensions
                  idx, #volume index file
                  par,
                  mask,
                  bvals):
        binary_name='eddy_quad'
        arguments=[
                input_base,
                "-idx",idx,
                "-par",par,
                "-m",mask,
                "-b",bvals
        ]
        self.setArguments(arguments)
        return self.execute(binary_name,arguments)    


    def bet(self,
            inputfile,
            outputfile):
        binary_name='bet'
        arguments=[
                    inputfile,
                    outputfile,
                    '-m',
                    '-v'
                ]
        self.setArguments(arguments)
        return self.execute(binary_name,arguments)

    def fslmerge(self,
                 outputfilename,
                 inputfiles:list):
        binary_name='fslmerge'
        arguments=[
                '-t',outputfilename
        ] + inputfiles
        self.setArguments(arguments)
        return self.execute(binary_name,arguments)        

    def topup(self,
              imain,  # input image filename
              datain, # acqp params filename
              out,    # output basename (not a filename), path + basename(without extension)
              fout,   # field output filename (Hz)
              iout,   # movement corrected image output filename
              config):# config filename
        binary_name='topup'
        arguments=[
                '--imain={}'.format(imain),
                '--datain={}'.format(datain),
                '--out={}'.format(out),
                '--fout={}'.format(fout),
                '--iout={}'.format(iout),
                '--config={}'.format(config)
        ]
        self.setArguments(arguments)
        return self.execute(binary_name,arguments)

    def eddy_openmp(self,
                    imain, # input image filename
                    mask, # brain mask filename
                    acqp, #acqp filename , topup params for b0 
                    index_file, #b0 index filename
                    bvals, #bvals filename
                    bvecs, #bvecs filename
                    out, # output basename (not a filename), path + basename(without extension)
                    estimate_move_by_susceptibility:bool = False,  # susceptibility correction
                    topup=None, # topuped file (if susceptibility_correct==True)
                    data_is_shelled=True,
                    repol=True,
                    verbose=True
                    ):
        binary_name='eddy_openmp'
        arguments=[]
        if topup is not None:  # susceptibility correction 
            arguments=[
                '--imain={}'.format(imain),
                '--mask={}'.format(mask),
                '--acqp={}'.format(acqp),
                '--index={}'.format(index_file),
                '--bvals={}'.format(bvals),
                '--bvecs={}'.format(bvecs),
                '--out={}'.format(out),
                '--topup={}'.format(topup)
            ]
            if estimate_move_by_susceptibility:
                arguments.append('--estimate_move_by_susceptibility')
        else: ## singlefile eddy correction without susceptibility
            arguments=[
                '--imain={}'.format(imain),
                '--mask={}'.format(mask),
                '--acqp={}'.format(acqp),
                '--index={}'.format(index_file),
                '--bvals={}'.format(bvals),
                '--bvecs={}'.format(bvecs),
                '--out={}'.format(out)
            ]
        if data_is_shelled: arguments.append('--data_is_shelled')
        if verbose : arguments.append('--verbose')
        if repol: arguments.append('--repol')

        self.setArguments(arguments)
        return self.execute(binary_name,arguments)

    @measure_time
    def execute(self,binary_name,arguments=None,stdin=None):
        binary=Path(self.binary_path).joinpath('bin').joinpath(binary_name).__str__()
        command=[binary]+self.getArguments()
        if arguments is not None: command=[binary]+arguments
        logger("{}".format(command))
        output=sp.run(command,capture_output=True,text=True,stdin=stdin)
        if self.dev_mode:
            logger("{}\n{} {}".format(output.args,output.stdout,output.stderr))
            output.check_returncode()
        return output  ## output.returncode, output.stdout output.stderr, output.args, output.check_returncode()

    @measure_time
    def execute_pipe(self,binary_name,stdin=None):
        binary=Path(self.binary_path).joinpath('bin').joinpath(binary_name).__str__()
        command=[binary]+self.getArguments()
        if arguments is not None: command=[binary]+arguments
        logger("{}".format(command))
        if stdin is None:
            pipe_output=sp.Popen(command,stdout=sp.PIPE)
        else:
            pipe_output=sp.Popen(command,stdin=stdin,stdout=sp.PIPE)
        return pipe_output 