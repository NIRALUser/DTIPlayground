#!python

import sys
import os 
import traceback
import shutil
from pathlib import Path
import argparse
from argparse import RawTextHelpFormatter
import yaml
sys.path.append(Path(__file__).resolve().parent.parent.__str__()) ## this line is for development
import dtiplayground.dmri.common as common
from dtiplayground.config import INFO as info
from dtiplayground.dmri.preprocessing.app import DMRIPrepApp

logger=common.logger.write 
color= common.Color

def _parse_global_variables(global_vars: list):
    gv = {}
    if global_vars is not None:
        n_vars = int(len(global_vars)/2)
        for i in range(n_vars):
            gv[global_vars[i*2]]=global_vars[i*2+1]
    return gv

##################### commands
def command_init(args):
    ## reparametrization
    options = {
        'config_dir' : args.config_dir,
        'log' : args.log,
        'execution_id' : args.execution_id,
        'no_verbosity' : args.no_verbosity,
        'no_log_timestamp' : args.no_log_timestamp,
        'version' : args.version,
        'tools_dir' : args.tools_dir,
    }
    app = DMRIPrepApp(options['config_dir'])
    return app.initialize(options)
    
def command_remove_module(args):
    options = {
        'config_dir' : args.config_dir,
        'name' : args.name
    }
    app = DMRIPrepApp(options['config_dir'])
    app.remove_module(options)

    return True

def command_add_module(args):
    options = {
        'config_dir': args.config_dir,
        'name' : args.name,
        'base_module' : args.base_module,
        'edit' : args.edit
    }
    app = DMRIPrepApp(options['config_dir'])
    app.add_module(options)


def command_make_protocols(args):
    ## reparametrization
    options={
        "config_dir": args.config_dir,
        "input_images" : args.input_images,
        "module_list": args.module_list,
        "output" : args.output,
        "b0_threshold" : args.b0_threshold,
        "output_format" : args.output_format,
        "no_output_image" : args.no_output_image,
        "global_variables" : _parse_global_variables(args.global_variables)
    }
    app = DMRIPrepApp(options['config_dir'])
    app.makeProtocols(options)


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
        "no_output_image" : args.no_output_image,
        "global_variables" : _parse_global_variables(args.global_variables)
    }
    app = DMRIPrepApp(options['config_dir'])
    app.run(options)
### Arguments 

def command_run_dir(args):
    options = {
        "config_dir" : args.config_dir,
        "output_dir" : args.output_dir,
        "execution_id":args.execution_id,
        "default_protocols": None,
        "global_variables" : _parse_global_variables(args.global_variables)        
    }
    protocol_fn = Path(options['output_dir']).joinpath('protocols.yml')
    if protocol_fn.exists():
        options['protocol_path']=protocol_fn.__str__()
    else:
        protocol_fn = Path(options['output_dir']).joinpath('protocols.json')
        if protocol_fn.exists():
            options['protocol_path']=protocol_fn.__str__()
        else:
            raise Exception("No protocols fille exists")
    protocol = yaml.safe_load(open(protocol_fn,'r'))
    options['num_threads'] = protocol['io']['num_threads']
    options['output_format'] = protocol['io']['output_format']
    options['baseline_threshold'] = protocol['io']['baseline_threshold']
    options['output_filename_base'] = protocol['io']['output_filename_base']
    options['input_image_paths'] = [protocol['io']['input_image_1']]
    if 'input_image_2' in protocol['io']:
        if protocol['io']['input_image_2'] is not None:
            options['input_image_paths'].append(protocol['io']['input_image_2'])

    app = DMRIPrepApp(options['config_dir'])
    app.run(options)


