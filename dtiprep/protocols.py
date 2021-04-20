import yaml,sys,traceback,time
import dtiprep
#import dtiprep.dwi
from dtiprep.modules import _load_modules
import dtiprep.modules 
from pathlib import Path


logger=dtiprep.logger.write

def _load_protocol(filename):
    return yaml.safe_load(open(filename,'r'))

def _generate_exec_seqeunce(pipeline): ## generate sequence using uuid to avoid the issue from redundant module use
    seq=[]
    for parr in pipeline:
        uid=dtiprep.get_uuid()
        seq.append([uid]+parr)
    return seq 


def _generate_output_directories(output_dir,exec_sequence): ## map exec sequence uuid to output directory
    Path(output_dir).mkdir(parents=True,exist_ok=True)
    module_output_dirs={}
    for idx,parr in enumerate(exec_sequence):
        uid, m,options=parr 
        module_output_dir=Path(output_dir).joinpath("{:02d}_{}".format(idx,m))
        module_output_dir.mkdir(parents=True,exist_ok=True)
        module_output_dirs[uid]=str(module_output_dir)
    return module_output_dirs

def default_pipeline_options():
    return {
                 "overwrite":False,
                 "recompute":False,
                 "write_image":False # unless module is forced to write (such as BASELINE_Average, or correcting ones)
            }

