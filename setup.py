import sys,os
from setuptools import setup, find_packages
import subprocess
from os.path import join as pjoin, dirname, exists
from glob import glob
from dtiplayground.config import INFO as info

def install_conda_packages():
    '''
    We are using the conda flag -c to specify the channel so please add the channel
    and package_name as a string seperated by a space. Please pass -y at the end
    '''
    conda_packages = [
        ["mrtrix3", "mrtrix3", '-y']
    ]
    try:
        print("Checking for Conda dependencies...")
        for packages in conda_packages:
            subprocess.run(["conda", "install", "-c"] + packages, check=True)
    except subprocess.CalledProcessError:
        print("Error installing Conda packages. Please install them manually.")

def is_conda_env():
    return "CONDA_PREFIX" in os.environ

if is_conda_env():
    install_conda_packages()
else:
    print("Warning: You are not in a Conda environment. Some dependencies may fail to install.")

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
        'dipy>=1.6.0',
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
        'dmri-amico',
        'mrtrix3'
       ],

 )

