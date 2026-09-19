import sys,os
from setuptools import setup, find_packages
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
        python_requires=">= 3.9",
        )

    
setup(
    name='dtiplayground',
    version=info['dtiplayground']['version'],
    python_requires=">=3.9",
    license='MIT',
    author="SK Park, NIRAL, University of North Carolina @ Chapel Hill",
    author_email='scalphunter@gmail.com',
    packages=find_packages('.'),
    package_dir={'':'.'},
    package_data = {
    '': ['*.yml','*.yaml','*.json','*.xml','*.cnf','*.md','*.zip','LICENSE.freesurfer.txt']
    },
    scripts=glob(pjoin('bin', '*')),
    url='https://github.com/niraluser/dtiplayground',
    keywords=['dtiplayground','dmriprep','dmriatlas','dmriautotract','dmrifiberprofile','nrrd','nifti','dwi','dti','qc','quality control'],
    install_requires=[
        'wheel',
        'cmake>=3.24.1',
        ## upper bounds avoid numpy 2.x and newer releases that caused run issues;
        ## requirements.txt pins the exact tested versions
        'pynrrd>=1.0.0,<2',
        'dipy>=1.6.0,<1.10',
        'pyyaml>=5.3.1',
        'nibabel>=5.0.0,<6',
        'opencv-python-headless',
        'simpleitk>=2.1.1',
        'xhtml2pdf',
        'flask',
        'flask_cors',
        'flask_jwt_extended',
        'numpy>=1.21,<2',
        'fury>=0.10.0,<0.13', ## needed by dipy to save tract files (BRAIN_Tractography)
        'vtk>=9.1', ## fiber file reading/writing (fiber profiles)
        ## fiber profile analysis tools (dmrifiberprofile impute / qc-registration / qc-profiles)
        'torch>=2.1',
        'matplotlib>=3.7',
        'scikit-image>=0.21',
        'scikit-learn>=1.3',
        'scipy>=1.10',
        'markdown',
        'reportlab',
        'pypdf2',
        'pandas>=1.4,<3',
        'dmri-amico>=2.1.1', ## 2.1.0 imports pkg_resources, which newer setuptools no longer provide
       ],

 )