class Protocols:
    def __init__(self,modules=None,*args,**kwargs):
        self.image_path=None
        self.protocol_filename=None
        self.rawdata=None
        self.protocols=None
        self.pipeline=None
        self.io={}
        self.version=None

        #Image data 
        self.image=None

        #Execution variables
        self.template_filename=Path(__file__).parent.joinpath("templates/protocol_template.yml")
        self.modules=modules
        self.previous_process=None #this is to ensure to access previous results (image and so on)
        #output
        self.result_history=None
        self.output_path=None

    def loadImage(self, image_path):
        self.image_path=str(Path(image_path).absolute())
        logger("Loading original image : {}".format(str(self.image_path)),dtiprep.Color.PROCESS)
        self.image=dtiprep.dwi.DWI(str(self.image_path))
        self.result_history=[{"output":{"image_path": str(Path(self.image_path).absolute()),
                                         "image_object" : id(self.image)}}]

    def setOutputDirectory(self, output_dir=None):
        if output_dir is None:
            self.output_dir=Path(self.getImagePath()).parent
        else:
            self.output_dir=str(Path(output_dir).absolute())
        self.io['output_directory']=str(self.output_dir)

    def writeProtocols(self,filename):
        self.rawdata={
            'version' : self.version,
            'io' : self.io,
            'pipeline': self.pipeline,
            'protocols':self.protocols
        }
        yaml.dump(self.rawdata,open(filename,'w'))

    def loadProtocols(self,filename):
        try:
            self.rawdata=_load_protocol(filename)
            self.version=self.rawdata['version']
            self.pipeline=self.furnishPipeline(self.rawdata['pipeline'])
            self.protocols=self.rawdata['protocols']
            self.io=self.rawdata['io']
            self.protocol_filename=filename
            self.output_dir=self.io['output_directory']
            return True
        except Exception as e:
            logger("Exception occurred : {}".format(str(e)))
            return False

    def setModules(self,modules):
        self.modules=modules 

    def addPipeline(self,modulename,options={},index=-1,default_protocol=True):
        opt=default_pipeline_options()
        opt.update(options)
        if modulename not in list(map(lambda x:x[0],self.pipeline)):
            self.pipeline.insert(index, [modulename,opt])
            if default_protocol:
                self.makeDefaultProtocolForModule(modulename)

    def makeDefaultProtocolForModule(self, module_name):
        if module_name in self.modules.keys():
            self.protocols[module_name]=getattr(self.modules[module_name]['module'],module_name)().generateDefaultProtocol(self.image)

    def makeDefaultProtocols(self,pipeline=None,template=None):
        self.checkImage()
        logger("Default protocols are being generated using image information",dtiprep.Color.PROCESS)
        if template==None:
            template=yaml.safe_load(open(self.template_filename,'r'))

        ### generate default protocols
        self.protocols={}
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
        for p in self.pipeline:
            mod_name,options  = p
            self.makeDefaultProtocolForModule(mod_name)

        logger("Default protocols are generated.",dtiprep.Color.OK)

    def furnishPipeline(self,pipeline):
        new_pipeline=[]
        for parr in pipeline:
            default_options=default_pipeline_options()
            if not isinstance(parr, list):
                new_pipeline.append([parr,default_options])
            else:
                p,opt = parr 
                default_options.update(opt)
                newopt=default_options
                new_pipeline.append([p,newopt])
        return new_pipeline 


    def checkRunnable(self):
        logger("Checking runability ...",dtiprep.Color.PROCESS)
        self.checkImage()
        self.checkProtocols()
        self.checkPipeline()
        self.checkDependencies()

    def checkImage(self):
         if self.image is None: 
            logger("[ERROR] Image is not loaded.",dtiprep.Color.ERROR)
            raise Exception("Image is not set")       
    def checkProtocols(self):
        if self.protocols is None:
            logger("[ERROR] Protocols are not set.",dtiprep.Color.ERROR)
            raise Exception("Image is not set")    
    def checkPipeline(self):
        if self.pipeline is None:
            logger("[ERROR] Protocols are not set.",dtiprep.Color.ERROR)
            raise Exception("Image is not set")
    def checkDependencies(self):
        for parr in self.pipeline:
            p, options = parr 
            if not self.modules[p]['valid']: 
                msg=self.modules[p]['validity_message']
                logger("[ERROR] Dependency is not met for the module : {} , {}".format(p,msg),dtiprep.Color.WARNING)
                raise Exception("Module {} is not configured correctly.".format(p))    

    @dtiprep.measure_time
    def runPipeline(self):
        try:

            self.checkRunnable()
            self.processes_history=[]
            
            execution_sequence = _generate_exec_seqeunce(self.pipeline)
            output_dir_map=_generate_output_directories(self.output_dir,execution_sequence)
            protocol_filename=Path(self.output_dir).joinpath('protocols.yml').__str__()
            logger("Writing protocol file to : {}".format(protocol_filename),dtiprep.Color.PROCESS)
            self.writeProtocols(protocol_filename)
            ## run pipeline
            for idx,parr in enumerate(execution_sequence):
                uid, p, options=parr 
                bt=time.time()
                logger("-----------------------------------------------",dtiprep.Color.BOLD)
                logger("Processing [{0}/{1}] : {2}".format(idx+1,len(self.pipeline),p),dtiprep.Color.BOLD)    
                logger("-----------------------------------------------",dtiprep.Color.BOLD)
                
                m=getattr(self.modules[p]['module'], p)()
                m.setProtocol(self.protocols)
                m.setOptions(options)
                logger(yaml.dump(m.getOptions()),dtiprep.Color.DEV)
                logger(yaml.dump(m.getProtocol()),dtiprep.Color.DEV)
                m.initialize(self.result_history,output_dir=output_dir_map[uid])
                success=False
                resultfile_path=Path(output_dir_map[uid]).joinpath('result.yml')

                ### if result file is exist, just run post process and continue with previous information
                if resultfile_path.exists() and not options['overwrite']:
                    result_temp=yaml.safe_load(open(resultfile_path,'r'))
                    logger("Result file exists, just post-processing ...",dtiprep.Color.INFO+dtiprep.Color.BOLD)
                    m.postProcess(result_temp)
                    success=True
                else: # in case overwriting or there is no result.yml file
                    success=m.run()
                if not success: raise Exception("Process failed in {}".format(p))
                self.previous_process=m  #this is for the image id reference
                self.result_history =m.getResultHistory()
                et=time.time()-bt
                self.result_history[-1]['processing_time']=et
                logger("[{}] Processed time : {:.2f}s".format(p,et),dtiprep.Color.DEV)
            return self.result_history

        except Exception as e:
            logger("Exception occurred in runPipeline {}".format(str(e)))
            traceback.print_exc()
            return None
        finally:
            with open(Path(self.output_dir).joinpath('result_history.yml'),'w') as f:
                yaml.dump(self.result_history,f)

