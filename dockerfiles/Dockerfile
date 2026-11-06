FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt update
RUN apt install -y build-essential
RUN apt install -y python3-pip python3-dev python3-venv
RUN apt install -y git
RUN apt install -y libgl1
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
## Python 3.12 of Ubuntu 24.04 (dipy 1.12 needs 3.11+); the system Python refuses pip installs (PEP 668), so use a venv
RUN python3 -m venv /opt/dtiplayground
ENV PATH=/opt/dtiplayground/bin:$PATH
RUN pip install --upgrade pip packaging
## dependency pins match requirements.txt
RUN pip install --upgrade dtiplayground==0.9.6 numpy==2.4.6 dipy==1.12.1 nibabel==5.4.2 pandas==3.1.1 pynrrd==1.1.3
ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib
RUN chmod 777 -R /root
EXPOSE 6543
ENTRYPOINT ["dmriplayground","serve","--host","0.0.0.0","-p","6543"]