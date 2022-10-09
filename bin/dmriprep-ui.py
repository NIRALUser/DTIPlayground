#!python

import sys
from pathlib import Path
import yaml
from yaml.loader import SafeLoader
from PyQt5.QtWidgets import * 
import argparse
import os

sys.path.append(Path(__file__).resolve().parent.parent.__str__()) ## this line is for development

from dtiplayground.ui.dmriprepwindow import Window
import dtiplayground.dmri.preprocessing.templates 
import dtiplayground.config as config

parser = argparse.ArgumentParser()
parser.add_argument("-i", "--image", type=str, help="input image path", nargs="+")
parser.add_argument("-p", "--protocol", type=str, help="protocol file (*.yml) to load")
parser.add_argument("-o", "--output_directory", type=str, help="output directory name")
parser.add_argument("-q", "--quickview", nargs="?", type=bool, default=False, const=True, help="launch QuickView window (need to provide an input image)")
args = parser.parse_args()

source_template_path=Path(dtiplayground.dmri.preprocessing.__file__).parent.joinpath("templates/protocol_template.yml")
protocol_template=yaml.safe_load(open(source_template_path,'r'))

user_directory = os.path.expanduser("~/.niral-dti/dmriprep-" + config.INFO["dmriprep"]["version"])
need_init = False
list_needed_files = [user_directory, 
                     user_directory + "/config.yml",
                     user_directory + "/environment.yml",
                     user_directory + "/log.txt",
                     user_directory + "/parameters", 
                     user_directory + "/protocol_template.yml", 
                     user_directory + "/software_paths.yml"]

for filepath in list_needed_files:
    if not os.path.exists(filepath):
        need_init = True

if need_init:
    os.system("dmriprep init")

app = QApplication(sys.argv)
ex = Window(protocol_template, args)
sys.exit(app.exec_())
