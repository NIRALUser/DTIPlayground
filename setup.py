import sys,os
from setuptools import setup, find_packages
import json
from os.path import join as pjoin, dirname, exists
from glob import glob

from dtiplayground.config import INFO as info

using_setuptools = 'setuptools' in sys.modules
extra_setuptools_args = {}

if using_setuptools:
    # Set setuptools extra arguments
    extra_setuptools_args = dict(
        tests_require=[],
        zip_safe=False,
        python_requires=">= 3.8",
        )

    
setup(
    name='dtiplayground',
    version=info['dtiplayground']['version'],
    python_requires=">=3.8",
    license='MIT',
    author="SK Park, NIRAL, University of North Carolina @ Chapel Hill",
    author_email='scalphunter@gmail.com',
    packages=find_packages('.'),
    package_dir={'': '.'},
    package_data = {
    '': ['*.yml','*.yaml','*.json','*.cnf'],
    },
    scripts=glob(pjoin('bin', '*')),
    # data_files=[('', glob(pjoin('dtiplayground/dmri/common/data','*.*'))),
    #             ('', glob(pjoin('dtiplayground/dmri/preprocessing/templates','*.*'))),
    #             ],
    url='https://github.com/niraluser/dtiplayground',
    keywords='dtiplayground',
    install_requires=[
        'pynrrd==0.4.2',
        'dipy==1.4.0',
        'pyyaml==5.3.1',
        'nibabel==3.2.1',
        'tensorflow==2.8.0',
        'antspynet==0.1.2',
        'pyqt5',
        'simpleitk==2.1.1',
        'reportlab==3.6.6',
        'pypdf2==1.26.0'
       ],

 )

