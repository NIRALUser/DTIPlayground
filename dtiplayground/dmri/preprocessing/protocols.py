
import dtiplayground.dmri.preprocessing as prep
import dtiplayground.dmri.preprocessing.dwi as dwi

import shutil
import yaml,sys,traceback,time
from pathlib import Path

logger=prep.logger.write

def _load_protocol(filename):
    return yaml.safe_load(open(filename,'r'))


def load_configurations(config_dir:str):
    ## reparametrization
    home_dir=Path(config_dir)
    ## Function begins
    config_filename=home_dir.joinpath("config.yml")
    environment_filename=home_dir.joinpath("environment.yml")
    config=yaml.safe_load(open(config_filename,'r'))
    environment=yaml.safe_load(open(environment_filename,'r'))
    return config,environment

def _generate_exec_seqeunce(pipeline,image_paths:list,output_dir,modules, io_options): ## generate sequence using uuid to avoid the issue from redundant module use
    seq=[]
    after_multi_input=False
    for idx,parr in enumerate(pipeline):
        module_name, options=parr 
        is_multi_input='multi_input' in modules[module_name]['template']['process_attributes']
        is_single_input_allowed="single_input" in modules[module_name]['template']['process_attributes']
        if (is_multi_input and (len(image_paths)<2)):
            if(not is_single_input_allowed):
                raise Exception("Multi_input module needs at least 2 input images. in {}".format(module_name))
        if ((is_multi_input and (len(image_paths)>=2)) or after_multi_input) :
            uid=prep.get_uuid()
            execution={
                "order": idx,
                "id":uid,
                "multi_input":True,
                "module_name":module_name,
                "options": options,
                "image_path": Path(output_dir).joinpath(io_options['output_filename_base']).__str__(),
                "output_base": Path(output_dir).joinpath(io_options['output_filename_base']).__str__(),
               "save": idx+1==len(pipeline) ## is it the final stage? (to save the final output)
            }
            ## save previous results
            if idx>0 and not after_multi_input:
                for idx2,ip in enumerate(image_paths):
                    seq[-idx2-1]['save']=True
            #seq.append([uid]+parr+[ip])
            seq.append(execution)
            after_multi_input=True
        else:
            for ip in image_paths:
                uid=prep.get_uuid()
                execution={
                    "order": idx,
                    "id":uid,
                    "multi_input":False,
                    "module_name":module_name,
                    "options": options,
                    "image_path":ip,
                    "output_base": ip,
                    "save": idx+1==len(pipeline)  ## is it the final stage? (to save the final output)
                }
                #seq.append([uid]+parr+[ip])
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
        image_path=execution['image_path']
        order=execution['order']
        module_output_dir=Path(output_dir).joinpath(Path(image_path).stem.split('.')[0]).joinpath("{:02d}_{}".format(order,m))
        #module_output_dir.mkdir(parents=True,exist_ok=True)
        module_output_dirs[uid]=str(module_output_dir)
    return module_output_dirs

def default_pipeline_options():
    return {
                 "options":{
                    "overwrite":False, # if result.yml exists and overwrite is false, module skips overall computation except for postProcess
                    # "recompute":False,
                    "write_image":False, # unless module is forced to write (such as BASELINE_Average, or correcting ones)
                    "skip":False
                    }, 
                 "protocol" :{}
            }

