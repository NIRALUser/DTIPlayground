import sys,os
from setuptools import setup, find_packages
import json

info={}
with open('info.json') as f:
    info = json.load(f)
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
    version=info['version'],
    license='MIT',
    author="SK Park, NIRAL, University of North Carolina @ Chapel Hill",
    author_email='scalphunter@gmail.com',
    packages=find_packages('.'),
    package_dir={'': '.'},
    url='https://github.com/niraluser/dtiplayground',
    keywords='dtiplayground',
    install_requires=[
        'pynrrd==0.4.2',
        'dipy==1.4.0',
        'pyyaml==5.3.1',
        'nibabel==3.2.1',
        'tensorflow==2.7.0',
        'antspynet==0.1.2'
      ],

)