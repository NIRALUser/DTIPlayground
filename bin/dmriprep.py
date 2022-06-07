#!python

import shutil
import os 
import importlib
from pathlib import Path
import argparse,yaml
from argparse import RawTextHelpFormatter
import traceback,time,copy,yaml,sys,uuid
import sys
sys.path.append(Path(__file__).resolve().parent.parent.__str__()) ## this line is for development
import dtiplayground
import dtiplayground.dmri.common
from dtiplayground.config import INFO as info
logger=dtiplayground.dmri.common.logger.write 
color= dtiplayground.dmri.common.Color

### unit functions

def initialize_logger(args):
    ## default log setting
    dtiplayground.dmri.common.logger.setLogfile(args.log)
    dtiplayground.dmri.common.logger.setTimestamp(not args.no_log_timestamp)
    dtiplayground.dmri.common.logger.setVerbosity(not args.no_verbosity)

def check_initialized(args):
    home_dir=Path(args.config_dir)
    if home_dir.exists():
        config_file=home_dir.joinpath('config.yml')
        environment_file=home_dir.joinpath('environment.yml')
        if not config_file.exists():  return False
        if not environment_file.exists(): return False
        return True
    else: 
        return False

def load_configurations(config_dir:str):
    ## reparametrization
    home_dir=Path(config_dir)
    ## Function begins
    config_filename=home_dir.joinpath("config.yml")
    environment_filename=home_dir.joinpath("environment.yml")
    config=yaml.safe_load(open(config_filename,'r'))
    environment=yaml.safe_load(open(environment_filename,'r'))
    return config,environment

### decorators
def after_initialized(func): #decorator for other functions other than command_init
    def wrapper(args):
        home_dir=Path(args.config_dir)
        if home_dir.exists() and home_dir.joinpath('config.yml').exists() and home_dir.joinpath('environment.yml').exists():
            config_file=home_dir.joinpath('config.yml')
            environment_file=home_dir.joinpath('environment.yml')
            initialize_logger(args)
            return func(args)
        else: 
            # raise Exception("Not initialized, please run init command at the first use")
            logger("Configuration directory is not found or some files are missing, commencing initialization ...",dtiplayground.dmri.common.Color.WARNING)
            command_init(args)
            config_file=home_dir.joinpath('config.yml')
            environment_file=home_dir.joinpath('environment.yml')
            initialize_logger(args)
            return func(args)
    return wrapper

def log_off(func):
    def wrapper(*args,**kwargs):
        dtiplayground.dmri.common.logger.setVerbosity(False)
        res=func(*args,**kwargs)
        dtiplayground.dmri.common.logger.setVerbosity(True)
        return res 
    return wrapper

def search_fsl():
    fslpath=Path(os.environ['FSLDIR'])
    if fslpath.exists():
        logger("FSL directory found : {}".format(os.environ['FSLDIR']), color.OK)
    else:
        logger("FSL directory not found for environment variable FSLDIR in: {}".format(os.environ['FSLDIR']), color.ERROR)
        search_dir = input("Specify the directory of installed FSL [/] :")
        if not search_dir: 
            search_dir = '/'
        search_dir = Path(search_dir)
        candidates = search_dir.glob("**/bin/fsl")
        logger("Searching in {}".format(search_dir.__str__()),color.PROCESS)
        for c in candidates:
            c = Path(c)
            if c.__str__().lower().endswith('/bin/fsl'):
                fslpath = c.resolve().parent.parent
                logger("Found : {}".format(fslpath.__str__()), color.OK)
                confirm = input("Is this FSL what you want? [Y/n]")
                if not confirm: confirm = 'y'
                if confirm.lower() == 'y':
                    break
    return fslpath

def search_niral_tools():
    pass
    
### command functions

def command_find_tools(args):
    ## reparametrization
    home_dir=Path(args.config_dir)

    ## Function begins
    config_filename=home_dir.joinpath("config.yml")
    environment_filename=home_dir.joinpath("environment.yml")
    software_filename=home_dir.joinpath('software_paths.yml')
    software_info_path=Path(dtiplayground.__file__).resolve().parent.joinpath("dmri/common/data/software_paths.yml")
    ## load default software paths

    software_paths=yaml.safe_load(open(software_info_path,'r'))

    ## search FSL
    fslpath = search_fsl()
    logger("Selected FSL directory is : {}".format(fslpath.__str__()),color.INFO)
    software_paths['softwares']['FSL']['path']=fslpath.__str__()

    ## search NIRAL
   
    return True

