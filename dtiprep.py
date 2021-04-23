#!/usr/bin/python3

#
#
# dtiprep launcher 
#
#


from pathlib import Path
import argparse,yaml
import traceback,time,copy,yaml,sys,os,uuid
import dtiprep
import dtiprep.modules
import dtiprep.protocols

logger=dtiprep.logger.write 

### unit functions

def initialize_logger(args):
    ## default log setting
    dtiprep.logger.setLogfile(args.log)
    dtiprep.logger.setTimestamp(not args.no_log_timestamp)
    dtiprep.logger.setVerbosity(not args.no_verbosity)

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
        if home_dir.exists():
            config_file=home_dir.joinpath('config.yml')
            environment_file=home_dir.joinpath('environment.yml')
            initialize_logger(args)
            return func(args)
        else: 
            raise Exception("Not initialized, please run init command at the first use")
    return wrapper

def log_off(func):
    def wrapper(*args,**kwargs):
        dtiprep.logger.setVerbosity(False)
        res=func(*args,**kwargs)
        dtiprep.logger.setVerbosity(True)
        return res 
    return wrapper


### command functions

def command_init(args):
    ## reparametrization
    home_dir=Path(args.config_dir)

    ## Function begins
    if not check_initialized(args):
        home_dir.mkdir(parents=True,exist_ok=True)
        user_module_dir=home_dir.joinpath('modules').absolute()
        user_module_dir.mkdir(parents=True,exist_ok=True)
        initialize_logger(args)
        config_filename=home_dir.joinpath("config.yml")
        environment_filename=home_dir.joinpath("environment.yml")
        ## make configuration file (config.yml)
        config={"user_module_directories": [str(user_module_dir)]}
        yaml.dump(config,open(config_filename,'w'))
        logger("Config file written to : {}".format(str(config_filename)),dtiprep.Color.INFO)
        ## make environment file (environment.yml)
        modules=dtiprep.modules.load_modules(user_module_paths=config['user_module_directories'])
        environment=dtiprep.modules.generate_module_envionrment(modules)
        yaml.dump(environment,open(environment_filename,'w'))
        logger("Environment file written to : {}".format(str(environment_filename)),dtiprep.Color.INFO)
        logger("Initialized. Local configuration will be stored in {}".format(str(home_dir)),dtiprep.Color.OK)
        return True
    else:
        logger("Already initialized in {}".format(str(home_dir)),dtiprep.Color.WARNING)
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
    modules=dtiprep.modules.load_modules(user_module_paths=config['user_module_directories'])
    environment=dtiprep.modules.generate_module_envionrment(modules)
    yaml.dump(environment,open(environment_filename,'w'))
    logger("Environment file written to : {}".format(str(environment_filename)),dtiprep.Color.INFO)
    logger("Initialized. Local configuration will be stored in {}".format(str(home_dir)),dtiprep.Color.OK)
    return True


@after_initialized
@log_off
def command_make_protocols(args):
    ## reparametrization
    options={
        "config_dir" : args.config_dir,
        "input_image_path" : args.input_image,
        "pipeline" : args.pipeline,
        "output_path" : args.output    
    }
    if options['output_path'] is not None:
        dtiprep.logger.setVerbosity(True)
    ## load config file
    config,environment = load_configurations(options['config_dir'])
    modules=dtiprep.modules.load_modules(user_module_paths=config['user_module_directories'])
    modules=dtiprep.modules.check_module_validity(modules,environment)  
    proto=dtiprep.protocols.Protocols(modules)
    proto.loadImage(options['input_image_path'],b0_threshold=10)
    proto.makeDefaultProtocols(options['pipeline'])
    outstr=yaml.dump(proto.getProtocols())
    print(outstr)
    if options['output_path'] is not None:
        open(options['output_path'],'w').write(outstr)
        logger("Protocol file has been writte to : {}".format(options['output_path']),dtiprep.Color.OK)


