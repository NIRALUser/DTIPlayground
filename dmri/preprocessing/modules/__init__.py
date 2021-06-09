
import dmri.preprocessing as prep

import yaml, inspect
from pathlib import Path 
import pkgutil,sys, copy

logger=prep.logger.write

@prep.measure_time
def _load_modules(user_module_paths=[]):
    modules=_load_default_modules()
    usermodules= _load_modules_from_paths(user_module_paths)
    modules.update(usermodules)
    return modules

def _load_default_modules(): # user_modules list of paths of user modules
    modules={}
    default_module_paths=[Path(__file__).parent]
    return _load_modules_from_paths(default_module_paths)

def _load_modules_from_paths(user_module_paths: list):
    modules={}
    mods=[]
    for pth in map(lambda x: str(x),user_module_paths):  ## path objects to string array
        logger("Loading modules from {} ".format(str(pth)),prep.Color.PROCESS)
        sys.path.insert(0, pth)
        pkgs_info=list(pkgutil.walk_packages([pth]))
        for p in pkgs_info:
            if len(p.name.split('.'))==1:
                logger("Loading module : {}".format(p.name),prep.Color.OK)
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
                                "validity_message" : None 
                                } 
    return modules 

@prep.measure_time
def check_module_validity(modules:list,environment):
    logger("Checking dependencies ...",prep.Color.PROCESS)
    for name,md in modules.items():
                validity, msg=getattr(md['module'], name)().checkDependency(environment)
                if not validity:
                    logger("[WARNING] Dependency is not met for the module : {} , {}".format(name,msg),prep.Color.WARNING)
                modules[name]['valid']=validity
                modules[name]['validity_message']=msg
    logger("Checking dependencies DONE",prep.Color.OK)
    return modules 


def generate_module_envionrment(modules :list):
    env={}
    for name,m in modules.items():
        module_env=getattr(m['module'],name)().generateDefaultEnvironment()
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
                "success" : False
            } 
        }

    return res 

class DTIPrepModule: #base class
    def __init__(self,*args, **kwargs):
        self.name=self.__class__.__name__
        self.source_image=None
        self.image=None #image for output
        self.protocol=None
        self.result_history=None
        self.result=empty_result()
       
        ##
        self.template=None ## template information located at the same directory of this module.(modulename.yml)
        self.output_dir=None ## output root
        self.output_root=None ## output root (one level up)
        self.computation_dir=None ## computation files 
        self.options={} ## this is pipeline option, not protocol. It should not affect the way of computing, only does to the behaviour of execution

        ## loading template file (yml)
        self.loadTemplate()
    
    @prep.measure_time
    def initialize(self,result_history,image_path,output_dir):
        self.history=result_history
        self.result_history=result_history[image_path]
        self.output_dir=output_dir
        self.output_root=str(Path(self.output_dir).parent)
        self.computation_dir=Path(output_dir).joinpath("computations")
        self.computation_dir.mkdir(parents=True,exist_ok=True)

        inputpath=Path(self.result_history[0]["output"]["image_path"]).absolute()


        previous_result=self.getPreviousResult()

        if previous_result["output"]["image_object"] is not None:
            self.source_image=prep.object_by_id(previous_result["output"]["image_object"])
            self.image=copy.deepcopy(self.source_image)
            logger("Source Image (Previous output) loaded from memory (object id): {}".format(id(self.source_image)),prep.Color.OK)
        else:
            logger("Loading image from the file : {}".format(previous_result['output']['image_path']),prep.Color.PROCESS)
            src_image_filename=Path(self.output_root).joinpath(previous_result['output']['image_path']).__str__()
            self.source_image=self.loadImage(src_image_filename)
            self.image=copy.deepcopy(self.source_image)
                ## gradient information update
            prev_output_dir=Path(self.output_root).joinpath(previous_result['output']['output_directory'])
            prev_gradient_filename=prev_output_dir.joinpath('output_gradients.yml').__str__()
            prev_image_information_filename=prev_output_dir.joinpath('output_image_information.yml').__str__()
            self.image.loadGradients(prev_gradient_filename)
            self.image.loadImageInformation(prev_image_information_filename)
            logger("Source Image (Previous output) loaded",prep.Color.OK)

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


    def checkDependency(self,environment={}): #use information in template, check if this module can be processed
        return True , None

    def writeImage(self,filename,dest_type='nrrd'):
        self.image.writeImage(filename,dest_type=dest_type)
        self.result['output']['image_path']=str(Path(filename).absolute().relative_to(self.output_root))

    @prep.measure_time
    def loadImage(self, image_path, gradient_path=None):
        grad_path=gradient_path 
        if gradient_path is None:
            grad_path=Path(image_path).parent.joinpath('gradients.yml')

        image=prep.dwi.DWI(image_path)
        if grad_path.exists():
            grad=yaml.safe_load(open(grad_path,'r'))
            image.setGradients(grad)
        return image

    def getPreviousResult(self):
        return self.result_history[-1]

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

    def process(self,*args,**kwargs): ## returns new result array (User implementation), returns output result
        #anything common
        ## variables : self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        pass

    @prep.measure_time
    def postProcess(self,result_obj):
        self.result=result_obj
        self.result['input']=self.getPreviousResult()['output']
        self.image.deleteGradientsByOriginalIndex(self.result['output']['excluded_gradients_original_indexes'])
        logger("Excluded gradient indexes (original index) : {}"
            .format(self.result['output']['excluded_gradients_original_indexes']),prep.Color.WARNING)

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

        self.result['output']['success']=True
        outstr=yaml.dump(self.result)
        with open(str(Path(self.output_dir).joinpath('result.yml')),'w') as f:
            yaml.dump(self.result,f)
        self.image.dumpGradients(gradient_filename)
        self.image.dumpInformation(image_information_filename)

        ## output gradients summary
        b_grads, _ =self.image.getBaselines()
        grad_summary = self.image.gradientSummary()
        logger("Remaining Gradients summary - Num.Gradients: {}, Num.Baselines: {}"
            .format(grad_summary['number_of_gradients'],
                    grad_summary['number_of_baselines']),prep.Color.INFO)

        logger("Remaining baselines",prep.Color.INFO)
        for g in b_grads:
            logger("[Gradient.idx {:03d} Original.idx {:03d}] Gradient Dir {} B-Value {:.1f}"
                .format(g['index'],g['original_index'],g['gradient'],g['b_value']),prep.Color.INFO)


    @prep.measure_time
    def run(self,*args,**kwargs): #wrapper 
    
        res=self.process(*args,**kwargs) ## main computation for user implementation
        ## Post processing
        self.postProcess(res) ## pretty much automatic        
        return self.result["output"]["success"]

    def getResultHistory(self):
        return self.result_history+[self.result]