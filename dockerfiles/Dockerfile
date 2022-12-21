FROM ubuntu:20.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt update
RUN apt install -y build-essential
RUN apt install -y python3-pip python3-dev
RUN apt install -y qt5-default
RUN apt install -y git
RUN pip install packaging
RUN pip install --upgrade dtiplayground==0.5.2
RUN pip uninstall -y dtiplayground
RUN pip install opencv-python
