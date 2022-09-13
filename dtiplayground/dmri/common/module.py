
import dtiplayground.dmri.common as common

import yaml, inspect
from pathlib import Path 
import pkgutil,sys, copy
import os
import markdown

logger=common.logger.write

@common.measure_time
def _load_modules(system_module_paths=[],user_module_paths=[],module_names=None, **options):
    modules=_load_default_modules(system_module_paths, module_names, **options)
    usermodules= _load_modules_from_paths(user_module_paths,module_names, **options)
    modules.update(usermodules)
    return modules

def _load_default_modules( system_module_paths: list, module_names=None, **options): # user_modules list of paths of user modules
    modules={}
    return _load_modules_from_paths(system_module_paths,module_names, **options)

def _load_modules_from_paths(user_module_paths: list,module_names=None, **options): #module names = list of modules to load (if none, load everything)
    modules={}
    mods=[]
    for pth in map(lambda x: str(x),user_module_paths):  ## path objects to string array
        logger("Loading modules from {} ".format(str(pth)),common.Color.PROCESS)
        sys.path.insert(0, pth)
        pkgs_info=list(pkgutil.walk_packages([pth]))
        for p in pkgs_info:
            if module_names is not None:
                if p.name.split('.')[0] in module_names:
                    if len(p.name.split('.'))==1:
                        logger("Loading module : {}".format(p.name),common.Color.OK)
                    mods.append(p.module_finder.find_module(p.name).load_module(p.name))
            else:
                if len(p.name.split('.'))==1:
                    logger("Loading module : {}".format(p.name),common.Color.OK)
                mods.append(p.module_finder.find_module(p.name).load_module(p.name))
                    
        mod_filtered=list(filter(lambda x: len(x.__name__.split('.'))==2 and x.__name__.split('.')[0]==x.__name__.split('.')[1] ,mods))
        
        for md in mod_filtered:
            fn=Path(md.__file__)
            template_path= fn.parent.joinpath(fn.stem+'.yml')
            template=yaml.safe_load(open(template_path,'r'))
            name=md.__name__.split('.')[0]  #module name
            modules[name]={
                                "name" : name,
                                "module" : md,
                                "path" : md.__file__,
                                "template" : template,
                                "template_path" : template_path,
                                "valid" : False,
                                "validity_message" : None,
                                "options" : options
                                } 
    return modules 

@common.measure_time
def check_module_validity(modules:list,environment,config_dir):
    logger("Checking dependencies ...",common.Color.PROCESS)
    for name,md in modules.items():
                validity, msg=getattr(md['module'], name)(config_dir).checkDependency(environment)
                if not validity:
                    logger("[WARNING] Dependency is not met for the module : {} , {}".format(name,msg),common.Color.WARNING)
                modules[name]['valid']=validity
                modules[name]['validity_message']=msg
    logger("Checking dependencies DONE",common.Color.OK)
    return modules 


def generate_module_envionrment(modules :list,install_dir,*args,**kwargs):
    env={}
    for name,m in modules.items():
        mod_instance=getattr(m['module'],name)(install_dir)
        mod_instance.install(install_dir,*args,**kwargs)
        module_env=mod_instance.generateDefaultEnvironment()
        env[name]=module_env
    return env 

load_modules=_load_modules

def empty_result():
    res={
            "module_name" : None,
            "input" : None,
            "output": {
                "image_path" : None, #output image path (string)
                "image_object" : None,
                "output_directory": None,
                "excluded_gradients_original_indexes": [],
                "output_path": None,
                "success" : False,
                "image_information": None,
                "global_variables": {}
            } 
        }

    return res 