def command_init(args):
    ## reparametrization
    home_dir=Path(args.config_dir)

    ## Function begins
    home_dir.mkdir(parents=True,exist_ok=True)
    user_module_dir=home_dir.joinpath('modules').absolute()
    user_module_dir.mkdir(parents=True,exist_ok=True)
    user_tools_param_dir=home_dir.joinpath('parameters').absolute()
    user_tools_param_dir.mkdir(parents=True,exist_ok=True)
    template_filename=home_dir.joinpath("protocol_template.yml").absolute()
    source_template_path=Path(dtiplayground.dmri.preprocessing.__file__).parent.joinpath("templates/protocol_template.yml")
    protocol_template=yaml.safe_load(open(source_template_path,'r'))
    initialize_logger(args)
    config_filename=home_dir.joinpath("config.yml")
    environment_filename=home_dir.joinpath("environment.yml")
    ## make configuration file (config.yml)
    config={"user_module_directories": [str(user_module_dir)],"protocol_template_path" : 'protocol_template.yml'}
    yaml.dump(protocol_template,open(template_filename,'w'))
    yaml.dump(config,open(config_filename,'w'))
    logger("Config file written to : {}".format(str(config_filename)),dtiplayground.dmri.preprocessing.Color.INFO)
    ## copy default software path
    software_info_path=Path(dtiplayground.__file__).resolve().parent.joinpath("dmri/common/data/software_paths.yml")
    software_filename=home_dir.joinpath('software_paths.yml')
    shutil.copy(software_info_path,software_filename)
    logger("Software path file is written to : {}".format(str(software_filename)),dtiplayground.dmri.preprocessing.Color.INFO)

    modules=dtiplayground.dmri.preprocessing.modules.load_modules(user_module_paths=config['user_module_directories'])
    environment=dtiplayground.dmri.preprocessing.modules.generate_module_envionrment(modules,str(home_dir))
    yaml.dump(environment,open(environment_filename,'w'))
    logger("Environment file written to : {}".format(str(environment_filename)),dtiplayground.dmri.preprocessing.Color.INFO)
    logger("Initialized. Local configuration will be stored in {}".format(str(home_dir)),dtiplayground.dmri.preprocessing.Color.OK)
    
    return True


@after_initialized
def command_update(args):
    ## reparametrization
    home_dir=Path(args.config_dir)

    ## Function begins
    config_filename=home_dir.joinpath("config.yml")
    environment_filename=home_dir.joinpath("environment.yml")

    ## load config_file
    config=yaml.safe_load(open(config_filename,'r'))
    ## make environment file (environment.yml)
    modules=dtiplayground.dmri.preprocessing.modules.load_modules(user_module_paths=config['user_module_directories'])
    environment=dtiplayground.dmri.preprocessing.modules.generate_module_envionrment(modules,str(home_dir))
    yaml.dump(environment,open(environment_filename,'w'))
    logger("Environment file written to : {}".format(str(environment_filename)),dtiplayground.dmri.preprocessing.Color.INFO)
    logger("Initialized. Local configuration will be stored in {}".format(str(home_dir)),dtiplayground.dmri.preprocessing.Color.OK)
    return True

@after_initialized
@log_off
def command_make_protocols(args):
    ## reparametrization
    options={
        "config_dir" : args.config_dir,
        "input_image_paths" : args.input_images,
        "module_list": args.module_list,
        "output_path" : args.output,
        "baseline_threshold" : args.b0_threshold,
        "output_format" : args.output_format,
        "no_output_image" : args.no_output_image
    }
    if options['output_path'] is not None:
        dtiplayground.dmri.common.logger.setVerbosity(True)
    ## load config file
    config,environment = load_configurations(options['config_dir'])
    template_path=Path(options['config_dir']).joinpath(config['protocol_template_path'])
    template=yaml.safe_load(open(template_path,'r'))
    proto=dtiplayground.dmri.preprocessing.protocols.Protocols(options['config_dir'])
    proto.loadImages(options['input_image_paths'],b0_threshold=options['baseline_threshold'])
    if options['module_list'] is not None and  len(options['module_list'])==0:
            options['module_list']=None
    proto.makeDefaultProtocols(options['module_list'],template=template,options=options)
    outstr=yaml.dump(proto.getProtocols())
    print(outstr)
    if options['output_path'] is not None:
        open(options['output_path'],'w').write(outstr)
        logger("Protocol file has been writte to : {}".format(options['output_path']),dtiplayground.dmri.preprocessing.Color.OK)


