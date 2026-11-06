import sys,os,re
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
        python_requires=">= 3.11",
        )


## project description on PyPI: the README, with its links to files of the repository made absolute
with open(pjoin(dirname(os.path.abspath(__file__)), 'README.md'), encoding='utf-8') as f:
    long_description = re.sub(r'\]\((?!https?:|#)([^)]+)\)', r'](https://github.com/NIRALUser/DTIPlayground/blob/master/\1)', f.read())

setup(
    name='dtiplayground',
    version=info['dtiplayground']['version'],
    python_requires=">=3.11",
    license='MIT',
    description='NIRAL pipeline software for diffusion MRI: preprocessing and quality control, fiber profile analysis, atlas building',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author="Martin Styner, SK Park, NIRAL, University of North Carolina @ Chapel Hill",
    author_email='styner@unc.edu',
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
        ## numpy 2: the lower bounds of the compiled packages are their first releases built for numpy 2, so that pip
        ## upgrades them in an environment that has older builds; the upper bounds keep untested major releases out.
        ## requirements.txt pins the exact tested versions
        'numpy>=1.26,<3',
        'scipy>=1.15', ## impute-profiles linear: older LinearNDInterpolator re-triangulates and fails on flat point sets
        'pynrrd>=1.1.1,<2', ## 1.0.0 imports nptyping, which fails with numpy 2
        'dipy>=1.12,<2', ## 1.12 needs Python 3.11+
        'h5py>=3.11', ## used by dipy and dmri-amico; older builds fail with numpy 2 and dipy only asks for >=3.1
        'pyyaml>=5.3.1',
        'nibabel>=5.2.1,<6',
        'opencv-python-headless>=4.10.0.84',
        'simpleitk>=2.4',
        'xhtml2pdf',
        'flask',
        'flask_cors',
        'flask_jwt_extended',
        'vtk>=9.4', ## fiber file reading/writing (fiber profiles, BRAIN_Tractography)
        ## fiber profile analysis tools (dmrifiberprofile impute / qc-registration / qc-profiles)
        'torch>=2.3',
        'matplotlib>=3.8.4',
        'scikit-image>=0.24',
        'scikit-learn>=1.4.2',
        'markdown',
        'reportlab',
        'pandas>=2.2.2,<4',
        'dmri-amico>=2.1.1', ## 2.1.0 imports pkg_resources, which newer setuptools no longer provide
       ],

 )

