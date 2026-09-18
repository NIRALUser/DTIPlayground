from dtiplayground.dmri.common.tools.base import ExternalToolWrapper
from dtiplayground.dmri.common import measure_time 
import dtiplayground.dmri.common
from pathlib import Path 
import subprocess as sp
import os 
import re

_options_cache={} # binary path -> set of option names listed in its usage text


class FSL(ExternalToolWrapper):
    def __init__(self,binary_path= None, **kwargs): ## binary_path in this class is binary dir e.g. $FSLHOME 
        super().__init__(binary_path, **kwargs)
        self.binary_path=binary_path
        self.arguments=[]
        self.fslhome=binary_path
        try: ## keep the thread count set by the caller (e.g. from the protocol)
            self.num_threads=int(os.environ.get('OMP_NUM_THREADS',4))
        except ValueError:
            self.num_threads=4
        self.dev_mode=False
        os.environ['FSLDIR']=self.fslhome 
        os.environ['FSLOUTPUTTYPE']="NIFTI_GZ"

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
            outputfile,
            fractional_threshold=None): # bet -f (0..1, bet's default 0.5; smaller gives larger brain outline estimates)
        binary_name='bet'
        arguments=[
                    inputfile,
                    outputfile,
                    '-m',
                    '-v'
                ]
        if fractional_threshold is not None:
            arguments+=['-f',str(fractional_threshold)]
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
        ## --nthr only exists in newer topup builds (not in FSL 6.0.3), topup refuses unknown options
        if 'nthr' in self._supported_options(binary_name):
            arguments.append('--nthr={}'.format(self.num_threads))
        self.setArguments(arguments)
        return self.execute(binary_name,arguments)

    # def eddy_cpu(self,
    #                 imain, # input image filename
    #                 mask, # brain mask filename
    #                 acqp, #acqp filename , topup params for b0 
    #                 index_file, #b0 index filename
    #                 bvals, #bvals filename
    #                 bvecs, #bvecs filename
    #                 out, # output basename (not a filename), path + basename(without extension)
    #                 estimate_move_by_susceptibility:bool = False,  # susceptibility correction
    #                 topup=None, # topuped file (if susceptibility_correct==True)
    #                 data_is_shelled=True,
    #                 repol=True,
    #                 verbose=True
    #                 ):
    #     binary_name='eddy_cpu'
    #     arguments=[]
    #     if topup is not None:  # susceptibility correction 
    #         arguments=[
    #             '--imain={}'.format(imain),
    #             '--mask={}'.format(mask),
    #             '--acqp={}'.format(acqp),
    #             '--index={}'.format(index_file),
    #             '--bvals={}'.format(bvals),
    #             '--bvecs={}'.format(bvecs),
    #             '--out={}'.format(out),
    #             '--topup={}'.format(topup)
    #         ]
    #         if estimate_move_by_susceptibility:
    #             arguments.append('--estimate_move_by_susceptibility')
    #     else: ## singlefile eddy correction without susceptibility
    #         arguments=[
    #             '--imain={}'.format(imain),
    #             '--mask={}'.format(mask),
    #             '--acqp={}'.format(acqp),
    #             '--index={}'.format(index_file),
    #             '--bvals={}'.format(bvals),
    #             '--bvecs={}'.format(bvecs),
    #             '--out={}'.format(out)
    #         ]
    #     if data_is_shelled: arguments.append('--data_is_shelled')
    #     if verbose : arguments.append('--verbose')
    #     if repol: arguments.append('--repol')

    #     self.setArguments(arguments)
    #     return self.execute(binary_name,arguments)


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
                    verbose=True,
                    b_range=None # b-values within this range are treated as one shell (None: use eddy's default)
                    ):
        binary_name='eddy_openmp'
        if not Path(self.binary_path).joinpath('bin').joinpath(binary_name).exists():
            binary_name="eddy_cpu"
            
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

        ## --nthr and --b_range only exist in newer eddy builds (not in FSL 6.0.3 / 6.0.6.4).
        ## eddy refuses to run when given an option it does not know, so only pass supported ones.
        supported=self._supported_options(binary_name)
        if 'nthr' in supported:
            arguments.append('--nthr={}'.format(self.num_threads))
        if b_range is not None and b_range > 0:
            ## eddy's default range can merge shells that are close together in some protocols
            if 'b_range' in supported:
                arguments.append('--b_range={}'.format(int(b_range))) ## protocol values may be loaded as float
            else:
                self.logger.write("{} does not support --b_range, using eddy's default shell grouping".format(binary_name))

        self.setArguments(arguments)
        return self.execute(binary_name,arguments)

    def _supported_options(self,binary_name):
        binary=Path(self.binary_path).joinpath('bin').joinpath(binary_name).__str__()
        if binary not in _options_cache:
            try:
                output=sp.run([binary],capture_output=True,text=True,timeout=60) ## without arguments eddy/topup print their usage
                _options_cache[binary]=set(re.findall(r'--([A-Za-z0-9_]+)',output.stdout+output.stderr))
            except (OSError,sp.TimeoutExpired):
                _options_cache[binary]=set()
        return _options_cache[binary]

    @measure_time
    def execute(self,binary_name,arguments=None,stdin=None):
        binary=Path(self.binary_path).joinpath('bin').joinpath(binary_name).__str__()
        command=[binary]+self.getArguments()
        if arguments is not None: command=[binary]+arguments
        self.logger.write("{}".format(command))
        output=sp.run(command,capture_output=True,text=True,stdin=stdin)
        if self.dev_mode:
            self.logger.write("{}\n{} {}".format(output.args,output.stdout,output.stderr))
            output.check_returncode()
        return output  ## output.returncode, output.stdout output.stderr, output.args, output.check_returncode()

    @measure_time
    def execute_pipe(self,binary_name,arguments=None,stdin=None):
        binary=Path(self.binary_path).joinpath('bin').joinpath(binary_name).__str__()
        command=[binary]+self.getArguments()
        if arguments is not None: command=[binary]+arguments
        self.logger.write("{}".format(command))
        if stdin is None:
            pipe_output=sp.Popen(command,stdout=sp.PIPE)
        else:
            pipe_output=sp.Popen(command,stdin=stdin,stdout=sp.PIPE)
        return pipe_output 
