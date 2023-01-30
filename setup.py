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
    package_dir={'':'.'},
    package_data = {
    '': ['*.yml','*.yaml','*.json','*.xml','*.cnf','*.md','*.zip']
    },
    scripts=glob(pjoin('bin', '*')),
    url='https://github.com/niraluser/dtiplayground',
    keywords=['dtiplayground','dmriprep','dmriatlas','dmriautotract','dmrifiberprofile','nrrd','nifti','dwi','dti','qc','quality control'],
    install_requires=[
        'wheel',
        'cmake>=3.24.1',
        'pynrrd>=0.4.2',
        'dipy>=1.4.0',
        'pyyaml>=5.3.1',
        'nibabel>=3.2.1',
        'opencv-python-headless',
        'simpleitk>=2.1.1',
        'xhtml2pdf',
        'flask',
        'flask_cors',
        'flask_jwt_extended',
        'numpy',
        'fury',
        'markdown',
        'reportlab',
        'pypdf2',
        'pandas',
       ],

 )

