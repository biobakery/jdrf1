
import os
import sys
import subprocess

import pandas

IGNORE_NAMES = ["huttenhower","arze","ljmciver","demo","test","smaharjan"]

METADATA_FOLDER = "metadata"
METADATA_FILE_NAME = "metadata.tsv"
METADATA_STUDY_FILE_NAME = "metadata_study.tsv"
METADATA_UPDATE_FILE_NAME = "metadata_manual_updates.tsv"

DEFAULT_TYPE = "UNK"

EXTERNAL_RELEASE = 18
INTERNAL_RELEASE = 6

taxid_to_host = {"9606":"human", "10090": "mouse"}

COUNT_FILE = sys.argv[1]
PUBLIC_COUNT_FILE = sys.argv[2]

ARCHIVE_FOLDER = os.path.dirname(COUNT_FILE)

def add_months(date_years,date_months,months_to_add):
    """ Add total months to date """

    date_years = int(date_years)
    date_months = int(date_months)

    if months_to_add > 12:
        date_years += 1
        months_to_add -= 12

    if date_months + months_to_add > 12:
        date_years += 1
        months_to_add -= 12
       
    date_months += months_to_add

    return str(date_years), str(date_months)

def update_metadata(file, id, original_value):
    """ Check the manual updates file to determine if there is a new value for this metadata """

    try:
        updated_data_frame = pandas.read_csv(file, keep_default_na=False)
        new_value = updated_data_frame[id][0]
    except (KeyError, EnvironmentError, AttributeError):
        new_value = original_value

    return new_value

def get_study_metadata(study_file):
    """ Parses study metadata file and returns a pandas DataFrame representation of metadata 
        Use the same method as the site uses to parse this file """

    try:
        data_frame = pandas.read_csv(study_file, keep_default_na=False).ix[0]
    except IOError:
        data_frame = None

    try:
        if data_frame.sample_type == "":
            data_frame.sample_type = DEFAULT_TYPE

        return data_frame.pi_name, data_frame.sample_type, data_frame.study_id
    except (KeyError, ValueError, AttributeError):
        return ("","","")

def get_metadata(file):
    """ Read in the total number of samples and host"""

    # set defaults
    total_samples = 0
    host = DEFAULT_TYPE    

    try:
        data_frame = pandas.read_csv(file, keep_default_na=False) 
        total_samples = len(list(set(data_frame['sample_id'])))
        taxid = data_frame['subject_tax_id'][0]
        host = taxid_to_host.get(str(taxid), DEFAULT_TYPE)
    except (KeyError, EnvironmentError, AttributeError):
        pass

    # check for update to host value
    updated_file = os.path.join(os.path.dirname(file),METADATA_UPDATE_FILE_NAME)
    host = taxid_to_host.get(str(update_metadata(updated_file,'subject_tax_id', host)), host)

    return total_samples, host

def count_total_data(metadata_file):
    """ Count the total number of data sets included """

    try:
        total_data = int(len(open(metadata_file).readlines()))-1
    except EnvironmentError:
        total_data = 0

    return total_data

def get_deposition_date(project_folder):
    """ Get the deposition date from the project folder name """

    info = project_folder.split("_")
    date = ["-".join([info[-2],info[-4],info[-3]])]
    for release in (INTERNAL_RELEASE,EXTERNAL_RELEASE):
        new_years, new_months = add_months(info[-2],info[-4],release)
        date.append("-".join([new_years,new_months,info[-3]]))
    return date

def get_size(project_folder):
    """ Get the size of the data set """

    try:
        size = subprocess.check_output(["du","-sc",project_folder,"--block-size","M"]).strip().split("\t")[0]
    except EnvironmentError:
        size = 0
    return size

def to_GB(size):
    """ If larger than 1 GB, convert to GB"""

    size_int = size
    if not isinstance(size,int):
        try:
            size_int = int(size.replace("M",""))
        except ValueError:
            size_int = 0

    if size_int > 1024:
        size_int = int(size_int / 1024.0)
        size = str(size_int)+"G"
    else:
        size = str(size_int)+"M"

    return size

def demo_study(pi_name,study_name,user):
    """ Check if this is a test or demo run """

    demo = False
    if not pi_name:
        demo = True
    if pi_name.lower() in IGNORE_NAMES:
        demo = True
    if study_name.lower() in IGNORE_NAMES:
        demo = True
    for name in IGNORE_NAMES:
        if name in study_name.lower():
            demo = True
    if user in IGNORE_NAMES:
        demo = True

    return demo

# for each user folder, count the projects
counts = {}
public_counts = {}
for user in os.listdir(ARCHIVE_FOLDER):
    user_folder = os.path.join(ARCHIVE_FOLDER,user)
    if os.path.isdir(user_folder):
        for project_folder in os.listdir(user_folder):
            # only use the upload folders
            if "upload" in project_folder:
                metadata_study_file = os.path.join(user_folder,project_folder,METADATA_FOLDER,METADATA_STUDY_FILE_NAME)        
                metadata_file = os.path.join(user_folder,project_folder,METADATA_FOLDER,METADATA_FILE_NAME)

                total_data_files = count_total_data(metadata_file)        
                total_samples, host = get_metadata(metadata_file)
                pi_name, sample_type, study_name = get_study_metadata(metadata_study_file)
                date = get_deposition_date(project_folder)            
                size = get_size(os.path.join(user_folder,project_folder))

                if not demo_study(pi_name,study_name,user):
                    if not pi_name in counts:
                        counts[pi_name]={}
                    if not sample_type in counts[pi_name]:
                        counts[pi_name][sample_type]={}
                    counts[pi_name][sample_type][study_name]=[user, host, total_samples, to_GB(size)]+date

                    if not sample_type in public_counts:
                        public_counts[sample_type]={}
                    if not host in public_counts[sample_type]:
                        public_counts[sample_type][host]=[0,0]
                    public_counts[sample_type][host]=[public_counts[sample_type][host][0]+int(total_samples),public_counts[sample_type][host][1]+int(size.replace('M',''))]

with open(COUNT_FILE, "w") as file_handle:
    file_handle.write(",".join(["Principal Investigator","User","Sample Type","Study Name","Host","Total Samples","Size","Deposition Date","Internal Release","External Release"])+"\n")
    for pi in counts.keys():
        for sample_type in counts[pi].keys():
            for study_name in counts[pi][sample_type].keys():
                study_info = counts[pi][sample_type][study_name]
                file_handle.write(",".join(map(lambda x: str(x),[pi,study_info[0],sample_type,study_name]+study_info[1:]))+"\n")

with open(PUBLIC_COUNT_FILE, "w") as file_handle:
    file_handle.write(",".join(["Sample Type","Host","Total Samples","Size"])+"\n")
    for type in public_counts.keys():
        for host in public_counts[type]:
            file_handle.write(",".join(map(lambda x: str(x),[type,host,public_counts[type][host][0],to_GB(public_counts[type][host][1])]))+"\n")

