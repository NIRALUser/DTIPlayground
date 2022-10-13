import os 
from pathlib import Path
import traceback
import sys

from flask import Flask
from flask import send_from_directory
from flask_cors import CORS


import dtiplayground
import dtiplayground.dmri.common as common
from dtiplayground.config import INFO as info

logger=dtiplayground.dmri.common.logger.write 
color= dtiplayground.dmri.common.Color

### APIs
from dtiplayground.api.filebrowser import FileBrowserAPI 
from dtiplayground.api.dmriatlasbuilder import DMRIAtlasbuilderAPI
from dtiplayground.api.dmriprep import DMRIPrepAPI

class DTIPlaygroundServer(object):
    def __init__(self,*args,**kwargs):
        self.host = '127.0.0.1'
        self.port = '6543'
        self.static_folder = None
        self.static_url_path='/'
        self.app = None

    def configure(self, host, port, static_folder = None , static_url_path='/'):

        self.host=host
        self.port=port
        self.static_folder=static_folder
        self.static_url_path = static_url_path

        self.app=Flask(__name__, static_folder=self.static_folder, static_url_path=self.static_url_path)
        CORS(self.app)

        self.app.config['SUBMODULES']={}
        self.app.config['SUBMODULES']['FileBrowserAPI']=FileBrowserAPI(self.app)
        self.app.config['SUBMODULES']['DMRIAtlasbuilderAPI']=DMRIAtlasbuilderAPI(self.app)
        self.app.config['SUBMODULES']['DMRIPrepAPI']=DMRIPrepAPI(self.app)

        @self.app.route('/', defaults={'path': ''})
        @self.app.route('/<path>') ## for routers
        def catch_all(path):
            return self.app.send_static_file("index.html")


    def get_app(self): ## for UWSGI
        return self.app

    def serve(self):
        if not self.app: raise Exception('Flask app is not configured')
        self.app.run(host=self.host, port=self.port,debug=True)

