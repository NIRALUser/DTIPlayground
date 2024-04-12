from dtiplayground.dmri.common.pipeline import *
from dtiplayground.dmri.common.pipeline import _num
# from dtiplayground.dmri.common.pipeline import _generate_exec_sequence, _generate_output_directories_mapping

def _generate_exec_sequence(pipeline,file_paths:list,output_dir,modules, io_options): ## generate sequence using uuid to avoid the issue from redundant module use
    seq=[]
    after_multi_input=False
    print(io_options)
    for idx,parr in enumerate(pipeline):
        module_name, options=parr
        is_multi_input='multi_input' in modules[module_name]['template']['process_attributes']
        is_single_input_allowed="single_input" in modules[module_name]['template']['process_attributes']
        if (is_multi_input and (len(file_paths)<2)):
            if(not is_single_input_allowed):
                raise Exception("Multi_input module needs at least 2 input files. in {}".format(module_name))
        if ((is_multi_input and (len(file_paths)>=2)) or after_multi_input) :
            uid=common.get_uuid()
            execution={
                "order": idx,
                "id":uid,
                "multi_input":True,
                "module_name":module_name,
                "options": options,
                "file_path": Path(output_dir).joinpath(io_options['output_filename_base']).__str__(),
                "output_base": Path(output_dir).joinpath(io_options['output_filename_base']).__str__(),
               "save": idx+1==len(pipeline) ## is it the final stage? (to save the final output)
            }
            ## save previous results
            if idx>0 and not after_multi_input:
                for idx2,ip in enumerate(file_paths):
                    seq[-idx2-1]['save']=True
            seq.append(execution)
            after_multi_input=True
        else:
            for fp in file_paths:
                uid=common.get_uuid()
                execution={
                    "order": idx,
                    "id":uid,
                    "multi_input":False,
                    "module_name":module_name,
                    "options": options,
                    "file_path":fp,
                    "output_base": fp,
                    "save": idx+1==len(pipeline)  ## is it the final stage? (to save the final output)
                }
                seq.append(execution)
    return seq


def _generate_output_directories_mapping(output_dir,exec_sequence): ## map exec sequence uuid to output directory
    # Path(output_dir).mkdir(parents=True,exist_ok=True)
    module_output_dirs={}
    for idx,execution in enumerate(exec_sequence):
        # uid, m,options=parr
        uid=execution['id']
        m=execution['module_name']
        options=execution['options']
        file_path=execution['file_path']
        order=execution['order']
        module_output_dir=Path(output_dir).joinpath(Path(file_path).stem.split('.')[0]).joinpath("{:02d}_{}".format(order,m))
        module_output_dirs[uid]=str(module_output_dir)
    return module_output_dirs

def _load_protocol(filename):
    res = yaml.safe_load(open(filename,'r'))
    res['io'].setdefault('num_threads',1)
    res['io']['num_threads']=int(res['io']['num_threads'])
    for idx,p in enumerate(res['pipeline']):
        module_name, parameter = p
        protocol = parameter['protocol']
        for k, v in protocol.items():
            res['pipeline'][idx][1]['protocol'][k] = _num(v)
    return res

