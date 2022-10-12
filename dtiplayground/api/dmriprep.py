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

from dtiplayground.dmri.atlasbuilder import AtlasBuilder 
import  dtiplayground.dmri.common as common

class DMRIPrepAPI:
    def __init__(self,app,**kwargs):
        self.app=app
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
                output_dir = req['output_dir']
                res= self.run(output_dir)
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

        return req

    def run(self, configured_dir):

        res = { 'task_id' : utils.get_uuid()}
        return res

    def getProtocolTemplateConfig(self):
        config_dir = self.getConfigDirectory();
        ptc_fn = config_dir.joinpath('protocol_template.yml')
        with open(ptc_fn,'r') as f:
            ptc = yaml.safe_load(f)
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

        ui = self.convertTemplate(original)
        res = {
                'original': original,
                'ui': ui
        }
        return res

    def convertTemplate(self, template):
        new_proto = []
        for k,v in template['protocol'].items():
            tmp = v
            tmp.update({'name': k})
            new_proto.append(tmp)
        template['protocol']=new_proto
        return template


    def getConfigDirectory(self):
        from dtiplayground.config import INFO
        version = INFO['dmriprep']['version']
        return Path(os.path.expandvars('$HOME')).joinpath('.niral-dti/dmriprep-{}'.format(version));

    def getUserModuleDirectory(self):
        return Path(os.path.expandvars('$HOME')).joinpath('.niral-dti/modules/dmriprep').__str__()

    def getSystemModulePath(self):
        import dtiplayground.dmri.preprocessing.modules as modules
        return Path(modules.__file__).parent.__str__()