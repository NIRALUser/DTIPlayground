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
        "overwrite" : args.overwrite,
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
        "overwrite" : args.overwrite,
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
    options['output_file_base'] = protocol['io'].get('output_filename_base')
    options['input_image_paths'] = [protocol['io']['input_image_1']]
    if 'input_image_2' in protocol['io']:
        if protocol['io']['input_image_2'] is not None:
            options['input_image_paths'].append(protocol['io']['input_image_2'])

    app = DMRIPrepApp(options['config_dir'])
    app.run(options)



def _batch_settings(args):
    return {'config_dir': os.path.abspath(args.config_dir), 'command': batch_module().dmriprep_command()}

def batch_module():
    import dtiplayground.dmri.preprocessing.batch as batch
    return batch

def _print_plan(batch, out, datasets, skipped, notes):
    by_protocol = {}
    for d in datasets:
        signatures = tuple(batch.image_signature(i) for i in d['images'])
        by_protocol.setdefault(d['protocol'], {}).setdefault(signatures, []).append(d['id'])
    logger("{} dataset(s), {} skipped run(s); batch folder {}".format(len(datasets), len(skipped), batch.batch_dir(out)),color.INFO)
    for protocol, groups in by_protocol.items():
        logger("Protocol {} : {} dataset(s)".format(protocol, sum(len(v) for v in groups.values())),color.INFO)
        for signatures, ids in groups.items():
            logger("    {} x [{}]".format(len(ids), ' + '.join(signatures)),color.INFO)
            for i in ids[:3]:
                logger("        {}".format(i))
            if len(ids) > 3:
                logger("        ... ({} more)".format(len(ids)-3))
        if len(groups) > 1:
            logger("    WARNING: the datasets of this protocol have {} different acquisitions".format(len(groups)),color.WARNING)
    for name, reason in skipped:
        logger("Skipped {} : {}".format(name, reason),color.WARNING)
    for n in notes:
        logger(n,color.WARNING)

def _execute_batch(args, batch, out):
    selected, running = batch.select_datasets(out, only=args.only, rerun=args.rerun)
    if running:
        logger("{} dataset(s) are running in another process and are left out: {}".format(len(running), ', '.join(d['id'] for d in running)),color.WARNING)
    if not selected:
        logger("Nothing to process (all datasets are done; --rerun processes them again)",color.OK)
        return True
    logger("{} dataset(s) to process".format(len(selected)),color.PROCESS)
    if args.slurm or args.slurm_submit:
        batch.write_slurm(out, selected, threads=args.num_threads, overwrite=args.overwrite, time_limit=args.slurm_time,
                          memory=args.slurm_mem, partition=args.slurm_partition, setup=args.slurm_setup,
                          extra=args.slurm_option, max_parallel=args.slurm_max_parallel, submit=args.slurm_submit,
                          echo=lambda m: logger(m,color.OK))
        return True
    counts = batch.run_local(out, selected, jobs=args.jobs, threads=args.num_threads, overwrite=args.overwrite,
                             echo=lambda m: logger(m,color.OK if ' done ' in m else color.ERROR))
    _, all_counts = batch.summarize(out)
    logger("Batch: {}".format(', '.join('{} {}'.format(v,k) for k,v in sorted(all_counts.items()))),color.INFO)
    if counts.get('failed'):
        logger("{} dataset(s) failed, see {} (running the same command again retries them)".format(counts['failed'], batch.batch_dir(out).joinpath('status.tsv')),color.ERROR)
        exit(1)
    return True

def _protocol_specs(args, batch, required=True):
    if args.default_protocols is not None:
        return [('*', batch.DefaultProtocol(args.default_protocols, args.b0_threshold))]
    if required and not args.protocols:
        raise Exception("A protocol is needed: -p/--protocols PROTOCOL or -d/--default-protocols [MODULE ...]")
    return batch.parse_protocol_specs(args.protocols)

def command_bids(args):
    batch = batch_module()
    out = Path(os.path.abspath(args.output_dir))
    if args.analysis_level == 'group':
        return command_batch_report_impl(batch, out)
    specs = _protocol_specs(args, batch)
    datasets, skipped, notes = batch.plan_bids(args.bids_dir, specs, os.path.abspath(args.config_dir),
                                               participants=args.participant_label, sessions=args.session_label)
    batch.generate_default_protocols(out, datasets, os.path.abspath(args.config_dir), echo=lambda m: logger(m,color.PROCESS))
    batch.write_batch(out, datasets, skipped, dict(_batch_settings(args), source='bids', bids_dir=os.path.abspath(args.bids_dir)))
    batch.write_dataset_description(out, args.bids_dir)
    _print_plan(batch, out, datasets, skipped, notes)
    if args.dry_run:
        return True
    return _execute_batch(args, batch, out)

