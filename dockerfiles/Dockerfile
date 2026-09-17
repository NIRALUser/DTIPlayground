FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt update
RUN apt install -y build-essential
RUN apt install -y python2
RUN apt install -y python3-pip python3-dev
RUN apt install -y git
RUN apt install -y libgl1-mesa-glx
RUN apt install -y libglib2.0-0 libsm6 libxrender1 libxext6
RUN apt install -y libjpeg62 libpng-dev zlib1g-dev
RUN apt install -y wget
WORKDIR /root
RUN wget https://sourceforge.net/projects/libpng/files/libpng15/older-releases/1.5.15/libpng-1.5.15.tar.gz
RUN tar xvfz libpng-1.5.15.tar.gz
WORKDIR /root/libpng-1.5.15
RUN ./configure
RUN make install
WORKDIR /
RUN pip install packaging
## dependency pins match requirements.txt; install them in the same command so dependencies can't upgrade numpy to 2.x
RUN pip install --upgrade dtiplayground==0.7.7 numpy==1.26.4 dipy==1.9.0 nibabel==5.2.1 pandas==2.2.2 pynrrd==1.0.0
ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib
RUN chmod 777 -R /root
EXPOSE 6543
ENTRYPOINT ["dmriplayground","serve","--host","0.0.0.0","-p","6543"]