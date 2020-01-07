#
"""
Checks all datasets in the specified JDRF data folder to verify whether or 
not the dataset should be moved to interal release or flagged for public release.

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


def get_all_archived_data_sets(archive_folder):
    """ Retrieve all archived folders and return a list of dictionaries 
    containing path to folder, owner email, study_name and date archived.
    """
    archived_datasets = defaultdict(list)
    study_sort = lambda d: re.split(r'_\d+_\d+_\d{4}', os.path.basename(d))[0]

    data_dirs = list(filter(lambda d: os.path.isdir(d), glob.glob("%s/*/*" % archive_folder)))
    data_dirs = list(filter(lambda d: "public" not in d, data_dirs))
    data_dirs = list(filter(lambda d: "demo" not in d, data_dirs))
    data_dirs = list(filter(lambda d: "test" not in d, data_dirs))
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

        archived_datasets[user].append({'study': study_name, 
                                        'dirs': archived_dirs, 
                                        'user_email': user_info.get('email'), 
                                        'name': user_info.get('name'),
                                        'archive_date': archive_dt})

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
            user_name = dataset.get('name').encode('ascii', errors='ignore')
            dataset_dirs = dataset.get('dirs')
            archive_dt = dataset.get('archive_date')

            datasets_status.setdefault(user_email, [])

            public_release_dt = archive_dt.add(months=public_release)
            internal_release_dt = archive_dt.add(months=internal_release)

            days_to_public = (public_release_dt - current_dt).days
            days_to_internal = (internal_release_dt - current_dt).days
            datasets_status[user_email].append([user_name, study, dataset_dirs,
                                                {'public': max(0, days_to_public),
                                                 'internal': max(0, days_to_internal)}])

    return datasets_status


def send_dataset_notifications(dataset_status):
    """Iterates over the collection of datasets and their release status and 
    send out emails for any datasets that have hit public or internal milestones 
    and for remaining datasets will send a status update if the current day matches
    the specified day to send email report out.
    """
    release_msg = "".join([
                   "Hello {0}!\n\nThis is an automated message ",
                   "to inform you that the following datasets are ",
                   "set to be released in the following days.\n\n",
                   "Internal:\n{1}\n\n",
                   "Public:\n{2}",
                   "\n\n** Datasets pending internal and external release (ie 0 days to release) will not be released without PI approval **",
                   "\n\nPlease feel free to email the JDRF MIBC staff ",
                   "if you have any questions regarding the data release ",
                   "policy.\n\nThank You!\nThe JDRF MIBC team"])

    for (email, datasets) in dataset_status.iteritems():
        internal_release_dates = "   - " + "\n   - ".join(["{0}: {1} days to release".format(d[1], d[3].get('internal')) for d in datasets])
        public_release_dates = "   - " + "\n   - ".join(["{0}: {1} days to release".format(d[1], d[3].get('public')) for d in datasets])

        user_name = datasets[0][0]
        custom_release_msg = release_msg.format(user_name, internal_release_dates, public_release_dates)
        #send_email_update("Data Release Update %s - %s" % (pendulum.now().to_formatted_date_string(), user_name), custom_release_msg, to=email)


archived_datasets = get_all_archived_data_sets(settings.ARCHIVE_FOLDER)
# With all our datasets we want to bucket them into three bins by user: 
#
#       1.) Datasets that haven't hit internal or public release time limit
#       2.) Datasets that hit internal but not public release time limit
#       3.) Datasets that have hit public release time limit
dataset_status = check_datasets_release_status(archived_datasets, settings.RELEASE_PUBLIC_MONTHS, 
                                               settings.RELEASE_INTERNAL_MONTHS)
send_dataset_notifications(dataset_status)