class DTIPlaygroundModule: #base class
    def __init__(self,config_dir,*args, **kwargs):
        self.name=self.__class__.__name__
        self.config_dir=config_dir
        self.source_image=None
        self.image=None #image for output
        self.images=[] #image list for the multi-input modules
        self.image_paths=[] 
        self.protocol=None
        self.result_history=None
        self.result=empty_result()
       
        ##
        self.template=None ## template information located at the same directory of this module.(modulename.yml)
        self.output_dir=None ## output root
        self.output_root=None ## output root (one level up)
        self.computation_dir=None ## computation files 
        self.options={} ## this is pipeline option, not protocol. It should not affect the way of computing, only does to the behaviour of execution
        self.output_files = []
        self.software_info = {}
        self.softwares = {}
        self.global_variables={}
        if 'software_info' in kwargs:
            self.software_info= kwargs['software_info']
            self.softwares = self.software_info['softwares']
        if 'global_variables' in kwargs:
            self.global_variables.update(kwargs['global_variables'])
        ## loading template file (yml)
        self.loadTemplate()

    @common.measure_time
    def initialize(self,result_history,image_path,output_dir):
        self.history=result_history
        self.result_history=result_history[image_path]
        self.output_dir=output_dir
        self.output_root=str(Path(self.output_dir).parent.parent)
        self.computation_dir=Path(output_dir).joinpath("computations")
        self.computation_dir.mkdir(parents=True,exist_ok=True)
        inputpath=None

        if 'multi_input' in self.template['process_attributes']:
            previous_outputs=[]
            for k,v in self.history.items():
                if k != image_path:
                    previous_outputs.append(v[-1])
            
            for idx,previous_result in enumerate(previous_outputs):
                if previous_result["output"]["image_object"] is not None:
                    # self.source_image=common.object_by_id(previous_result["output"]["image_object"])
                    # self.images.append(copy.deepcopy(self.source_image))
                    self.source_image=common.object_by_id(previous_result["output"]["image_object"])
                    self.images.append(self.source_image)
                    logger("Source Image (Previous output) loaded from memory (object id): {}".format(id(self.source_image)),common.Color.OK)
                else:
                    logger("Loading image from the file : {}".format(previous_result['output']['image_path']),common.Color.PROCESS)
                    src_image_filename=Path(self.output_root).joinpath(previous_result['output']['image_path']).__str__()
                    # self.source_image=self.loadImage(src_image_filename)
                    # self.images.append(copy.deepcopy(self.source_image))
                    self.source_image=self.loadImage(src_image_filename)
                    self.images.append(self.source_image)
                        ## gradient information update
                    prev_output_dir=Path(self.output_root).joinpath(previous_result['output']['output_directory'])
                    prev_gradient_filename=prev_output_dir.joinpath('output_gradients.yml').__str__()
                    prev_image_information_filename=prev_output_dir.joinpath('output_image_information.yml').__str__()
                    self.images[idx].loadGradients(prev_gradient_filename)
                    self.images[idx].loadImageInformation(prev_image_information_filename)
                    logger("Source Image (Previous output) loaded",common.Color.OK)

                    ### dump initial gradients and image information
                gradient_filename=str(Path(self.output_dir).joinpath('input_gradients_{:02d}.yml'.format(idx)))
                image_information_filename=str(Path(self.output_dir).joinpath('input_image_information_{:02d}.yml'.format(idx)))

                self.images[idx].dumpGradients(gradient_filename)
                self.images[idx].dumpInformation(image_information_filename)

            self.result_history.append({"output":previous_outputs})
            self.image=copy.deepcopy(self.images[0])
            self.result["module_name"]=self.name 
            self.result["input"]=previous_outputs
            self.result["output"]["image_object"]= id(self.image)
            self.result["output"]["success"]=False 
            self.result["output"]["output_directory"]=str(Path(self.output_dir).relative_to(self.output_root))

        else:
            #inputpath=Path(self.result_history[0]["output"]["image_path"]).absolute()
            previous_result=self.getPreviousResult()
            logger(yaml.safe_dump(previous_result))
            if previous_result["output"]["image_object"] is not None:
                # self.source_image=common.object_by_id(previous_result["output"]["image_object"])
                # self.image=copy.deepcopy(self.source_image)
                self.source_image=common.object_by_id(previous_result["output"]["image_object"])
                self.image=self.source_image
                logger("Source Image (Previous output) loaded from memory (object id): {}".format(id(self.source_image)),common.Color.OK)
            else:
                logger("Loading image from the file : {}".format(previous_result['output']['image_path']),common.Color.PROCESS)
                src_image_filename=Path(self.output_root).joinpath(previous_result['output']['image_path']).__str__()
                # self.source_image=self.loadImage(src_image_filename)
                # self.image=copy.deepcopy(self.source_image)
                self.source_image=self.loadImage(src_image_filename)
                self.image=self.source_image
                    ## gradient information update
                prev_output_dir=Path(self.output_root).joinpath(previous_result['output']['output_directory'])
                prev_gradient_filename=prev_output_dir.joinpath('output_gradients.yml').__str__()
                prev_image_information_filename=prev_output_dir.joinpath('output_image_information.yml').__str__()
                self.image.loadGradients(prev_gradient_filename)
                self.image.loadImageInformation(prev_image_information_filename)
                logger("Source Image (Previous output) loaded",common.Color.OK)

            ### dump initial gradients and image information
            gradient_filename=str(Path(self.output_dir).joinpath('input_gradients.yml'))
            image_information_filename=str(Path(self.output_dir).joinpath('input_image_information.yml'))

            self.image.dumpGradients(gradient_filename)
            self.image.dumpInformation(image_information_filename)

            self.result["module_name"]=self.name 
            self.result["input"]=previous_result["output"]
            self.result["output"]["image_object"]= id(self.image)
            self.result["output"]["success"]=False 
            self.result["output"]["output_directory"]=str(Path(self.output_dir).relative_to(self.output_root))


    def install(self,install_dir=None,*args,**kwargs):
        pass 

    def checkDependency(self,environment={}): #use information in template, check if this module can be processed
        return True , None

    def addOutputFile(self, src_filename, postfix):
        self.output_files.append({'source': src_filename, 'postfix': postfix})

    def addGlobalVariable(self, key, value):
        self.result['output']['global_variables'][key]=value

    def updateGlobalVariable(self, global_vars):
        self.result['output']['global_variables'].update(global_vars)
        
    def getGlobalVariables(self):
        return self.result['output']['global_variables']

    def getOutputFiles(self):
        return self.output_files

    @common.measure_time
    def writeImage(self,filename,dest_type='nrrd',dtype='short'):
        self.image.writeImage(filename,dest_type=dest_type,dtype=dtype)
        #self.result['output']['image_path']=str(Path(filename).absolute().relative_to(self.output_root))
        self.result['output']['image_path']=str(Path(filename).absolute())

    @common.measure_time
    def writeImageWithOriginalSpace(self,filename,dest_type='nrrd',dtype='short'):
        target_space = self.getSourceImageInformation()['space']
        self.image.setSpaceDirection(target_space=target_space)
        self.writeImage(filename,dest_type,dtype)

    @common.measure_time 
    def loadImage(self, image_path, gradient_path=None):
        grad_path=gradient_path 
        if gradient_path is None:
            grad_path=Path(image_path).parent.joinpath('gradients.yml')

        image=common.dwi.DWI(image_path)
        if grad_path.exists():
            grad=yaml.safe_load(open(grad_path,'r'))
            image.setGradients(grad)
        return image

    def getInputResult(self):
        return self.result_history[0]

    def getPreviousResult(self):
        return self.result_history[-1]

    def getSourceImageInformation(self):
        inputInfo = self.getInputResult()
        info=None
        #if 'multi_input' in self.template['process_attributes']:
        if type(inputInfo['output'])==list:
            info = inputInfo['output'][0]['output']['image_information']
        else:
            info = inputInfo['output']['image_information']
        return info

    def loadTemplate(self):
        modulepath=inspect.getfile(self.__class__)
        template_filename=Path(modulepath).parent.joinpath(self.name+".yml")
        self.template=yaml.safe_load(open(template_filename,'r'))

    def setImage(self, image ):
        self.image=image

    def setOptionsAndProtocol(self,options):
        self.options=options['options']
        self.protocol=options['protocol']

    def setProtocol(self,options):
        self.protocol=options['protocol']

    def getProtocol(self):
        return self.protocol

    def setOptions(self,options):
        self.options=options['options']

    def getOptions(self):
        return self.options 

    def getTemplate(self):
        return self.template 

    def generateDefaultProtocol(self,image_obj):
        self.protocol={}
        for k,v in self.template['protocol'].items():
                self.protocol[k]=v['default_value']
        return self.protocol

    def generateDefaultEnvironment(self):
        return None

    def overwriteFile(self, filename):
        return (not Path(filename).exists()) or self.options['overwrite']

    def process(self,*args,**kwargs): ## returns new result array (User implementation), returns output result
        #anything common
        ## variables : self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        pass

    @common.measure_time
    def postProcess(self,result_obj,opts):
        self.result=result_obj
        if "multi_input" in self.template['process_attributes']:
            self.image=self.loadImage(self.result['output']['image_path'])
            self.result['output']['image_object']=id(self.image)
        self.result['input']=self.getPreviousResult()['output']
        self.image.deleteGradientsByOriginalIndex(self.result['output']['excluded_gradients_original_indexes'])
        logger("Excluded gradient indexes (original index) : {}"
            .format(self.result['output']['excluded_gradients_original_indexes']),common.Color.WARNING)

        gradient_filename=str(Path(self.output_dir).joinpath('output_gradients.yml'))
        image_information_filename=str(Path(self.output_dir).joinpath('output_image_information.yml'))
        self.result['output']['image_object']=id(self.image)
        ### if deform_image process type, then forced file loading should be done from the second run in the subsequent process.
        if "deform_image" in self.template['process_attributes']:        
            if  Path(self.output_dir).joinpath('result.yml').exists() and not self.options['overwrite']: ## second run
                self.result['output']['image_object']=None 
                #self.image.gradients=yaml.safe_load(open(gradient_filename,'r'))
                self.image.loadGradients(gradient_filename)
                self.image.loadImageInformation(image_information_filename)
                #self.image.information=yaml.safe_load(open(image_information_filename,'r'))
            else: ## first run
                self.result['output']['image_object']=id(self.image)
        ### deform_image ends

        
        ### set baseline_threashold
        baseline_threshold=opts['baseline_threshold']
        self.image.setB0Threshold(baseline_threshold)
        self.image.getGradients()

        self.result['output']['success']=True
        self.result['output']['image_information']=self.image.information
        outstr=yaml.safe_dump(self.result)
        with open(str(Path(self.output_dir).joinpath('result.yml')),'w') as f:
            yaml.safe_dump(self.result,f)
        self.image.dumpGradients(gradient_filename)
        self.image.dumpInformation(image_information_filename)

        ## output gradients summary
        b_grads, _ =self.image.getBaselines()
        grad_summary = self.image.gradientSummary()
        logger("Remaining Gradients summary - Num.Gradients: {}, Num.Baselines: {}"
            .format(grad_summary['number_of_gradients'],
                    grad_summary['number_of_baselines']),common.Color.INFO)

        logger("Remaining baselines",common.Color.INFO)
        for g in b_grads:
            logger("[Gradient.idx {:03d} Original.idx {:03d}] Gradient Dir {} B-Value {:.1f}"
                .format(g['index'],g['original_index'],g['gradient'],g['b_value']),common.Color.INFO)

        self.makeReport()



    @common.measure_time
    def run(self,*args,**kwargs): #wrapper 
        opts=args[0]
        baseline_threshold=opts['baseline_threshold']
        if 'global_vars' in kwargs:
            self.result['output']['global_variables'].update(kwargs['global_vars'])
            self.global_variables.update(kwargs['global_vars'])
        self.image.setB0Threshold(baseline_threshold)
        self.image.getGradients()
        
        res=self.process(*args,**kwargs) ## main computation for user implementation
        ## Post processing
        self.postProcess(res,opts) ## pretty much automatic        
        #return self.result["output"]["success"]
        return self.result["output"]

    def getResultHistory(self):
        return self.result_history+[self.result]

    def makeReport(self):
        self.result['report'] = {'module_report_paths': os.path.abspath(self.output_dir) + '/report.md',
                                 'csv_data': {'image_name': None,
                                              'original_number_of_gradients': None,
                                              'excluded_gradients': None,
                                              'rms_gt_1': None,
                                              'rms_gt_2': None,
                                              'rms_gt_3': None}, 
                                 'eddymotion_pdf_path': None}

        if self.result['input']['image_path']:
            input_image = self.result['input']['image_path']
            for number in self.result['input']['image_information']['sizes']:
                if number not in self.result['input']['image_information']['image_size']:
                    self.result['report']['csv_data']['original_number_of_gradients'] = number
        elif type(self.result_history[0]["output"]) == dict: #single input
            input_image = self.result_history[0]["output"]["image_path"]
        else:
            input_image = None
            input_directory = self.result["input"]["output_directory"]
            while input_image == None:
                previous_result = yaml.safe_load(open(str(Path(self.output_dir).parent.parent) + "/" + input_directory + "/result.yml", 'r'))
                input_image = previous_result["input"]["image_path"]
                if "output_directory" in previous_result["input"]:
                    input_directory = previous_result["input"]["output_directory"]
        self.result['report']['csv_data']['image_name'] = str(os.path.abspath(input_image))
        with open(os.path.abspath(self.output_dir) + '/report.md', 'bw+') as f:
            f.write('## {}\n'.format("Module: " + self.result['module_name']).encode('utf-8'))
            f.write('### {}\n'.format("input image: " + str(os.path.abspath(input_image))).encode('utf-8'))
            f.seek(0)
            markdown.markdownFromFile(input=f, output=os.path.abspath(self.output_dir) + '/report.html')
  
        with open(str(Path(self.output_dir).joinpath('result.yml')),'w') as f:
            yaml.dump(self.result,f)


DTIPrepModule = DTIPlaygroundModule