def command_run_batch(args):
    batch = batch_module()
    out = Path(os.path.abspath(args.output_dir))
    specs = _protocol_specs(args, batch, required=False)
    datasets, skipped, notes = batch.plan_manifest(args.datasheet, specs)
    batch.generate_default_protocols(out, datasets, os.path.abspath(args.config_dir), echo=lambda m: logger(m,color.PROCESS))
    batch.write_batch(out, datasets, skipped, dict(_batch_settings(args), source='datasheet', datasheet=os.path.abspath(args.datasheet)))
    _print_plan(batch, out, datasets, skipped, notes)
    if args.dry_run:
        return True
    return _execute_batch(args, batch, out)

def command_batch_task(args):
    batch = batch_module()
    code = batch.run_task(args.output_dir, args.id, args.config_dir, threads=args.num_threads, overwrite=args.overwrite)
    if code:
        exit(code)
    return True

def command_batch_status(args):
    batch = batch_module()
    rows, counts = batch.summarize(Path(os.path.abspath(args.output_dir)))
    for r in rows:
        if args.all or r['state'] != 'done':
            logger("{:<12} {}  {}".format(r['state'], r['id'], r['error'] or ''))
    logger("{} dataset(s): {}".format(len(rows), ', '.join('{} {}'.format(v,k) for k,v in sorted(counts.items()))),color.INFO)
    return True

def command_batch_report(args):
    return command_batch_report_impl(batch_module(), Path(os.path.abspath(args.output_dir)))

def command_batch_report_impl(batch, out):
    import dtiplayground.dmri.preprocessing.batch_report as batch_report
    batch_report.write_report(out, echo=lambda m: logger(m,color.OK))
    return True