class Protocols(Pipeline):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        global logger
        logger = self.logger.write
    def loadModules(self,pipeline:list,user_module_paths:list, **options):
        mod_names=[x for x in pipeline]
        system_module_paths = [Path(__file__).resolve().parent.joinpath('modules')]
        modules=module._load_modules(system_module_paths = system_module_paths, user_module_paths=user_module_paths,module_names=mod_names, **options)
        modules=module.check_module_validity(modules, self.environment, self.config_dir)
        self.modules=modules

        return self.modules
    def checkRunnable(self):
        logger("Checking runability ...",common.Color.PROCESS)
        self.checkDatasheet()
        self.checkPipeline()
        self.checkDependencies()

    def checkDatasheet(self):
         if len(self.file_paths) == 0:
            logger("[ERROR] Datasheet is not loaded.",common.Color.ERROR)
            raise Exception("Datasheet is not set")
    def checkPipeline(self):
        if self.pipeline is None:
            logger("[ERROR] Protocols are not set.",common.Color.ERROR)
            raise Exception("Pipe line error")



    def checkDependencies(self):
        for parr in self.pipeline:
            p, options = parr
            if not self.modules[p]['valid']:
                msg=self.modules[p]['validity_message']
                logger("[ERROR] Dependency is not met for the module : {} , {}".format(p,msg),common.Color.WARNING)
                raise Exception("Module {} is not configured correctly.".format(p))

    def loadProtocols(self, filename):
        try:
            self.rawdata = _load_protocol(filename)
            self.version = self.rawdata['version']
            self.pipeline = self.furnishPipeline(self.rawdata['pipeline'])
            self.io = self.rawdata['io']
            self.protocol_filename = filename
            return True
        except Exception as e:
            logger("Exception occurred : {}".format(str(e)))
            traceback.print_exc()
            return False

    def makeDefaultProtocols(self,pipeline=None,template=None,options={}):
        self.checkDatasheet()
        logger("Default protocols are being generated using image information",common.Color.PROCESS)
        if template==None:
            template=yaml.safe_load(open(self.template_filename,'r'))

        ### generate default protocols
        self.io={}
        self.version=template['version']
        for k,elm in template['options']['io'].items():
            self.io[k]=elm['default_value']
        if self.file_paths is not None:
            self.io['input_datasheet']=self.file_paths[0]
        if self.output_dir is not None:
            self.io['output_directory']=str(self.output_dir)
        if pipeline is not None:
            self.pipeline=self.furnishPipeline(pipeline)
        else:
            self.pipeline=self.furnishPipeline(template['options']['execution']['pipeline']['default_value'])
        logger("Default protocols are generated.",common.Color.OK)
     # Override default runPipeline method with fiberprofile specific functionality
    @common.measure_time
    def runPipeline(self,options={}): ## default is QC module (to be abstracted)
        try:
            if 'execution_id' in options: logger("Execution ID : {}".format(options['execution_id']))
            logger(str(options),common.Color.DEV)
            self.checkRunnable()
            self.processes_history=[]
            print(Path(self.file_paths[0]).stem)
            self.io_options['output_filename_base']=Path(self.file_paths[0]).stem

            if 'output_file_base' in options:
                if options['output_file_base'] is not None:
                    self.io_options['output_filename_base']=options['output_file_base']

            execution_sequence = _generate_exec_sequence(self.pipeline,
                                                         self.file_paths,
                                                         self.output_dir,
                                                         self.modules,
                                                         self.io_options)

            Path(self.output_dir).mkdir(parents=True,exist_ok=True)
            output_dir_map=_generate_output_directories_mapping(self.output_dir,execution_sequence)
            protocol_filename=Path(self.output_dir).joinpath('protocols.yml').__str__()
            logger("Writing protocol file to : {}".format(protocol_filename),common.Color.PROCESS)
            self.writeProtocols(protocol_filename)
            ## print pipeline
            logger("PIPELINE",common.Color.INFO)
            logger(yaml.safe_dump(self.io),common.Color.DEV)
            logger(yaml.safe_dump(self.pipeline),common.Color.DEV)
            ## run pipeline
            opts={
                    "software_info": self.getSoftwareInfo(),
                    "global_variables" : self.global_variables,
                    **options
                 }
            forced_overwrite=False
            self.global_variables.update(self.loadGlobalVariables())
            for idx,execution in enumerate(execution_sequence):
                # uid, p, options=parr
                uid=execution['id']
                p=execution['module_name']
                options=execution['options']
                file_path=execution['file_path']
                output_base=execution['output_base']
                save=execution['save']

                bt=time.time()
                logger("-----------------------------------------------",common.Color.BOLD)
                logger("Processing [{0}/{1}] : {2}".format(idx+1,len(execution_sequence),p),common.Color.BOLD)
                logger("Filename: {}".format(file_path),common.Color.BOLD)
                logger("-----------------------------------------------",common.Color.BOLD)
                Path(output_dir_map[uid]).mkdir(parents=True,exist_ok=True)
                logger("Output directory : {}\n".format(str(output_dir_map[uid])),common.Color.DEV)
                m=getattr(self.modules[p]['module'], p)(**opts)
                m.setOptionsAndProtocol(options)
                logger(yaml.safe_dump(m.getTemplate()['process_attributes']),common.Color.DEV)
                logger(yaml.safe_dump(m.getOptions()),common.Color.DEV)
                logger(yaml.safe_dump(m.getProtocol()),common.Color.DEV)
                if m.getOptions()['skip']:
                    forced_overwrite=True
                    logger("SKIPPING THIS",common.Color.INFO)
                    continue

                m.initialize(self.result_history,file_path,output_dir=output_dir_map[uid])
                success=False
                resultfile_path=Path(output_dir_map[uid]).joinpath('result.yml')

                ### if result file is exist, just run post process and continue with previous information

                if m.getOptions()['overwrite']:
                    forced_overwrite=True

                if resultfile_path.exists() and not m.getOptions()['overwrite'] and not forced_overwrite:
                    result_temp=yaml.safe_load(open(resultfile_path,'r'))
                    logger("Result file exists, just post-processing ...",common.Color.INFO+common.Color.BOLD)
                    m.postProcess(result_temp,opts)
                    success=True
                else: # in case overwriting or there is no result.yml file
                    outres=m.run(opts,global_vars=self.global_variables)
                    success=outres['success']
                if not success:
                    logger("[ERROR] Process failed in {}".format(p),common.Color.ERROR)
                    raise Exception("Process failed in {}".format(p))
                self.global_variables.update(m.getGlobalVariables())
                self.writeGlobalVariables()
                self.previous_process=m  #this is for the image id reference
                # self.result_history[image_path] =m.getResultHistory()
                # self.image_cache[image_path]=m.image
                for intermediary_file in m.getOutputFiles():
                    srcfilepath = intermediary_file['source']
                    postfix = intermediary_file['postfix']
                    output_stem = Path(output_base).name.split('.')[0]+"_{}".format(postfix)

                    ext=Path(srcfilepath).suffix
                    if ".nrrd" in srcfilepath.lower():
                        ext=".nrrd"
                    elif ".nii.gz" in srcfilepath.lower():
                        ext=".nii.gz"
                    else:
                        ext=Path(srcfilepath).suffix
                    filename="{}{}".format(output_stem,ext)
                    output_path = Path(self.output_dir).joinpath(filename)
                    logger("Saving intermediary files from {} to {}".format(srcfilepath, output_path),common.Color.PROCESS)
                    shutil.copy(srcfilepath, output_path)

                et=time.time()-bt
                self.result_history[file_path][-1]['processing_time']=et
                logger("[{}] Processed time : {:.2f}s".format(p,et),common.Color.DEV)
                if save and not self.io['no_output_image']: ### for the last, dump image and informations
                    ## Save final Qced image
                    logger("Preparing final output ... ",common.Color.PROCESS)
                    # final output stuff
            logger(yaml.safe_dump(execution_sequence),common.Color.INFO)
            return self.result_history

        except Exception as e:
            logger("Exception occurred in runPipeline {}".format(str(e)),common.Color.ERROR)
            tbstr=traceback.format_exc()
            logger(tbstr,common.Color.ERROR)
            exit(1);
        finally:
            with open(Path(self.output_dir).joinpath('result_history.yml'),'w') as f:
                yaml.safe_dump(self.result_history,f)