@after_initialized
def command_run(args):
    ## reparametrization
    options={
        "config_dir" : args.config_dir,
        "input_image_paths" : args.input_image_list,
        "protocol_path" : args.protocols,
        "output_dir" : args.output_dir,
        "default_protocols":args.default_protocols,
        "num_threads":args.num_threads,
        "execution_id":args.execution_id,
        "baseline_threshold" : args.b0_threshold,
        "output_format" : args.output_format,
        "output_file_base" : args.output_file_base,
        "no_output_image" : args.no_output_image
    }
    if args.output_format is not None:
        options['output_format']=args.output_format.lower()
    ## load config file and run pipeline
    config,environment = load_configurations(options['config_dir'])
    template_path=Path(options['config_dir']).joinpath(config['protocol_template_path'])
    template=yaml.safe_load(open(template_path,'r'))
    proto=dtiplayground.dmri.preprocessing.protocols.Protocols(options['config_dir'])
    proto.loadImages(options['input_image_paths'],b0_threshold=options['baseline_threshold'])
    if options['output_dir'] is None:
        raise Exception("Output directory is missing")
    else:
        proto.setOutputDirectory(options['output_dir'])
    if options['default_protocols'] is not None:
        if len(options['default_protocols'])==0:
            options['default_protocols']=None
        proto.makeDefaultProtocols(options['default_protocols'],template=template,options=options)
    elif options['protocol_path'] is not None:
        proto.loadProtocols(options["protocol_path"])
    else :
        proto.makeDefaultProtocols(options['default_protocols'],template=template,options=options)
    if options['num_threads'] is not None:
        proto.setNumThreads(options['num_threads'])
    Path(options['output_dir']).mkdir(parents=True,exist_ok=True)
    logfilename=str(Path(options['output_dir']).joinpath('log.txt').absolute())
    dtiplayground.dmri.common.logger.setLogfile(logfilename)  
    logger("\r----------------------------------- QC Begins ----------------------------------------\n")
    res=proto.runPipeline(options=options)
    logger("\r----------------------------------- QC Done ----------------------------------------\n")
    return res 
### Arguments 

