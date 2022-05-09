#!python

import sys
from pathlib import Path
import yaml
from yaml.loader import SafeLoader
from PyQt5.QtWidgets import * 
import argparse

sys.path.append(Path(__file__).resolve().parent.parent.__str__()) ## this line is for development

from dtiplayground.ui.dmriprepwindow import Window
import dtiplayground.dmri.preprocessing.templates 
#sys.path.append("/BAND/USERS/skp78-dti/dtiplayground/dtiplayground")
#sys.path.append("dtiplayground")

parser = argparse.ArgumentParser()
parser.add_argument("-i", "--image", type=str, help="input image path", nargs="+")
parser.add_argument("-p", "--protocol", type=str, help="protocol file (*.yml) to load")
parser.add_argument("-o", "--output_directory", type=str, help="output directory name")
parser.add_argument("-q", "--quickview", nargs="?", type=bool, default=False, const=True, help="launch QuickView window (need to provide an input image)")
args = parser.parse_args()

source_template_path=Path(dtiplayground.dmri.preprocessing.__file__).parent.joinpath("templates/protocol_template.yml")
protocol_template=yaml.safe_load(open(source_template_path,'r'))

app = QApplication(sys.argv)
ex = Window(protocol_template, args)
sys.exit(app.exec_())
