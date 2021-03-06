# JDRF1 MIBC #

This repository contains the source and configuration for the JDRF1 MIBC site.

The JDRF1 site is the data depository. This site hosts raw data and metadata uploads.

### Install ###

1. Install [Docker](https://www.docker.com/).
2. Clone or download a copy of this repository.
3. Change directories to the main folder of this repository.
4. Edit the secret keys/passwords (in ``keys.env`` to customize your setup).
5. Edit the settings file (in ``jdrf/jdrf/settings.py`` to add your host name).
6. Build a Docker image containing all dependencies for the site.

    a. ``$ sudo docker build -t jdrf1_mibc ./``

7. Create a container from the image (mapping port 80 to 80), start it, and connect to it

    a. ``$ sudo docker run -itd --env-file keys.env -p 80:80 --name jdrf1_mibc_container jdrf1_mibc bash``

    b. ``$ sudo docker exec -it jdrf1_mibc_container bash``
    
8. From in the container, first run the configuration script to start services running in the container and to setup the environment. Then run gunicorn to start the site. Then create symlinks to the usearch software and update the configuration for the humann2 databases.

    a. ``$ cd /usr/local/src/jdrf``
    
    b. ``$ bash config.bash`` (run the configuration script)

    c. ``$ nohup gunicorn --bind 127.0.0.1:8000 jdrf.wsgi &``

    d. ``$ ln -s /opt/usearch/usearch8_64 /usr/local/bin/usearch``

    e. ``$ humann2_config --update database_folders protein /opt/biobakery_workflows_databases/humann2/uniref/``

    f. ``$ humann2_config --update database_folders nucleotide /opt/biobakery_workflows_databases/humann2/chocophlan/``

    g. ``$ humann2_config --update database_folders utility_mapping /opt/biobakery_workflows_databases/humann2/utility_mapping/``
    

To stop the container run ``$ sudo docker stop jdrf1_mibc_container``.