class Protocols:
    def __init__(self,config_dir,modules=None,*args,**kwargs):
        self.image_paths=[]
        self.protocol_filename=None
        self.rawdata=None
        self.pipeline=None
        self.io={}
        self.io_options={}
        self.version=None
        self.config_dir=config_dir 

        #Image data 
        self.original_image_information=None
        self.original_image_format='nrrd'
        self.images=[]
        self.image_cache={} # cache for the previous results

        #Execution variables
        self.template_filename=Path(__file__).resolve().parent.joinpath("templates/protocol_template.yml")
        self.modules=modules
        self.previous_process=None #this is to ensure to access previous results (image and so on)
        self.software_info=None # binary path of softwares (such as fsl)
        self.num_threads=4 # number of threads to use 
        self.global_variables={} # global variables to track from each module (arbitrary key-value dict)
        #Module related
        self.config,self.environment=load_configurations(self.config_dir)

        #output
        self.result_history={}
        self.output_dir=None
        
        self.setSoftwareInfo()

    def loadImages(self, image_paths,b0_threshold=10):
        self.image_paths=list(map(lambda x:str(Path(x).absolute()),image_paths))
        #print(self.image_paths)
        for ip in self.image_paths:
            logger("Loading original image : {}".format(str(ip)),prep.Color.PROCESS)
            img=dwi.DWI(str(ip))
            self.result_history[ip]=[{"output":{"image_path": str(Path(ip).absolute()),
                                             "image_information": img.information,
                                             "image_object" : id(img)}}]
            img.setB0Threshold(b0_threshold)
            img.getGradients()
            self.images.append(img)
        self.original_image_information = self.images[0].information
        self.original_image_format = self.images[0].image_type

    def setOutputDirectory(self, output_dir=None):
        if output_dir is None:
            self.output_dir=Path(self.getImagePath()).parent
        else:
            self.output_dir=str(Path(output_dir).absolute())
        self.io['output_directory']=str(self.output_dir)

    def setSoftwareInfo(self, paths:object=None):
        softwares=None
        if paths is None:
            spaths=[Path(self.config_dir).joinpath('software_paths.yml'),Path(__file__).resolve().parent.parent.joinpath('common/data/software_paths.yml')]
            for p in spaths:
                if Path(p).exists():
                    softwares=yaml.safe_load(open(p,'r'))
                    self.software_info=softwares 
                    self.num_threads=softwares['parameters']['num_max_threads']
                    break 
        if softwares is None: raise Exception("Software information is required")
        return softwares is not None 

    def getSoftwareInfo(self):
        return self.software_info 

    def setNumThreads(self,nth:int):
        assert(nth>0)
        self.num_threads=nth 
        self.software_info['parameters']['num_max_threads']=nth
        self.io['num_threads']=nth  

    def getProtocols(self):
        proto={
            'version' : self.version,
            'io' : self.io,
            'pipeline': self.pipeline
        }
        return proto

    def writeProtocols(self,filename):
        self.rawdata=self.getProtocols()
        yaml.dump(self.rawdata,open(filename,'w'))


    def loadProtocols(self,filename):
        try:
            self.rawdata=_load_protocol(filename)
            self.version=self.rawdata['version']
            self.pipeline=self.furnishPipeline(self.rawdata['pipeline'])
            self.io=self.rawdata['io']
            if 'no_output_image' not in self.io:
                self.io['no_output_image']= False
            if 'output_format' not in self.io:
                self.io['output_format']=None
            if 'baseline_threshold' not in self.io:
                self.io['baseline_threshold']=10
            self.protocol_filename=filename
            return True
        except Exception as e:
            logger("Exception occurred : {}".format(str(e)))
            return False

    def loadModules(self,pipeline:list,user_module_paths:list):
        mod_names=[x for x in pipeline]
        modules=prep.modules._load_modules(user_module_paths=user_module_paths,module_names=mod_names)
        modules=prep.modules.check_module_validity(modules, self.environment, self.config_dir)
        self.modules=modules

        return self.modules 

    def setModules(self,modules):
        self.modules=modules 

    def addPipeline(self,modulename,options={},index=-1):
        opt=default_pipeline_options()
        if 'options' in options:
            opt['options'].update(options['options'])
        default_protocol=getattr(self.modules[modulename]['module'],modulename)().generateDefaultProtocol(self.images[0])
        opt['protocol'].update(default_protocol)
        if 'protocol' in options:
            opt['protocol'].update(options['protocol'])
        self.pipeline.insert(index, [modulename,opt])

    def makeDefaultProtocols(self,pipeline=None,template=None,options={}):
        self.checkImage()
        logger("Default protocols are being generated using image information",prep.Color.PROCESS)
        if template==None:
            template=yaml.safe_load(open(self.template_filename,'r'))

        ### generate default protocols
        self.io={}
        self.version=template['version']
        for k,elm in template['options']['io'].items():
            self.io[k]=elm['default_value']
        if self.output_dir is not None:
            self.io['output_directory']=str(self.output_dir)
        if 'baseline_threshold' in options:
            self.io['baseline_threshold']=options['baseline_threshold']
        self.io['output_format']=None
        if 'output_format' in options:
            self.io['output_format']=options['output_format']
        self.io['no_output_image']= False
        if 'no_output_image' in options:
            self.io['no_output_image']=options['no_output_image']

        # self.io['output_filename_base'] = getBaseFilename(self.images[0].filename)
        # if 'output_filename_base' in options:
        #     if options['output_filename_base']:
        #         self.io['output_filename_base']=options['output_filename_base']
        if pipeline is not None:
            self.pipeline=self.furnishPipeline(pipeline)
        else:
            self.pipeline=self.furnishPipeline(template['options']['execution']['pipeline']['default_value'])
        logger("Default protocols are generated.",prep.Color.OK)

    def furnishPipeline(self,pipeline):
        self.checkImage()
        module_names=[]
        for idx,parr in enumerate(pipeline):
            if not isinstance(parr, list):
                mod_name = parr
            else:
                mod_name , _ = parr
            module_names.append(mod_name)
        self.loadModules(module_names,user_module_paths=self.config['user_module_directories'])

        new_pipeline=[]
        for idx,parr in enumerate(pipeline):
            mod_name = None
            if not isinstance(parr, list):
                mod_name = parr
            else:
                mod_name , _ = parr
            default_options=default_pipeline_options()

            default_protocol=getattr(self.modules[mod_name]['module'],mod_name)(str(self.config_dir)).generateDefaultProtocol(self.images[0])
            default_options['protocol'].update(default_protocol)
            if not isinstance(parr, list):
                new_pipeline.append([parr,default_options])
            else:
                p,opt = parr 
                if "options" in opt:
                    if opt["options"]==None : opt["options"]={}
                    default_options['options'].update(opt['options'])
                if "protocol" in opt:
                    if opt["protocol"]==None : opt["protocol"]={}
                    default_options['protocol'].update(opt['protocol'])
                newopt=default_options
                new_pipeline.append([p,newopt])
        return new_pipeline 


    def checkRunnable(self):
        logger("Checking runability ...",prep.Color.PROCESS)
        self.checkImage()
        self.checkPipeline()
        self.checkDependencies()

    def checkImage(self):
         if len(self.images) ==0: 
            logger("[ERROR] Image is not loaded.",prep.Color.ERROR)
            raise Exception("Image is not set")       
    def checkPipeline(self):
        if self.pipeline is None:
            logger("[ERROR] Protocols are not set.",prep.Color.ERROR)
            raise Exception("Image is not set")
    def checkDependencies(self):
        for parr in self.pipeline:
            p, options = parr 
            if not self.modules[p]['valid']: 
                msg=self.modules[p]['validity_message']
                logger("[ERROR] Dependency is not met for the module : {} , {}".format(p,msg),prep.Color.WARNING)
                raise Exception("Module {} is not configured correctly.".format(p))    

    def getBaseFilename(self,org_filename):
        fname = Path(org_filename).stem
        potential_kwds=['ap','pa','hf','fh','si','is','lr','rl']
        potential_kwds += list(map(lambda x: x.upper(),potential_kwds))
        for kwd in potential_kwds:
            splitter="_{}".format(kwd)
            if splitter in fname:
                return fname.split(splitter)[0]
        return fname.split('.')[0]

    @prep.measure_time
    def runPipeline(self,options={}):
        try:
            if 'execution_id' in options: logger("Execution ID : {}".format(options['execution_id']))
            self.checkRunnable()
            self.processes_history=[]
            self.io_options['output_filename_base']=self.getBaseFilename(self.images[0].filename)
            if options['output_file_base']:
                self.io_options['output_filename_base']=options['output_file_base']
            execution_sequence = _generate_exec_seqeunce(self.pipeline,self.image_paths,self.output_dir,self.modules, self.io_options)
            Path(self.output_dir).mkdir(parents=True,exist_ok=True)
            output_dir_map=_generate_output_directories_mapping(self.output_dir,execution_sequence)
            protocol_filename=Path(self.output_dir).joinpath('protocols.yml').__str__()
            logger("Writing protocol file to : {}".format(protocol_filename),prep.Color.PROCESS)
            self.writeProtocols(protocol_filename)
            ## print pipeline
            logger("PIPELINE",prep.Color.INFO)
            logger(yaml.dump(self.io),prep.Color.DEV)
            logger(yaml.dump(self.pipeline),prep.Color.DEV)
            ## run pipeline
            opts={
                    "software_info": self.getSoftwareInfo(),
                    "baseline_threshold" : self.io['baseline_threshold']
                 }
            forced_overwrite=False
            for idx,execution in enumerate(execution_sequence):
                # uid, p, options=parr 
                uid=execution['id']
                p=execution['module_name']
                options=execution['options']
                image_path=execution['image_path']
                output_base=execution['output_base']
                save=execution['save']

                if image_path not in self.result_history:
                    self.result_history[image_path]=[]
                bt=time.time()
                logger("-----------------------------------------------",prep.Color.BOLD)
                logger("Processing [{0}/{1}] : {2}".format(idx+1,len(execution_sequence),p),prep.Color.BOLD)
                logger("Filename: {}".format(image_path),prep.Color.BOLD)    
                logger("-----------------------------------------------",prep.Color.BOLD)
                Path(output_dir_map[uid]).mkdir(parents=True,exist_ok=True)
                logger("Output directory : {}\n".format(str(output_dir_map[uid])),prep.Color.DEV)
                m=getattr(self.modules[p]['module'], p)(self.config_dir)
                m.setOptionsAndProtocol(options)

                logger(yaml.dump(m.getTemplate()['process_attributes']),prep.Color.DEV)
                logger(yaml.dump(m.getOptions()),prep.Color.DEV)
                logger(yaml.dump(m.getProtocol()),prep.Color.DEV)
                if m.getOptions()['skip']:
                    forced_overwrite=True 
                    logger("SKIPPING THIS",prep.Color.INFO)
                    continue

                m.initialize(self.result_history,image_path,output_dir=output_dir_map[uid])
                success=False
                resultfile_path=Path(output_dir_map[uid]).joinpath('result.yml')

                ### if result file is exist, just run post process and continue with previous information

                if m.getOptions()['overwrite']:
                    forced_overwrite=True 

                if resultfile_path.exists() and not m.getOptions()['overwrite'] and not forced_overwrite:
                    result_temp=yaml.safe_load(open(resultfile_path,'r'))
                    logger("Result file exists, just post-processing ...",prep.Color.INFO+prep.Color.BOLD)
                    m.postProcess(result_temp,opts)
                    success=True
                else: # in case overwriting or there is no result.yml file
                    outres=m.run(opts,global_vars=self.global_variables)
                    success=outres['success']
                if not success:
                    logger("[ERROR] Process failed in {}".format(p),prep.Color.ERROR) 
                    raise Exception("Process failed in {}".format(p))
                self.global_variables.update(m.getGlobalVariables())
                self.previous_process=m  #this is for the image id reference
                self.result_history[image_path] =m.getResultHistory()
                self.image_cache[image_path]=m.image 
                for intermediary_file in m.getOutputFiles():
                    srcfilepath = intermediary_file['source']
                    postfix = intermediary_file['postfix']
                    output_stem = Path(output_base).name.split('.')[0]+"_{}".format(postfix)
                    ext=".nii.gz"
                    if ".nrrd" in srcfilepath.lower():
                        ext=".nrrd"
                    filename="{}{}".format(output_stem,ext)
                    output_path = Path(self.output_dir).joinpath(filename)
                    logger("Saving intermediary files from {} to {}".format(srcfilepath, output_path),prep.Color.PROCESS)
                    shutil.copy(srcfilepath, output_path)

                et=time.time()-bt
                self.result_history[image_path][-1]['processing_time']=et                   
                logger("[{}] Processed time : {:.2f}s".format(p,et),prep.Color.DEV)
                if save and not self.io['no_output_image']: ### for the last, dump image and informations
                    ## Save final Qced image
                    logger("Preparing final output ... ",prep.Color.PROCESS)
                    stem=Path(output_base).name.split('.')[0]+"_QCed"
                    ext='.nii.gz'
                    if self.io['output_format'] is None: self.io['output_format']=self.original_image_format
                    if self.io['output_format'] =='nrrd' : ext='.nrrd'
                    final_filename=Path(self.output_dir).joinpath(stem).__str__()+ext
                    final_gradients_filename=Path(self.output_dir).joinpath(Path(output_base).stem.split('.')[0]).joinpath('output_gradients.yml').__str__()
                    final_information_filename=Path(self.output_dir).joinpath(Path(output_base).stem.split('.')[0]).joinpath('output_image_information.yml').__str__()
                    
                    if not Path(final_filename).exists() or idx+1==len(execution_sequence):
                        # m.image.writeImage(final_filename,dest_type=m.image.image_type)
                        # if 'combined_QCed' in stem:
                        #     if self.io['output_filename_base']:
                        #         stem=self.io['output_filename_base']+"_QCed"
                        #         final_filename=Path(self.output_dir).joinpath(stem).__str__()+ext
                        m.image.writeImage(final_filename,dest_type=self.io['output_format'])
                        m.image.dumpGradients(final_gradients_filename)
                        m.image.dumpInformation(final_information_filename)

            logger(yaml.dump(execution_sequence),prep.Color.INFO)
            return self.result_history

        except Exception as e:
            logger("Exception occurred in runPipeline {}".format(str(e)),prep.Color.ERROR)
            tbstr=traceback.format_exc()
            logger(tbstr,prep.Color.ERROR)
            return None
        finally:
            with open(Path(self.output_dir).joinpath('result_history.yml'),'w') as f:
                yaml.dump(self.result_history,f)

