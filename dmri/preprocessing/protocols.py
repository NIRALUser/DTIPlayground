
import dmri.preprocessing as prep
import dmri.preprocessing.dwi as dwi

import yaml,sys,traceback,time
from pathlib import Path

logger=prep.logger.write

def _load_protocol(filename):
    return yaml.safe_load(open(filename,'r'))

def _generate_exec_seqeunce(pipeline,image_paths:list,output_dir,modules): ## generate sequence using uuid to avoid the issue from redundant module use
    seq=[]
    after_multi_input=False
    for idx,parr in enumerate(pipeline):
        module_name, options=parr 
        is_multi_input='multi_input' in modules[module_name]['template']['process_attributes']
        if is_multi_input or after_multi_input:
            uid=prep.get_uuid()
            execution={
                "order": idx,
                "id":uid,
                "multi_input":True,
                "module_name":module_name,
                "options": options,
                "image_path": Path(output_dir).joinpath('consolidated').__str__(),
                "output_base": Path(output_dir).joinpath('consolidated').__str__(),
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
        module_output_dir=Path(output_dir).joinpath(Path(image_path).stem).joinpath("{:02d}_{}".format(order,m))
        #module_output_dir.mkdir(parents=True,exist_ok=True)
        module_output_dirs[uid]=str(module_output_dir)
    return module_output_dirs

def default_pipeline_options():
    return {
                 "options":{
                    "overwrite":False, # if result.yml exists and overwrite is false, module skips overall computation except for postProcess
                    "recompute":False,
                    "write_image":False # unless module is forced to write (such as BASELINE_Average, or correcting ones)
                    }, 
                 "protocol" :{}
            }

class Protocols:
    def __init__(self,modules=None,*args,**kwargs):
        self.image_paths=[]
        self.protocol_filename=None
        self.rawdata=None
        self.pipeline=None
        self.io={}
        self.version=None

        #Image data 
        self.images=[]
        self.image_cache={} # cache for the previous results

        #Execution variables
        self.template_filename=Path(__file__).parent.joinpath("templates/protocol_template.yml")
        self.modules=modules
        self.previous_process=None #this is to ensure to access previous results (image and so on)
        self.software_info=None # binary path of softwares (such as fsl)
        self.num_threads=4 # number of threads to use 

        #output
        self.result_history={}
        self.output_dir=None

        self.setSoftwareInfo()

    def loadImage(self, image_paths,b0_threshold=10):
        self.image_paths=list(map(lambda x:str(Path(x).absolute()),image_paths))
        for ip in self.image_paths:
            logger("Loading original image : {}".format(str(ip)),prep.Color.PROCESS)
            img=dwi.DWI(str(ip))
            self.result_history[ip]=[{"output":{"image_path": str(Path(ip).absolute()),
                                             "image_object" : id(img)}}]
            img.setB0Threshold(b0_threshold)
            img.getGradients()
            self.images.append(img)

    def setOutputDirectory(self, output_dir=None):
        if output_dir is None:
            self.output_dir=Path(self.getImagePath()).parent
        else:
            self.output_dir=str(Path(output_dir).absolute())
        self.io['output_directory']=str(self.output_dir)

    def setSoftwareInfo(self, paths:object=None):
        softwares=None
        if paths is None:
            spaths=['~/.niral-dti/dmriprep/software_paths.yml',Path(__file__).parent.parent.joinpath('common/data/software_paths.yml')]
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
            self.protocol_filename=filename
            return True
        except Exception as e:
            logger("Exception occurred : {}".format(str(e)))
            return False

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

    def makeDefaultProtocols(self,pipeline=None,template=None):
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
        if pipeline is not None:
            self.pipeline=self.furnishPipeline(pipeline)
        else:
            self.pipeline=self.furnishPipeline(template['options']['execution']['pipeline']['default_value'])
        logger("Default protocols are generated.",prep.Color.OK)

    def furnishPipeline(self,pipeline):
        self.checkImage()
        new_pipeline=[]
        for idx,parr in enumerate(pipeline):
            mod_name = None
            if not isinstance(parr, list):
                mod_name = parr
            else:
                mod_name , _ = parr
            default_options=default_pipeline_options()
            default_protocol=getattr(self.modules[mod_name]['module'],mod_name)().generateDefaultProtocol(self.images[0])
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

    @prep.measure_time
    def runPipeline(self):
        try:
            self.checkRunnable()
            self.processes_history=[]
            execution_sequence = _generate_exec_seqeunce(self.pipeline,self.image_paths,self.output_dir,self.modules)
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
                    "software_info": self.getSoftwareInfo()
                 }
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
                m=getattr(self.modules[p]['module'], p)()
                m.setOptionsAndProtocol(options)
                logger(yaml.dump(m.getTemplate()['process_attributes']),prep.Color.DEV)
                logger(yaml.dump(m.getOptions()),prep.Color.DEV)
                logger(yaml.dump(m.getProtocol()),prep.Color.DEV)

                m.initialize(self.result_history,image_path,output_dir=output_dir_map[uid])
                success=False
                resultfile_path=Path(output_dir_map[uid]).joinpath('result.yml')

                ### if result file is exist, just run post process and continue with previous information


                if resultfile_path.exists() and not m.getOptions()['overwrite']:
                    result_temp=yaml.safe_load(open(resultfile_path,'r'))
                    logger("Result file exists, just post-processing ...",prep.Color.INFO+prep.Color.BOLD)
                    m.postProcess(result_temp)
                    success=True
                else: # in case overwriting or there is no result.yml file
                    success=m.run(opts)
                if not success:
                    logger("[ERROR] Process failed in {}".format(p),prep.Color.ERROR) 
                    raise Exception("Process failed in {}".format(p))
                self.previous_process=m  #this is for the image id reference
                self.result_history[image_path] =m.getResultHistory()
                self.image_cache[image_path]=m.image 
                et=time.time()-bt
                self.result_history[image_path][-1]['processing_time']=et
                logger("[{}] Processed time : {:.2f}s".format(p,et),prep.Color.DEV)
                if save: ### for the last, dump image and informations
                    ## Save final Qced image
                    logger("Preparing final output ... ",prep.Color.PROCESS)
                    stem=Path(output_base).name.split('.')[0]+"_QCed"
                    ext='.nii.gz'
                    if m.image.image_type=='nrrd' : ext='.nrrd'
                    final_filename=Path(self.output_dir).joinpath(stem).__str__()+ext
                    final_gradients_filename=Path(self.output_dir).joinpath(Path(output_base).stem).joinpath('output_gradients.yml').__str__()
                    final_information_filename=Path(self.output_dir).joinpath(Path(output_base).stem).joinpath('output_image_information.yml').__str__()
                    
                    if not Path(final_filename).exists() or idx-1==len(execution_sequence):
                        m.image.writeImage(final_filename,dest_type=m.image.image_type,dtype='short')
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

