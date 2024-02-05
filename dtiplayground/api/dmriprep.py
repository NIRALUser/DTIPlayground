##################################################################################
### Module : dmriatlasbuilder.py
### Description : Atlasbuilder api
###
###
###
### Written by : scalphunter@gmail.com ,  2022/10/08
### Copyrights reserved by NIRAL
##################################################################################

import sys, traceback
import os

### API
from flask import request, Response , send_from_directory, jsonify
import json
from . import utils
from pathlib import Path
import yaml
import multiprocessing
from multiprocessing import Process
class DMRIPrepAPI:
    def __init__(self,server,**kwargs):
        self.server = server
        self.app=self.server.app
        self.initEndpoints()

##### Endpoints

    def initEndpoints(self):

        @self.app.route('/api/v1/dmriprep',methods=['GET'])
        def _get_app_info():
            sc=200
            res=None
            req=None
            request_id=utils.get_request_id()
            try:
                res= self.getAppInfo(extra_dirs=[])
                res= utils.add_request_id(res)
            except Exception as e:
                sc=500
                exc=traceback.format_exc()
                res=utils.error_message("{}\n{}".format(str(e),exc),500,request_id)
            finally:
                resp=Response(json.dumps(res),status=sc)
                resp.headers['Content-Type']='application/json'
                return resp  

        @self.app.route('/api/v1/dmriprep/generate-default-protocols',methods=['POST'])
        def _post_dmriprep_generate_protocols():
            sc=200
            res=None
            req=None
            request_id=utils.get_request_id()
            try:
                req=request.get_json()
                res= self.generate_default_protocols(req)
                res= utils.add_request_id(res)
            except Exception as e:
                sc=500
                exc=traceback.format_exc()
                res=utils.error_message("{}\n{}".format(str(e),exc),500,request_id)
            finally:
                resp=Response(json.dumps(res),status=sc)
                resp.headers['Content-Type']='application/json'
                return resp  

        @self.app.route('/api/v1/dmriprep',methods=['POST'])
        def _execute_dmriprep():
            sc=200
            res=None
            req=None
            request_id=utils.get_request_id()
            try:
                req=request.get_json()
                res= self.run(req)
                res= utils.add_request_id(res)
            except Exception as e:
                sc=500
                exc=traceback.format_exc()
                res=utils.error_message("{}\n{}".format(str(e),exc),500,request_id)
            finally:
                resp=Response(json.dumps(res),status=sc)
                resp.headers['Content-Type']='application/json'
                return resp  

        @self.app.route('/api/v1/dmriprep/template',methods=['GET'])
        def _get_module_template():
            sc=200
            res=None
            req=None
            request_id=utils.get_request_id()
            param_module_name = request.args.get('name')
            param_dirs_name = request.args.get('dirs', default="[]")

            try:
                res= self.getTemplate(param_module_name, json.loads(param_dirs_name))
                res= utils.add_request_id(res)
            except Exception as e:
                sc=500
                exc=traceback.format_exc()
                res=utils.error_message("{}\n{}".format(str(e),exc),500,request_id)
            finally:
                resp=Response(json.dumps(res),status=sc)
                resp.headers['Content-Type']='application/json'
                return resp  


    def getAppInfo(self, extra_dirs = []):
        from dtiplayground.config import INFO
        version = INFO['dmriprep']['version']

        res = {
            'application' : 'dmriprep',
            'version': version,
            'modules': self.getModuleList(extra_dirs),
            'protocol_template': self.getProtocolTemplateConfig()
        }

        return res

    def generate_default_protocols(self,req):
        from dtiplayground.config import INFO
        req.setdefault('version', INFO['dmriprep']['version'])

        params = {
            'version' : req['version'],
            'output_dir' : req['output_dir'],
            'pipeline' : req['pipeline'],
            'io' : req['io']
        }

        protocols = {
            'version': params['version'],
            'io': params['io'],
            'pipeline': params['pipeline']
        }


        output_dir=Path(params['output_dir'])
        output_dir.mkdir(exist_ok=True,parents=False)

        protocol_fn_path = output_dir.joinpath('protocols.yml')
        protocol_fn_json = output_dir.joinpath('protocols.json')
        yaml.safe_dump(protocols, open(protocol_fn_path,'w'))
        json.dump(protocols, open(protocol_fn_json,'w'),indent=4)
        return req

    # def run(self, req):

    #     params = {
    #         'output_dir' : req['output_dir'],
    #     }
    #     output_dir = Path(params['output_dir'])
    #     config_dir = self.getConfigDirectory()
    #     protocol_fn = output_dir.joinpath('protocols.yml')
    #     protocol = yaml.safe_load(open(protocol_fn,'r'))
    #     params.setdefault('config_dir',str(config_dir))
    #     params.setdefault('protocol_path',str(protocol_fn))
    #     params.setdefault('execution_id', utils.get_uuid())
    #     params.setdefault('global_variables', {})

    
    #     def dmriprep_proc(param):

            
    #         with open(output_dir.joinpath('log.txt'),'w') as sys.stdout:
                
    #             ### begin
    #             os.environ['OMP_NUM_THREADS']=str(protocol['io']['num_threads']) ## this should go before loading any dipy function. 
    #             os.environ['ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS'] = str(protocol['io']['num_threads']) ## for ANTS threading
    #             import  dtiplayground.dmri.common as common
    #             import dtiplayground.dmri.preprocessing
    #             import dtiplayground.dmri.preprocessing.modules as m
    #             import dtiplayground.dmri.preprocessing.protocols as p
    #             logger = common.logger
    #             logger.setFilePointer(sys.stdout)
    #             sys.path.append(Path(m.__file__).parent.__str__()) 
    #             image_list = []
    #             image_list.append(protocol['io']['input_image_1'])
    #             if 'input_image_2' in protocol['io']:
    #                 if protocol['io']['input_image_2'] and protocol['io']['input_image_2'].strip()!='':
    #                     image_list.append(protocol['io']['input_image_2'])

    #             proto= p.Protocols(config_dir,logger=logger)
    #             proto.loadImages(image_list, protocol['io']['baseline_threshold'])
    #             proto.setOutputDirectory(params['output_dir'])
    #             proto.loadProtocols(str(protocol_fn))
    #             proto.setNumThreads(int(protocol['io']['num_threads']))
    #             proto.runPipeline(options=params)
             

    #     res = { 
    #         'execution_id' : params['execution_id'],
    #         'output_dir' : output_dir.__str__()
    #     }
    #     proc = Process(target= dmriprep_proc, name=params['execution_id'],args=[params])
    #     proc.start()

    #     res['pid']=proc.pid
    #     res['proc_name']=proc.name
    #     res['status']='running'
    #     json.dump(res,open(output_dir.joinpath('status.json'),'w'),indent=4)
    #     proc.join()
    #     if proc.exitcode != 0 : 
    #         res['status']='failed'
    #         json.dump(res,open(output_dir.joinpath('status.json'),'w'),indent=4)
    #         raise Exception("Error during running")
    #     else:
    #         res['status']='success'
    #         json.dump(res,open(output_dir.joinpath('status.json'),'w'),indent=4)
    #     return res

    def run(self, req):

        params = {
            'output_dir' : req['output_dir'],
        }
        output_dir = Path(params['output_dir'])
        config_dir = self.getConfigDirectory()
        protocol_fn = output_dir.joinpath('protocols.yml')
        protocol = yaml.safe_load(open(protocol_fn,'r'))
        params.setdefault('config_dir',str(config_dir))
        params.setdefault('protocol_path',str(protocol_fn))
        params.setdefault('execution_id', utils.get_uuid())
        params.setdefault('global_variables', {})

    
        def dmriprep_proc(param):

            
            with open(output_dir.joinpath('log.txt'),'w') as sys.stdout:
                
                ### begin
                os.environ['OMP_NUM_THREADS']=str(protocol['io']['num_threads']) ## this should go before loading any dipy function. 
                os.environ['ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS'] = str(protocol['io']['num_threads']) ## for ANTS threading
                import  dtiplayground.dmri.common as common
                import dtiplayground.dmri.preprocessing
                import dtiplayground.dmri.preprocessing.modules as m
                import dtiplayground.dmri.preprocessing.protocols as p
                from dtiplayground.dmri.preprocessing.app import DMRIPrepApp
                
                inputs = [protocol['io']['input_image_1']]
                protocol['io'].setdefault('input_image_2',None)
                if protocol['io']['input_image_2'] is not None:
                     if "," in protocol['io']['input_image_2']:
                        mult_image_list = protocol['io']['input_image_2'].split(',')
                        inputs += mult_image_list
                     else:
                         inputs.append(protocol['io']['input_image_2'])
                options={
                    "input_image_paths" : inputs,
                    "protocol_path" : str(protocol_fn),
                    "output_dir" : protocol['io']['output_directory'],
                    "num_threads":  protocol['io']['num_threads'],
                    "default_protocols": None,
                    "execution_id": param['execution_id'],
                    "baseline_threshold" : protocol['io']['baseline_threshold'],
                    "output_format" : protocol['io']['output_format'],
                    "output_file_base" : protocol['io']['output_filename_base'],
                    "no_output_image" :  protocol['io']['no_output_image'],
                    "global_variables" : {}
                }
                app=DMRIPrepApp(config_root=str(self.server.config_dir))
                app.run(options)

        res = { 
            'execution_id' : params['execution_id'],
            'output_dir' : output_dir.__str__()
        }
        proc = Process(target= dmriprep_proc, name=params['execution_id'],args=[params])
        proc.start()

        res['pid']=proc.pid
        res['proc_name']=proc.name
        res['status']='running'
        json.dump(res,open(output_dir.joinpath('status.json'),'w'),indent=4)
        proc.join()
        if proc.exitcode != 0 : 
            res['status']='failed'
            json.dump(res,open(output_dir.joinpath('status.json'),'w'),indent=4)
            raise Exception("Error during running")
        else:
            res['status']='success'
            json.dump(res,open(output_dir.joinpath('status.json'),'w'),indent=4)
        return res

    def getProtocolTemplateConfig(self):
        # config_dir = self.getConfigDirectory();
        import dtiplayground.dmri.preprocessing.templates as t
        ptc_fn = Path(t.__file__).parent.joinpath('protocol_template.yml')
        # ptc_fn = config_dir.joinpath('protocol_template.yml')
        with open(ptc_fn,'r') as f:
            ptc = yaml.safe_load(f)

        ptc['ui'] = {
            'execution': self.convertTemplate(ptc['options']['io'])
        } 
        return ptc

    def getModuleList(self,extra_dirs = []):
        res = {
            'system': self.getSystemModuleList(),
            'user': self.getUserModuleList(extra_dirs)
        }
        return res

    def getSystemModuleList(self):
        system_dir = Path(self.getSystemModulePath())    
        sp = [x for x in system_dir.glob('*')]
        sp = list(map(lambda x: {'name': x.name, 'path': str(x)},filter(lambda x: x.is_dir() and x.joinpath('__init__.py').exists() , sp)))
        sp.sort(key=lambda x: x['name'])
        return sp

    def getUserModuleList(self,extra_dirs=[]):
        user_module_dir = Path(self.getUserModuleDirectory())
        res = []
        for d in ([user_module_dir] + extra_dirs):      
            up = [x for x in Path(d).glob('*')]
            up = list(map(lambda x: {'name': x.name, 'path': str(x)},filter(lambda x: x.is_dir() and x.joinpath('__init__.py').exists() , up)))
            res = res + up
        res.sort(key=lambda x: x['name'])
        return res

    def getTemplate(self, name, extra_dirs=[]):

        system_dir = Path(self.getSystemModulePath())
        user_module_dir = Path(self.getUserModuleDirectory())
        filepath = system_dir.joinpath(name).joinpath("{}.yml".format(name))
        if not filepath.exists():
            for d in ([user_module_dir] + extra_dirs):
                filepath = d.joinpath(name).joinpath("{}.yml".format(name))
                if filepath.exists(): break
        if not filepath.exists() : raise Exception("There is no such module : {}".format(name))
        with open(filepath,'r') as f:
            original=yaml.safe_load(f)
        ui = self.convertTemplate(original['protocol'])

        protoTemplate = self.getProtocolTemplateConfig()
        
        options = self.convertTemplate(protoTemplate['options']['execution']['options'])
        res = {
                'original': original,
                'ui': {
                    'name' : original['name'],
                    'description': original['description'],
                    'protocol' : self.parseDefaultValues(ui),
                    'options' : options
                 }
        }
        return res

    def defaultVariables(self):
        config_dir = self.getConfigDirectory().__str__()

        resMap = {
            '$CONFIG' : config_dir
        }

        return resMap

    def setEnvironmentVars(self):
        os.environ['CONFIG_DIR'] = self.getConfigDirectory().__str__()

    def parseDefaultValues(self,template):
        # default_map = self.defaultVariables()
        self.setEnvironmentVars()
        for idx,v in enumerate(template):
            if 'filepath' in v['type'] or 'dirpath' in v['type']:
                if v['default_value'] is not None:
                    try:
                        template[idx]['default_value'] = os.path.expandvars(v['default_value'])
                    except:
                        pass

        return template
    def convertTemplate(self, template):
        new_proto = []
        for k,v in template.items():
            tmp = v
            tmp.update({'name': k})
            new_proto.append(tmp)
        return new_proto


    def getConfigDirectory(self):
        from dtiplayground.config import INFO
        version = INFO['dmriprep']['version']
        return Path(os.path.expandvars('$HOME')).joinpath('.niral-dti/dmriprep-{}'.format(version));

    def getUserModuleDirectory(self):
        return Path(os.path.expandvars('$HOME')).joinpath('.niral-dti/modules/dmriprep').__str__()

    def getSystemModulePath(self):
        import dtiplayground.dmri.preprocessing.modules as modules
        return Path(modules.__file__).parent.__str__()
