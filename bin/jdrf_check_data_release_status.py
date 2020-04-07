#
"""
Checks all datasets in the specified JDRF data folder to verify whether or 
not the dataset should be moved to internal release or flagged for public release.

In the case of a dataset not yet hitting either release status (or if ready for release)
the owner of the dataset will be notified how many days until internal release, public release 
or when either of these states is hit.
"""


import argparse
import glob
import os
import pwd
import re
import sys

from collections import defaultdict
from itertools import groupby
from yaml import safe_load

import django
import pendulum
import csv

# Setup up django outside of the environment 
JDRF_INSTALL_PATH=os.path.join(os.path.abspath(os.path.join(os.path.realpath(__file__), os.pardir, os.pardir)), 'jdrf')
sys.path.append(JDRF_INSTALL_PATH)
os.environ['DJANGO_SETTINGS_MODULE'] = 'jdrf.settings'
django.setup()

from django.contrib.auth.models import User
from django.conf import settings
from jdrf.process_data import send_email_update


def get_contact_info(archive_dir):
    """ Retrieve user email and user first name given an archive directory.
    """
    user_manifest_file = os.path.join(os.path.dirname(archive_dir), 'MANIFEST')
    with open(user_manifest_file) as manifest:
       user_info = safe_load(manifest)
    return user_info

def get_PI_email(metadata_study_path):
    """ Retrieve PI email from archive directory metadatastudy.tsv file.
    """
    with open(metadata_study_path) as user_metadata:
        csv_reader = csv.DictReader(user_metadata, delimiter=',')
        for rows in csv_reader:
            PI_email = rows['pi_email']
            PI_name = rows['pi_name']
        return PI_email,PI_name

def get_all_archived_data_sets(archive_folder):
    """ Retrieve all archived folders and return a list of dictionaries 
    containing path to folder, owner email, study_name and date archived.
    """
    archived_datasets = defaultdict(list)
    study_sort = lambda d: re.split(r'_\d+_\d+_\d{4}', os.path.basename(d))[0]

    data_dirs = list(filter(lambda d: os.path.isdir(d), glob.glob("%s/*/*" % archive_folder)))
    data_dirs = list(filter(lambda d: "public" not in d, data_dirs))
    data_dirs = list(filter(lambda d: "demo" not in d.lower(), data_dirs))
    data_dirs = list(filter(lambda d: "test" not in d.lower(), data_dirs))
    data_dirs = sorted(data_dirs, key=study_sort)

    for (study_name, study_dirs) in groupby(data_dirs, study_sort):
        archived_dirs = list(study_dirs)

        # Grab the users email
        user = archived_dirs[0].split(os.sep)[3]

        if user in ["root", "carze", "ljmciver", "kbonham", "smaharjan"]:
            continue

        user_info = get_contact_info(archived_dirs[0])

        # Now get the date that this data was archived
        match = re.search(r'\d+_\d+_\d{4}', os.path.basename(archived_dirs[0]))
        archive_date = match.group()
        current_dt = pendulum.now()
        archive_dt = pendulum.from_format(archive_date, 'MM_D_YYYY')

        metadata_study_file_path = os.path.join(archive_folder,user,study_name+'_'+archive_date+'_uploaded','metadata',settings.METADATA_GROUP_FILE_NAME)
        internal_release_complete = False
        # checking for the dot file to determine if a data set has been internally released
        if os.path.isfile(os.path.join(os.path.dirname(metadata_study_file_path), settings.INTERNAL_RELEASE_DOT_FILE)):
            internal_release_complete = True

        PI_email, PI_name = get_PI_email(metadata_study_file_path)

        user_info.update(PI_email = PI_email)
        user_info.update(PI_name = PI_name)
        archived_datasets[user].append({'study': study_name, 
                                        'dirs': archived_dirs, 
                                        'user_email': user_info.get('email'), 
                                        'PI_email': user_info.get('PI_email'),
                                        'name': user_info.get('name'),
                                        'archive_date': archive_dt,
                                        'internal_release_complete': internal_release_complete, 
                                        'PI_name': user_info.get('PI_name')})


    return archived_datasets


