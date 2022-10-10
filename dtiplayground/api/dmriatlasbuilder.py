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

### API
from flask import request, Response , send_from_directory, jsonify
import json
from . import utils
from pathlib import Path
import yaml

from dtiplayground.dmri.atlasbuilder import AtlasBuilder 

class DMRIAtlasbuilderAPI:
    def __init__(self,app,**kwargs):
        self.app=app
        self.initEndpoints()

##### Endpoints

    def initEndpoints(self):
        @self.app.route('/api/v1/dmriatlasbuilder/parameters',methods=['POST'])
        def _post_dmriab_params():
            sc=200
            res=None
            req=None
            request_id=utils.get_request_id()
            try:
                req=request.get_json()
                res= self.generate_parameter_dir(req)
                res= utils.add_request_id(res)
            except Exception as e:
                sc=500
                exc=traceback.format_exc()
                res=utils.error_message("{}\n{}".format(str(e),exc),500,request_id)
            finally:
                resp=Response(json.dumps(res),status=sc)
                resp.headers['Content-Type']='application/json'
                return resp  

        @self.app.route('/api/v1/dmriatlasbuilder',methods=['POST'])
        def _execute_dmriab_params():
            sc=200
            res=None
            req=None
            request_id=utils.get_request_id()
            try:
                req=request.get_json()
                output_dir = req['output_dir']
                res= self.build_atlas(output_dir)
                res= utils.add_request_id(res)
            except Exception as e:
                sc=500
                exc=traceback.format_exc()
                res=utils.error_message("{}\n{}".format(str(e),exc),500,request_id)
            finally:
                resp=Response(json.dumps(res),status=sc)
                resp.headers['Content-Type']='application/json'
                return resp  

    def generate_parameter_dir(self,req):
        params = {
            'output_dir' : req['output_dir'],
            'hbuild' : req['hbuild'],
            'config' : req['config'],
            'greedy' : req['greedy']
        }
        output_dir=Path(params['output_dir'])
        output_dir.mkdir(exist_ok=True,parents=False)
        common_dir = output_dir.joinpath('common')
        common_dir.mkdir(exist_ok=True)

        config_path = common_dir.joinpath('config.yml')
        hbuild_path = common_dir.joinpath('h-build.yml')
        greedy_path = common_dir.joinpath('greedy.yml')

        config = params['config']
        hbuild = params['hbuild']
        greedy = params['greedy']

        ## save config,hbuild
        yaml.safe_dump(config, open(config_path,'w'))
        yaml.safe_dump(hbuild, open(hbuild_path,'w'))
        yaml.safe_dump(greedy, open(greedy_path,'w'))

        return params

    def build_atlas(self, configured_dir):

        output_dir=Path(configured_dir)
        config_path=output_dir.joinpath('common/config.yml')
        hbuild_path=output_dir.joinpath('common/h-build.yml')
        greedy_path=output_dir.joinpath('common/greedy.yml')
        bldr=AtlasBuilder()
        bldr.configure( output_dir=output_dir,
                        config_path=config_path,
                        hbuild_path=hbuild_path,
                        greedy_path=greedy_path)
       
        bldr.build()

        res = { 'task_id' : utils.get_uuid()}
        return res