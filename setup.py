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
    url='https://github.com/niraluser/dtiplayground',
    keywords=['dtiplayground','dmriprep','dmriatlas','dmriautotract','dmrifiberprofile','nrrd','nifti','dwi','dti','qc','quality control'],
    install_requires=[
        'cmake==3.24.1',
        'pynrrd==0.4.2',
        'dipy==1.4.0',
        # 'fury==0.7.0',
        # 'fury',
        'pyyaml==5.3.1',
        'nibabel==3.2.1',
        'tensorflow==2.8.0',
        'antspyx==0.3.2', #0.3.3 and above has some build issue
        'antspynet==0.1.8',
        'pandas==1.4.3',
        'pyqt5',
        # 'simpleitk==2.1.1',
        'simpleitk',
        'reportlab==3.6.6',
        'pypdf2==1.26.0',
        'markdown==3.3.6',
        'xhtml2pdf==0.2.7'
       ],

 )