def get_args():
    version = info['dmriprep']['version']
    logger("VERSION : {}".format(str(version)))
    config_dir=Path.home().joinpath('.niral-dti').resolve()
    # ## read template
    module_help_str=None
    if config_dir.exists() and config_dir.joinpath('config.yml').exists() and config_dir.joinpath('environment.yml').exists():
        config,environment = load_configurations(str(config_dir))
        template_path=config_dir.joinpath(config['protocol_template_path'])
        template=yaml.safe_load(open(template_path,'r'))
        available_modules=template['options']['execution']['pipeline']['candidates']
        available_modules_list=["{}".format(x['value'])  for x in available_modules if x['description']!="Not implemented"]
        module_help_str="Avaliable Modules := \n" + " , ".join(available_modules_list)
    uid, ts = common.get_uuid(), common.get_timestamp()

    ### Argument parsers

    parser=argparse.ArgumentParser(prog="dmriprep",
                                   formatter_class=RawTextHelpFormatter,
                                   description="dmriprep is a tool that performs quality control over diffusion weighted images. Quality control is very essential preprocess in DTI research, in which the bad gradients with artifacts are to be excluded or corrected by using various computational methods. The software and library provides a module based package with which users can make his own QC pipeline as well as new pipeline modules.",
                                   epilog="Written by SK Park (sangkyoon_park@med.unc.edu) , Johanna Dubos (johannadubos32@gmail.com) , Neuro Image Research and Analysis Laboratories, University of North Carolina @ Chapel Hill , United States, 2021")
    subparsers=parser.add_subparsers(help="Commands")
    
    ## init command
    parser_init=subparsers.add_parser('init',help='Initialize configurations')
    parser_init.set_defaults(func=command_init)

    ## add new module
    parser_new_module=subparsers.add_parser('add-module', help='Add new module to user module directory')
    parser_new_module.add_argument('name', help="Module name")
    parser_new_module.add_argument('-b','--base-module', help="Fork from an existing module with new name", default=None, required=False)
    parser_new_module.add_argument('-e','--edit', help="Run vi editor after generating module", default=False, action="store_true")
    parser_new_module.set_defaults(func=command_add_module)

    ## remove user module 
    parser_remove_module=subparsers.add_parser('remove-module', help='Remove a user module from user module directory')
    parser_remove_module.add_argument('name', help="Module name")
    parser_remove_module.set_defaults(func=command_remove_module)

    ## generate-default-protocols
    parser_make_protocols=subparsers.add_parser('make-protocols',help='Generate default protocols',epilog=module_help_str)
    parser_make_protocols.add_argument('-i','--input-images',help='Input image paths',type=str,nargs='+',required=True)
    parser_make_protocols.add_argument('-g','--global-variables',help='Global Variables',type=str,nargs='*',required=False)
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
    parser_run.add_argument('-g','--global-variables',help='Global Variables',type=str,nargs='*',required=False)
    parser_run.add_argument('-o','--output-dir',help="Output directory",type=str,required=True)
    parser_run.add_argument('--output-file-base', help="Output filename base", type=str, required=False)
    parser_run.add_argument('-t','--num-threads',help="Number of threads to use",default=1,type=int,required=False)
    parser_run.add_argument('--no-output-image',help="No output Qced file will be generated",default=False,action='store_true')
    parser_run.add_argument('-b','--b0-threshold',metavar='BASELINE_THRESHOLD',help='b0 threshold value, default=10',default=10,type=float)
    parser_run.add_argument('-f','--output-format',metavar='OUTPUT FORMAT',default=None,help='OUTPUT format, if not specified, same format will be used for output  (NRRD | NIFTI)',type=str)
    run_exclusive_group=parser_run.add_mutually_exclusive_group()
    run_exclusive_group.add_argument('-p','--protocols',metavar="PROTOCOLS_FILE" ,help='Protocol file path', type=str)
    run_exclusive_group.add_argument('-d','--default-protocols',metavar="MODULE",help='Use default protocols (optional : sequence of modules, Example : -d DIFFUSION_Check SLICE_Check)',default=None,nargs='*')
    parser_run.set_defaults(func=command_run)

    ## run-dir command
    parser_run_dir=subparsers.add_parser('run-dir',help='Run pipeline with directory',epilog=module_help_str)
    parser_run_dir.add_argument('-g','--global-variables',help='Global Variables',type=str,nargs='*',required=False)
    parser_run_dir.add_argument('output_dir',help="Output directory",type=str)
    parser_run_dir.set_defaults(func=command_run_dir)


    ## log related
    parser.add_argument('--config-dir',help='Configuration directory',default=str(config_dir))
    parser.add_argument('--log',help='log file',default=str(config_dir.joinpath('log.txt')))
    parser.add_argument('--execution-id',help='execution id',default=uid,type=str)
    parser.add_argument('--no-log-timestamp',help='Remove timestamp in the log', default=False, action="store_true")
    parser.add_argument('--no-verbosity',help='Do not show any logs in the terminal', default=False, action="store_true")
    parser.add_argument('-v','--version', help="Show version", default=False,action="store_true")
    parser.add_argument('--tools-dir', help="Initialize with specific tool directory", default=None)
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
    os.environ['ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS'] = str(args.num_threads) ## for ANTS threading

import dtiplayground.dmri.preprocessing
import dtiplayground.dmri.preprocessing.modules
import dtiplayground.dmri.preprocessing.protocols

if __name__=='__main__':
    try:
        common.logger.setTimestamp(True)
        result=args.func(args)
        exit(0)
    except Exception as e:
        common.logger.setVerbosity(True)
        msg=traceback.format_exc()
        logger(msg,color.ERROR)
        exit(-1)
    finally:
        pass