def get_args():
    current_dir=Path(__file__).resolve().parent
    # info=yaml.safe_load(open(current_dir.parent.joinpath('dtiplayground/info.json'),'r'))
    version=info['dmriprep']['version']
    logger("VERSION : {}".format(str(version)))
    config_dir=Path(os.environ.get('HOME')).joinpath('.niral-dti/dmriprep-'+str(version))
    # ## read template
    module_help_str=None
    if config_dir.exists() and config_dir.joinpath('config.yml').exists() and config_dir.joinpath('environment.yml').exists():
        config,environment = load_configurations(str(config_dir))
        template_path=config_dir.joinpath(config['protocol_template_path'])
        template=yaml.safe_load(open(template_path,'r'))
        available_modules=template['options']['execution']['pipeline']['candidates']
        available_modules_list=["{}".format(x['value'])  for x in available_modules if x['description']!="Not implemented"]
        module_help_str="Avaliable Modules := \n" + " , ".join(available_modules_list)
        # print(module_help_str)
    uid, ts = dtiplayground.dmri.common.get_uuid(), dtiplayground.dmri.common.get_timestamp()

    ### Argument parsers

    parser=argparse.ArgumentParser(prog="dmriprep",
                                   formatter_class=RawTextHelpFormatter,
                                   description="dmriprep is a tool that performs quality control over diffusion weighted images. Quality control is very essential preprocess in DTI research, in which the bad gradients with artifacts are to be excluded or corrected by using various computational methods. The software and library provides a module based package with which users can make his own QC pipeline as well as new pipeline modules.",
                                   epilog="Written by SK Park (sangkyoon_park@med.unc.edu) , Johanna Dubos (johannadubos32@gmail.com) , Neuro Image Research and Analysis Laboratories, University of North Carolina @ Chapel Hill , United States, 2021")
    subparsers=parser.add_subparsers(help="Commands")
    
    ## init command
    parser_init=subparsers.add_parser('init',help='Initialize configurations')
    parser_init.set_defaults(func=command_init)

    ## init command
    parser_update=subparsers.add_parser('update',help='Update environment file')
    parser_update.set_defaults(func=command_update)

    ## software find command
    parser_find_tools=subparsers.add_parser('find-tools',help='Search and update software paths')
    parser_find_tools.set_defaults(func=command_find_tools)

    ## generate-default-protocols
    parser_make_protocols=subparsers.add_parser('make-protocols',help='Generate default protocols',epilog=module_help_str)
    parser_make_protocols.add_argument('-i','--input-images',help='Input image paths',type=str,nargs='+',required=True)
    parser_make_protocols.add_argument('-o','--output',help='Output protocol file(*.yml)',type=str)
    parser_make_protocols.add_argument('-d','--module-list',metavar="MODULE",
                                        help='Default protocols with specified list of modules, only works with default protocols. Example : -d DIFFUSION_Check SLICE_Check',
                                        default=None,nargs='*')
    parser_make_protocols.add_argument('-b','--b0-threshold',metavar='BASELINE_THRESHOLD',help='b0 threshold value, default=10',default=10,type=float)
    parser_make_protocols.add_argument('-f','--output-format',metavar='OUTPUT FORMAT',default=None,help='OUTPUT format, if not specified, same format will be used for output (NRRD | NIFTI)',type=str)
    parser_make_protocols.add_argument('--no-output-image',help="No output Qced file will be generated",default=False,action='store_true')
    parser_make_protocols.set_defaults(func=command_make_protocols)
        

    ## run command
    parser_run=subparsers.add_parser('run',help='Run pipeline',epilog=module_help_str)
    parser_run.add_argument('-i','--input-image-list',help='Input image paths',type=str,nargs='+',required=True)
    parser_run.add_argument('-o','--output-dir',help="Output directory",type=str,required=True)
    parser_run.add_argument('--output-file-base', help="Output filename base", type=str, required=False)
    parser_run.add_argument('-t','--num-threads',help="Number of threads to use",default=None,type=int,required=False)
    parser_run.add_argument('--no-output-image',help="No output Qced file will be generated",default=False,action='store_true')
    parser_run.add_argument('-b','--b0-threshold',metavar='BASELINE_THRESHOLD',help='b0 threshold value, default=10',default=10,type=float)
    parser_run.add_argument('-f','--output-format',metavar='OUTPUT FORMAT',default=None,help='OUTPUT format, if not specified, same format will be used for output  (NRRD | NIFTI)',type=str)
    run_exclusive_group=parser_run.add_mutually_exclusive_group()
    run_exclusive_group.add_argument('-p','--protocols',metavar="PROTOCOLS_FILE" ,help='Protocol file path', type=str)
    run_exclusive_group.add_argument('-d','--default-protocols',metavar="MODULE",help='Use default protocols (optional : sequence of modules, Example : -d DIFFUSION_Check SLICE_Check)',default=None,nargs='*')
    parser_run.set_defaults(func=command_run)

    ## log related
    parser.add_argument('--config-dir',help='Configuration directory',default=str(config_dir))
    parser.add_argument('--log',help='log file',default=str(config_dir.joinpath('log.txt')))
    # parser.add_argument('--system-log-dir',help='System log directory',default='/BAND/USERS/skp78-dti/system-logs',type=str)
    parser.add_argument('--execution-id',help='execution id',default=uid,type=str)
    parser.add_argument('--no-log-timestamp',help='Remove timestamp in the log', default=False, action="store_true")
    parser.add_argument('--no-verbosity',help='Do not show any logs in the terminal', default=False, action="store_true")
    parser.add_argument('-v','--version', help="Show version", default=False,action="store_true")

    ## if no parameter is furnished, exit with printing help
    if len(sys.argv)==1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    args=parser.parse_args()
    if args.version:
        sys.exit(1)

    return args 

## threading environment
args=get_args()
if hasattr(args,'num_threads'):
    os.environ['OMP_NUM_THREADS']=str(args.num_threads) ## this should go before loading any dipy function. 

import dtiplayground.dmri.preprocessing
import dtiplayground.dmri.preprocessing.modules
import dtiplayground.dmri.preprocessing.protocols

if __name__=='__main__':
    try:
        dtiplayground.dmri.common.logger.setTimestamp(True)
        result=args.func(args)
        exit(0)
    except Exception as e:
        dtiplayground.dmri.common.logger.setVerbosity(True)
        msg=traceback.format_exc()
        logger(msg,dtiplayground.dmri.preprocessing.Color.ERROR)
        exit(-1)
    finally:
        pass