@after_initialized
def command_run(args):
    ## reparametrization
    options={
        "config_dir" : args.config_dir,
        "input_image_path" : args.input_image,
        "protocol_path" : args.protocols,
        "output_dir" : args.output_dir,
        "pipeline" : args.pipeline,
        "default_protocols":args.default_protocols
    }
    ## logging setup
    Path(options['output_dir']).mkdir(parents=True,exist_ok=True)
    logfilename=str(Path(options['output_dir']).joinpath('log.txt').absolute())
    dtiprep.logger.setLogfile(logfilename)  

    logger("\r----------------------------------- QC Begins ----------------------------------------\n")

    ## load config file and run pipeline
    config,environment = load_configurations(options['config_dir'])
    modules=dtiprep.modules.load_modules(user_module_paths=config['user_module_directories'])
    modules=dtiprep.modules.check_module_validity(modules,environment)  
    proto=dtiprep.protocols.Protocols(modules)
    proto.loadImage(options['input_image_path'],b0_threshold=10)
    proto.setOutputDirectory(options['output_dir'])
    if options['default_protocols']:
        proto.makeDefaultProtocols(options['pipeline'])
    else:
        proto.loadProtocols(options["protocol_path"])

    res=proto.runPipeline()
    logger("\r----------------------------------- QC Done ----------------------------------------\n")
    return res 
### Arguments 

def get_args():
    current_dir=Path(__file__).parent
    config_dir=Path(os.environ.get('HOME')).joinpath('.niral-dti/dtiprep')
    parser=argparse.ArgumentParser(prog="dtiprep",description="DTIPrep is a tool that performs quality control over diffusion weighted images. Quality control is very essential preprocess in DTI research, in which the bad gradients with artifacts are to be excluded or corrected by using various computational methods. The software and library provides a module based package with which users can make his own QC pipeline as well as new pipeline modules.",
                                                  epilog="Written by SK Park (sangkyoon_park@med.unc.edu) , Neuro Image Research and Analysis Laboratories, University of North Carolina @ Chapel Hill , United States. All rights are left out somewhere in the universe, 2021")
    #parser.add_argument('command',help='command',type=str)
    subparsers=parser.add_subparsers(help="Commands")
    
    ## init command
    parser_init=subparsers.add_parser('init',help='Initialize configurations')
    parser_init.set_defaults(func=command_init)

    ## init command
    parser_update=subparsers.add_parser('update',help='Update environment file')
    parser_update.set_defaults(func=command_update)

    ## generate-default-protocols
    parser_make_protocols=subparsers.add_parser('make-protocols',help='Generate default protocols')
    parser_make_protocols.add_argument('-i','--input-image',help='Input image path',type=str,required=True)
    parser_make_protocols.add_argument('-o','--output',help='Output protocol file path',type=str)
    parser_make_protocols.add_argument('-l','--pipeline',metavar="MODULE",help='Pipeline sequence of modules, only works with default protocols. Example : -l DIFFUSION_Check SLICE_Check',nargs='+')
    parser_make_protocols.set_defaults(func=command_make_protocols)

    ## run command
    parser_run=subparsers.add_parser('run',help='Run pipeline')
    parser_run.add_argument('-i','--input-image',help='Input image path',type=str,required=True)
    parser_run.add_argument('-o','--output-dir',help="Output directory",type=str,required=True)
    parser_run.add_argument('-p','--protocols',help='Protocol file path',type=str)
    parser_run.add_argument('-l','--pipeline',metavar="MODULE",help='Pipeline sequence of modules, only works with -d option. Example : -l DIFFUSION_Check SLICE_Check',nargs='+')
    parser_run.add_argument('-d','--default-protocols',help='Use default protocols',default=False,action='store_true')
    parser_run.set_defaults(func=command_run)

    ## log related
    parser.add_argument('--config-dir',help='Configuration directory',default=str(config_dir))
    parser.add_argument('--log',help='log file',default=str(config_dir.joinpath('log.txt')))
    parser.add_argument('--no-log-timestamp',help='Add timestamp in the log', default=False, action="store_true")
    parser.add_argument('--no-verbosity',help='Do not show any logs in the terminal', default=False, action="store_true")
    
    ## if no parameter is furnished, exit with printing help
    if len(sys.argv)==1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    args=parser.parse_args()
    return args 

if __name__=='__main__':
    args=get_args()

    try:
        dtiprep.logger.setTimestamp(True)
        result=args.func(args)
    except Exception as e:
        dtiprep.logger.setVerbosity(True)
        msg=traceback.format_exc()
        logger(msg,dtiprep.Color.ERROR)
        exit(-1)
    finally:
        pass