def check_datasets_release_status(datasets, public_release, internal_release):
    """ Checks whether or not the passed in datasets meet any of the release 
    criteria specified. Release criteria should be passed in as months milestones 
    that must be hit before a dataset is released.
    """
    datasets_status = defaultdict(dict)
    current_dt = pendulum.now()

    for (username, datasets) in datasets.iteritems():
        for dataset in datasets:
            study = dataset.get('study').encode('ascii', errors='ignore')
            user_email = dataset.get('user_email')
            PI_email = dataset.get('PI_email')
            PI_name = dataset.get('PI_name')
            user_name = dataset.get('name').encode('ascii', errors='ignore')
            dataset_dirs = dataset.get('dirs')
            archive_dt = dataset.get('archive_date')
            internal_release_complete = dataset.get('internal_release_complete')

            public_release_dt = archive_dt.add(months=public_release)
            internal_release_dt = archive_dt.add(months=internal_release)
            days_to_public = (public_release_dt - current_dt).days
            days_to_internal = (internal_release_dt - current_dt).days

            datasets_status.setdefault(PI_email, [])      
                                        

            datasets_status[PI_email].append([user_name, user_email, study, dataset_dirs,
                                                {'public': max(0, days_to_public),
                                                 'internal': max(0, days_to_internal)}, internal_release_complete, PI_name])

    return datasets_status


def send_dataset_notifications(dataset_status):
    """Iterates over the collection of datasets and their release status and 
    send out emails for any datasets that have hit public or internal milestones 
    and for remaining datasets will send a status update if the current day matches
    the specified day to send email report out.
    """
    release_msg = "".join([
                   "Hello Dr. {0},",
                   "\n\n",
                   "Thank you for depositing data with the MIBC! ",
                   "We are reaching out because some of the data you have deposited ",
                   "is ready for (internal/external) release. Please see below for ",
                   "more information and MIBC's data release policies.",
                   "\n\n",
                   "The JDRF has a data release policy based on the date each dataset ",
                   "is generated and deposited. Six months after deposition, data is ",
                   "set to be released internally (available ONLY to the JDRF MIBC ",
                   "consortium members) and a year later (18 months after deposition) ",
                   "the data is set to be released externally (publicly downloadable from ",
                   "the JDRF MIBC site and released to the SRA/GEO/etc. as appropriate).",
                   "\n\n",
                   "** The JDRF MIBC will only release data once the release date is ",
                   "approved by the primary investigator. **",
                   "\n\n",
                   "If one of your data sets below has 0 days to release (or is close), ",
                   "please reach out to us (reply ALL to this email) to let us know if ",
                   "you are or when you will be ready for the data to be released.",
                   "\n\n",
                   "{1}",
                   "{2}",
                   "\n\n",
                   "Please email the JDRF MIBC team (cced on this email) if you have any ",
                   "questions regarding the data release policy.",
                   "\n\n",
                   "Thank You,",
                   "\n",
                   "The JDRF MIBC team"])

    for (email, datasets) in dataset_status.iteritems():
        if not datasets[0][5]:
            internal_release_dates = "Internal:\n{0}\n\n".format("   - " + "\n   - ".join(["{0}: {1} days to release".format(d[2], d[4].get('internal')) for d in datasets]))
        else:
            internal_release_dates = ""

        public_release_dates = "Public(External Release):\n{0}".format("   - " + "\n   - ".join(["{0}: {1} days to release".format(d[2], d[4].get('public')) for d in datasets]))
        

        user_name = datasets[0][6]
        user_email = datasets[0][1]
        custom_release_msg = release_msg.format(user_name, internal_release_dates, public_release_dates)
        send_email_update("Data Release Update %s - %s" % (pendulum.now().to_formatted_date_string(), user_name), custom_release_msg, to=email, cc=user_email)


archived_datasets = get_all_archived_data_sets(settings.ARCHIVE_FOLDER)
# With all our datasets we want to bucket them into three bins by user: 
#
#       1.) Datasets that haven't hit internal or public release time limit
#       2.) Datasets that hit internal but not public release time limit
#       3.) Datasets that have hit public release time limit
dataset_status = check_datasets_release_status(archived_datasets, settings.RELEASE_PUBLIC_MONTHS,
                                    settings.RELEASE_INTERNAL_MONTHS)
send_dataset_notifications(dataset_status)
