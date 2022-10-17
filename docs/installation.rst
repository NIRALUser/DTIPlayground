Installation
================

We recommend users to make a virtual environment first using python >= 3.8.6

For Windows users, install WSL and linux distribution (tested with ubuntu 20.04, Centos7).

Using command line
~~~~~~~~~~~~~~~~~~~

To install (as root)::

  $ pip install --upgrade dtiplayground

To install (as user)::

  $ pip install --user --upgrade dtiplayground

Using docker container
~~~~~~~~~~~~~~~~~~~~~~~

To install (with Docker)::
    
    $ docker pull niraluser/dtiplayground:latest


Current docker image contains all the necessary tools (FSL/DTIPlaygroundTools) and configurations initialized.

To use the container::

    $ docker run -it --rm -v $PWD:$PWD niraluser/dtiplayground:latest dmriprep [commands]



Install-tools
~~~~~~~~~~~~~
Install DTIPlayground Tools (docker & docker-compose required if custom build is needed)

    $ dmriprep install-tools [-o <output directory>] [--clean-install] [--no-remove] [--nofsl] [--install-only] [--build]

Note
~~~~
Build tested only on CentOS7 for now. However, it would work on most of linux systems. You don't need to install this tools everytime you upgrade dtiplayground.

    $ dmriprep install-tools [-o <output directory>] [--clean-install] [--no-remove] [--nofsl] [--install-only] [--build]

Default output directory is `$HOME/.niral-dti/dtiplayground-tools` if output directory option is omitted
- If `--clean-install` option is present, it removes existing software packages and temporary files first.
- If `--no-remove` option is present, it doesn't remove temporary build files after installation
- If `--nofsl` option is present, it will not install FSL.
- If `--install-only` option is present, it will not update software path file of the configuration of the current version.
- If `--build` option is present, it will build DTIPlaygroundTools with docker (docker required)

Once installed, `$HOME/.niral-dti/global_variables.yml` will have information of the tools including root path of the packages, and automatically changes software paths for the current version of dmriprep unless `--install-only` option is present.


NOTE 
~~~~
Once FSL is installed, some of tools in FSL has hard coded 
path in the script, which means that once FSL directory is 
moved or copied to different directory, some of functions 
will not work (e.g. eddy_quad). You need to re-install FSL 
in that case. But changing directory of FSL doesn't affect 
the functions of DTIPlayground so far.

