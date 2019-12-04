FROM ubuntu:16.04

# install dependencies from packages
RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -q -y \
        build-essential \
        wget \
        git \
        vim \
        libpq-dev \
	mysql-server \
        libmysqlclient-dev \
        python-dev \
	python-setuptools \
        python-pip \
        dialog \
        net-tools \
	nginx \
        cron

# clone the django site and rename folder
RUN git clone https://github.com/biobakery/jdrf1.git && \
    mv jdrf1/* jdrf1/.git* /usr/local/src/ && \
    rmdir jdrf1

# install python dependencies
RUN pip install --upgrade pip && \
    pip install setuptools && \
    pip install supervisor && \
    pip install django==1.11.0 gunicorn==19.7 MySQL-python==1.2.5 && \
    pip install django-widget-tweaks && \
    pip install fasteners && \
    pip install pronto && \
    pip install whoosh && \
    pip install pendulum && \
    pip install pyyaml

# add supervisor conf
RUN mkdir -pv /var/log/supervisord
ADD etc/supervisor.ini /etc/supervisord.conf

# replace nginx config to proxy gunicorn
RUN rm -v /etc/nginx/nginx.conf
ADD etc/jdrf_nginx.conf /etc/nginx/nginx.conf

# Add our crontab that will check for datasets to be released
ADD etc/crontab /etc/cron.d/jdrf-data-release-cron
RUN chmod 0644 /etc/cron.d/jdrf-data-release-cron
RUN crontab /etc/cron.d/jdrf-data-release-cron
RUN touch /var/log/cron.log

# install workflows dependencies
RUN pip install --no-cache-dir biobakery_workflows==0.13.5 humann2 kneaddata

# install modules needed for validation
RUN pip install pandas && \
    pip install pathlib2 && \
    pip install typing && \
    pip install git+https://github.com/carze/PandasSchema.git && \
    pip install Jinja2 && \
    pip install openpyxl

# install java for kneaddata, numpy for metaphlan2, workflow visualization dependencies, and ldap
# remove texlive docs to save ~330 MB
# install matplotlib version that is compatible with hclust and biobakery workflows (latest version is not)
RUN apt-get update -y && \
    apt-get install -y apt-transport-https openjdk-8-jre python-numpy python-matplotlib \
        python-ldap libsasl2-dev libldap2-dev libssl-dev \
        python-scipy pandoc texlive software-properties-common \ 
        python-pandas python-biopython && \
    apt-get remove -y texlive-fonts-recommended-doc texlive-latex-base-doc \
        texlive-latex-recommended-doc \
        texlive-pictures-doc texlive-pstricks-doc && \
    pip install matplotlib==2.0.0

# install python ldap dependencies
RUN pip install django-auth-ldap

# install panphlan and dependencies
RUN wget https://bitbucket.org/CibioCM/panphlan/get/1.2.tar.gz && \
    tar xzvf 1.2.tar.gz && \
    cp CibioCM-panphlan-b08b5a06deb1/*.py /usr/local/bin/ && \
    rm 1.2.tar.gz && \
    rm -r CibioCM-panphlan-b08b5a06deb1

# install metaphlan2 plus strainphlan and dependencies (plus pre-built database for this version)
RUN wget http://huttenhower.sph.harvard.edu/metaphlan2_downloads/metaphlan2-2.6.0.tar.gz && \
    tar xzvf metaphlan2-2.6.0.tar.gz && \
    mv biobakery-metaphlan2-c43e40a443ed/db_v20 /usr/local/bin/metaphlan_databases && \
    mkdir /usr/local/bin/db_v20 && \
    cp /usr/local/bin/metaphlan_databases/mpa_v20_m200.pkl /usr/local/bin/db_v20/ && \
    rm metaphlan2-2.6.0.tar.gz && \
    rm -r biobakery-metaphlan2-c43e40a443ed
RUN wget https://bitbucket.org/biobakery/metaphlan2/get/2.8.tar.gz && \
    tar xzvf 2.8.tar.gz && \
    mv biobakery-metaphlan2-097a52362c79/*.py /usr/local/bin/ && \
    mv biobakery-metaphlan2-097a52362c79/utils /usr/local/bin/ && \
    mv biobakery-metaphlan2-097a52362c79/strainphlan_src /usr/local/bin/ && \
    cp /usr/local/bin/strainphlan_src/* /usr/local/bin/ && \
    rm 2.8.tar.gz && \
    rm -r biobakery-metaphlan2-097a52362c79 && \
    pip install biom-format msgpack pysam

RUN apt-get update -y && \
    apt-get install -y install raxml muscle ncbi-blast+

RUN wget https://github.com/samtools/samtools/archive/0.1.19.tar.gz && \
    tar xzvf 0.1.19.tar.gz && \
    cd samtools-0.1.19 && \
    make && \
    make -C bcftools && \
    cp samtools bcftools/bcftools bcftools/vcfutils.pl /usr/local/bin/ && \
    cp misc/maq2sam-long misc/maq2sam-short misc/md5fa misc/md5sum-lite misc/wgsim /usr/local/bin/ && \
    cd ../ && \
    rm 0.1.19.tar.gz && \
    rm -r samtools-0.1.19

# Install the latest R
RUN add-apt-repository 'deb https://cloud.r-project.org/bin/linux/ubuntu xenial-cran35/' && \
    gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys E084DAB9 && \
    gpg -a --export E084DAB9 | apt-key add - && \
    apt-get update -y && \
    apt-get install r-base-dev libcurl4-openssl-dev -y && \
    R -q -e "install.packages('vegan', repos='http://cran.r-project.org')"

# install dada2
RUN R -q -e "install.packages('BiocManager', repos='http://cran.r-project.org')" && \
    R -q -e "install.packages('gridExtra', repos='http://cran.r-project.org')" && \
    R -q -e "install.packages('seqinr', repos='http://cran.r-project.org')" && \
    R -q -e "library('BiocManager'); BiocManager::install('dada2', version = '3.9');"

# install hclust2
RUN wget https://bitbucket.org/nsegata/hclust2/get/3d589ab2cb68.tar.gz && \
    tar xzvf 3d589ab2cb68.tar.gz && \
    mv nsegata-hclust2-3d589ab2cb68/hclust2.py /usr/local/bin/ && \
    rm -r nsegata-hclust2-3d589ab2cb68/ && \
    rm 3d589ab2cb68.tar.gz

# install biobakery 16s dependencies (biom, clustalo, ea-utils, fasttree and picrust)
# rollback numpy version for h5py (to prevent future warning message in vis report with biom version)
RUN apt-get update -y && \
    apt-get install -y clustalo ea-utils fasttree && \
    pip install biom-format h5py==2.7.0 cogent==1.5.3 && \
    wget https://github.com/picrust/picrust/releases/download/v1.1.3/picrust-1.1.3.tar.gz && \
    tar -xzf picrust-1.1.3.tar.gz && \
    cd picrust-1.1.3 && \
    pip install . && \
    cd ../ && \
    rm -r picrust-1.1.3* && \
    download_picrust_files.py && \
    pip install numpy==1.13

# generate the whoosh indices we need for the autocomplete in some of the metadata 
# form fields
RUN python /usr/local/src/bin/create_ontology_index.py -i "http://purl.obolibrary.org/obo/envo.owl" \
    -o /opt/whoosh_ontology_indices/envo
RUN python /usr/local/src/bin/create_ontology_index.py -i "http://aber-owl.net/media/ontologies/BTO/33/bto.obo" \
    -o /opt/whoosh_ontology_indices/bto

# install conda
RUN mkdir /usr/local/src/anaconda && \
    wget https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /usr/local/src/anaconda/miniconda.sh && \
    bash /usr/local/src/anaconda/miniconda.sh -b -p /usr/local/src/anaconda/miniconda/ && \
    cp /usr/local/src/anaconda/miniconda/etc/profile.d/conda.sh /etc/profile.d/ && \
    . /usr/local/src/anaconda/miniconda/etc/profile.d/conda.sh

# create picrust2 env
# set up the conda channels
RUN /usr/local/src/anaconda/miniconda/bin/conda config --add channels defaults && \
    /usr/local/src/anaconda/miniconda/bin/conda config --add channels bioconda && \
    /usr/local/src/anaconda/miniconda/bin/conda config --add channels conda-forge && \
    /usr/local/src/anaconda/miniconda/bin/conda config --add channels biobakery && \
    /usr/local/src/anaconda/miniconda/bin/conda create --name picrust_env python=3 picrust2 -c bioconda -y && \
    conda activate picrust_env ; pip install biobakery_workflows==0.13.5 ; conda install bioconductor-dada2 r-gridextra r-seqinr -y ; conda deactivate

EXPOSE :80