def _add_batch_execution_arguments(p):
    p.add_argument('-t','--num-threads',help="Threads per dataset (default: num_threads in the protocol)",default=None,type=int)
    p.add_argument('-j','--jobs',help="Datasets processed at the same time (local execution, default 1)",default=1,type=int)
    p.add_argument('--dry-run',help="Write the batch folder and show the datasets, but don't process them",default=False,action='store_true')
    p.add_argument('--only',metavar='ID',help="Process only these dataset ids",nargs='+',default=None)
    p.add_argument('--rerun',help="Process also the datasets that are done (only modules whose settings changed are recomputed, unless --overwrite)",default=False,action='store_true')
    p.add_argument('--overwrite',help="Recompute all modules of the processed datasets",default=False,action='store_true')
    g=p.add_argument_group('SLURM (cluster) execution')
    g.add_argument('--slurm',help="Write a SLURM job array script (one task per dataset) instead of running locally",default=False,action='store_true')
    g.add_argument('--slurm-submit',help="Write the SLURM script and submit it with sbatch",default=False,action='store_true')
    g.add_argument('--slurm-time',help="Time limit per dataset (default 24:00:00)",default='24:00:00')
    g.add_argument('--slurm-mem',help="Memory per dataset (default 16G)",default='16G')
    g.add_argument('--slurm-partition',help="SLURM partition",default=None)
    g.add_argument('--slurm-max-parallel',help="Maximum number of tasks running at the same time",default=None,type=int)
    g.add_argument('--slurm-setup',help="Shell line run before dmriprep in each task (e.g. 'module load fsl; conda activate env')",default=None)
    g.add_argument('--slurm-option',metavar='OPTION',help="Additional #SBATCH option (e.g. --slurm-option=--gres=gpu:1)",action='append',default=None)

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
    parser_run.add_argument('-t','--num-threads',help="Number of threads to use (default: num_threads in the protocol, 1 if not set)",default=None,type=int,required=False)
    parser_run.add_argument('--no-output-image',help="No output Qced file will be generated",default=False,action='store_true')
    parser_run.add_argument('--overwrite',help="Recompute all modules, also those with a result from a previous run in the output directory (otherwise only modules whose settings changed are recomputed)",default=False,action='store_true')
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
    parser_run_dir.add_argument('--overwrite',help="Recompute all modules, also those with a result from a previous run",default=False,action='store_true')
    parser_run_dir.set_defaults(func=command_run_dir)



    ## batch processing
    parser_bids=subparsers.add_parser('bids',help='Process the DWIs of a BIDS dataset (BIDS-App interface)',epilog=module_help_str,formatter_class=RawTextHelpFormatter,
        description="participant: processes every DWI run of the BIDS dataset (or the pairs of runs with opposite phase encoding\n"
                    "when the protocol needs two images, e.g. SUSCEPTIBILITY_Correct), with the output of each dataset in\n"
                    "<output_dir>/sub-<label>/[ses-<label>/]dwi/<dataset id>/. Running it again processes only the datasets that\n"
                    "are not done. group: writes the QC table of the processed datasets and a datasheet for dmrifiberprofile.")
    parser_bids.add_argument('bids_dir',help="BIDS dataset folder")
    parser_bids.add_argument('output_dir',help="Output folder (BIDS derivatives)")
    parser_bids.add_argument('analysis_level',choices=['participant','group'],help="participant: process the datasets; group: cohort QC table")
    bids_protocols=parser_bids.add_mutually_exclusive_group()
    bids_protocols.add_argument('-p','--protocols',metavar='[PATTERN=]PROTOCOL',nargs='+',default=None,
        help="Protocol file, or protocols per acquisition as PATTERN=protocol.yml (shell pattern on the dataset or\nrun name, e.g. '*acq-dir79*=dir79.yml'); the first match is used")
    bids_protocols.add_argument('-d','--default-protocols',metavar='MODULE',nargs='*',default=None,
        help="Default protocol with these modules (none: the default pipeline of the template), generated for each\nacquisition (batch/default_protocols/)")
    parser_bids.add_argument('-b','--b0-threshold',metavar='BASELINE_THRESHOLD',help='b0 threshold of the default protocols (-d), default=10',default=10,type=float)
    parser_bids.add_argument('--participant-label',metavar='LABEL',nargs='+',default=None,help="Only these subjects (with or without sub-)")
    parser_bids.add_argument('--session-label',metavar='LABEL',nargs='+',default=None,help="Only these sessions (with or without ses-)")
    _add_batch_execution_arguments(parser_bids)
    parser_bids.set_defaults(func=command_bids)

    parser_run_batch=subparsers.add_parser('run-batch',help='Process the datasets listed in a datasheet',epilog=module_help_str,formatter_class=RawTextHelpFormatter,
        description="Datasheet (TSV or CSV) columns: id, image_1 (required), image_2 (second image, e.g. opposite phase encoding),\n"
                    "protocol, output_dir (relative to the output folder, default: id), output_file_base, subject, session,\n"
                    "overrides (JSON {module: {parameter: value}}). Relative paths are relative to the datasheet.")
    parser_run_batch.add_argument('-m','--datasheet',help="Datasheet (TSV or CSV)",required=True)
    parser_run_batch.add_argument('-o','--output-dir',help="Output folder",required=True)
    batch_protocols=parser_run_batch.add_mutually_exclusive_group()
    batch_protocols.add_argument('-p','--protocols',metavar='[PATTERN=]PROTOCOL',nargs='+',default=None,help="Protocol for the rows without a protocol column (PATTERN matches the id)")
    batch_protocols.add_argument('-d','--default-protocols',metavar='MODULE',nargs='*',default=None,
        help="Default protocol with these modules (none: the default pipeline of the template) for the rows without a\nprotocol column, generated for each acquisition (batch/default_protocols/)")
    parser_run_batch.add_argument('-b','--b0-threshold',metavar='BASELINE_THRESHOLD',help='b0 threshold of the default protocols (-d), default=10',default=10,type=float)
    _add_batch_execution_arguments(parser_run_batch)
    parser_run_batch.set_defaults(func=command_run_batch)

    parser_batch_task=subparsers.add_parser('batch-task',help='Process one dataset of a batch (used by the local and SLURM batch execution)')
    parser_batch_task.add_argument('output_dir',help="Output folder of the batch")
    parser_batch_task.add_argument('id',help="Dataset id")
    parser_batch_task.add_argument('-t','--num-threads',default=None,type=int,help="Number of threads")
    parser_batch_task.add_argument('--overwrite',default=False,action='store_true',help="Recompute all modules")
    parser_batch_task.set_defaults(func=command_batch_task)

    parser_batch_status=subparsers.add_parser('batch-status',help='State of the datasets of a batch')
    parser_batch_status.add_argument('output_dir',help="Output folder of the batch")
    parser_batch_status.add_argument('--all',default=False,action='store_true',help="List also the datasets that are done")
    parser_batch_status.set_defaults(func=command_batch_status)

    parser_batch_report=subparsers.add_parser('batch-report',help='QC table of the datasets of a batch and datasheet for dmrifiberprofile')
    parser_batch_report.add_argument('output_dir',help="Output folder of the batch")
    parser_batch_report.set_defaults(func=command_batch_report)

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
num_threads=getattr(args,'num_threads',None)
if num_threads is None and isinstance(getattr(args,'protocols',None),str): ## no -t given, use the protocol's value (dmriprep run)
    num_threads=yaml.safe_load(open(args.protocols,'r'))['io'].get('num_threads')
if num_threads is None and getattr(args,'func',None) is command_batch_task: ## the protocol of the dataset
    _fn=Path(args.output_dir).joinpath('batch','protocols',args.id+'.yml')
    if _fn.exists():
        num_threads=yaml.safe_load(open(_fn,'r'))['io'].get('num_threads')
        args.num_threads=num_threads
if num_threads is not None:
    os.environ['OMP_NUM_THREADS']=str(num_threads) ## this should go before loading any dipy function. 
    os.environ['ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS'] = str(num_threads) ## for ANTS threading

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


