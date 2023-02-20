#!python

import os
import sys
import argparse
from argparse import RawTextHelpFormatter
import traceback
from pathlib import Path 
import yaml 
sys.path.append(Path(__file__).parent.parent.__str__())
### for dev
from argparse import RawTextHelpFormatter
import dtiplayground.dmri.atlasbuilder.utils as utils 
from dtiplayground.dmri.atlasbuilder import AtlasBuilder 
import dtiplayground.dmri.common as common

from dtiplayground.config import INFO as info
from dtiplayground.dmri.atlasbuilder.app import DMRIAtlasBuilderApp

logger=common.logger.write 
color= common.Color


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
    app = DMRIAtlasBuilderApp(options['config_dir'])
    return app.initialize(options)

def build_atlas(args):
    params_dir = args.params_dir

    if params_dir is None:
        options={
            "output_dir" : args.output_dir,
            "config_dir" : args.config_dir,
            "hbuild_path" : args.hbuild,
            "config_path" : args.config,
            "greedy_path" : args.greedy
        }
        app = DMRIAtlasBuilderApp(options['config_dir'])
        app.run(options)        
    else:
        build_dir = Path(params_dir)
        output_dir = args.output_dir
        config_dir = args.config_dir
        hbuild_path = build_dir.joinpath('common/h-build.json').__str__()
        config_path = build_dir.joinpath('common/config.json').__str__()
        greedy_path = build_dir.joinpath('common/greedy.json').__str__()
        options={
            "output_dir" : output_dir,
            "config_dir" : config_dir,
            "hbuild_path" : hbuild_path,
            "config_path" : config_path,
            "greedy_path" : greedy_path
        }
        app = DMRIAtlasBuilderApp(options['config_dir'])
        app.run(options)        


def build_atlas_dir(args):
    build_dir = Path(args.build_dir)
    output_dir = build_dir.__str__()
    config_dir = args.config_dir
    hbuild_path = build_dir.joinpath('common/h-build.json').__str__()
    config_path = build_dir.joinpath('common/config.json').__str__()
    greedy_path = build_dir.joinpath('common/greedy.json').__str__()
    options={
        "output_dir" : output_dir,
        "config_dir" : config_dir,
        "hbuild_path" : hbuild_path,
        "config_path" : config_path,
        "greedy_path" : greedy_path
    }
    app = DMRIAtlasBuilderApp(options['config_dir'])
    app.run(options)


def get_args():
    version = info['dmriatlas']['version']
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

    parser=argparse.ArgumentParser(prog="dmriatlas",
                                   formatter_class=RawTextHelpFormatter,
                                   description="dmriatlas is a tool to make DTI Atlas.",
                                   epilog="Written by SK Park (sangkyoon_park@med.unc.edu)  ,Neuro Image Research and Analysis Laboratories, University of North Carolina @ Chapel Hill , United States, 2021")
    subparsers=parser.add_subparsers(help="Commands")

    ## init command
    parser_init=subparsers.add_parser('init',help='Initialize configurations')
    parser_init.set_defaults(func=command_init)
    
    ## build command
    parser_build=subparsers.add_parser('build',help='Build Atlas')
    parser_build.add_argument('-o','--output-dir', help='Output directory',required=True,type=str)
    parser_build_param_dir= parser_build.add_argument_group('from-dir')
    parser_build_param_dir.add_argument('-p','--params-dir', help='Parameter directory', default=None, type=str)
    parser_build_param = parser_build.add_argument_group('from-files')
    parser_build_param.add_argument('-c','--config',help='configuration file',default='config.yml',type=str)
    parser_build_param.add_argument('-b','--hbuild',help='hierarchical build file', default='h-build.yml', type=str)
    parser_build_param.add_argument('-g','--greedy',help='Greedy atlas parameter xml file', default="greedy.xml", type=str)
    parser_build.set_defaults(func=build_atlas)

    ## build dir command
    parser_build_dir=subparsers.add_parser('build-dir',help='Build Atlas with parameterized directory')
    parser_build_dir.add_argument('build_dir', help='Build directory having parameters',type=str)
    parser_build_dir.set_defaults(func=build_atlas_dir)

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

