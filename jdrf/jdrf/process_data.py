
import csv
import sys
import os
import threading
import logging
import subprocess
import time
import re

import smtplib
import socket

from email.mime.text import MIMEText
from xlrd import open_workbook, XLRDError

from django.conf import settings

import fasteners
import yaml

# Set default email options
EMAIL_FROM = "jdrfmibc-dev@hutlab-jdrf01.rc.fas.harvard.edu"
EMAIL_TO = "jdrfmibc-dev@googlegroups.com"

EMAIL_SERVER = "rcsmtp.rc.fas.harvard.edu"

# Set default workflow config options
WMGX_PROCESSES="3"
WMGX_THREADS="8"
SixteenS_PROCESSES="1"
SixteenS_THREADS="15"
MAX_STRAINS="5"

import pandas as pd
import numpy as np

from jdrf.metadata_schema import schemas, sample_optional_cols, mr_parse
from pandas_schema.validation_warning import ValidationWarning

# name the general workflow stdout/stderr files
WORKFLOW_STDOUT = "workflow.stdout"
WORKFLOW_STDERR = "workflow.stderr"

# name the files for the process subfolders
METADATA_FOLDER="metadata"
WORKFLOW_MD5SUM_FOLDER="md5sum_check"
WORKFLOW_DATA_PRODUCTS_FOLDER="data_products"
WORFLOW_VISUALIZATIONS_FOLDER="visualizations"


def _my_unicode_repr(self, data):
    return self.represent_str(data.encode('utf-8'))

yaml.representer.Representer.add_representer(unicode, _my_unicode_repr)


def get_recursive_files_nonempty(folder,include_path=False,recursive=True):
    """ Get all files in all folder and subfolders that are not empty"""

    nonempty_files=[]
    for path, dirs, items in os.walk(folder):
        for file in items:
            file = os.path.join(path,file)
            if os.path.isfile(file) and os.stat(file).st_size > 0:
                if not include_path:
                    # remove the full path from the file name
                    file = os.path.basename(file)
                nonempty_files.append(file)
        if not recursive:
            break
    return nonempty_files

def get_metadata_column_by_name(metadata_file, column_name):
    """ Read the metadata file and get a list of all of the data for the column """

    file_names=[]
    with open(metadata_file) as file_handle:
        # read in the header
        header = file_handle.readline().rstrip().split(",")
        # file the column with the file names
        index = filter(lambda x: column_name in x[1].lower(), enumerate(header))[0][0]
        for line in file_handle:
            data=line.rstrip().split(",")
            try:
                file_names.append(data[index])
            except IndexError:
                pass
    return file_names

def get_metadata_file_md5sums(metadata_file):
    """ Return the md5sums for all of the files """

    return zip(get_metadata_column_by_name(metadata_file, "filename"),get_metadata_column_by_name(metadata_file, "md5_checksum"))

def get_metadata_file_names(metadata_file):
    """ Read the metadata file and get a list of all file names """
    return [item.strip() for item in get_metadata_column_by_name(metadata_file, "file")]


def delete_validation_files(upload_folder, logger):
    """Upon succesfully uploading a sample metadata file gets rid of any
    validation files if they exist.
    """
    validation_file = os.path.join(upload_folder, settings.METADATA_VALIDATION_FILE_NAME)
    update_file = os.path.join(upload_folder, settings.METADATA_EDIT_FILE_NAME)
    errors_csv = os.path.join(upload_folder, settings.METADATA_VALIDATION_FILE_NAME_CSV)

    for metadata_file in [validation_file, update_file, errors_csv]:
        if os.path.exists(metadata_file):
            os.remove(metadata_file)


def errors_to_json(errors, metadata_df):
    """ Takes any JDRF metadata validation errors and converts them into a
        JSON object for consumption on the JDRF MIBC website via jquery 
        DataTables.
    """
    def _map_errors_to_df(err):
        """ Quick little closure to handle mapping our errors to the dataframe """
        metadata_df.loc[err.row, err.column] = err.value
        metadata_df.loc[err.row, err.column + "_error"] = True
        metadata_df.loc[err.row, err.column + "_validation_msg"] = err.message
    
    map(_map_errors_to_df, errors)

    # For DataTable Editor to work properly we need to add a column that identifies
    # each row uniquely.
    metadata_df['DT_RowId'] = map(lambda x: "row_" + str(x+1), metadata_df.index)

    return (metadata_df, metadata_df.to_json(orient='records', date_format='iso'))


def errors_to_excel(errors, metadata_df, output_folder):
    """ Takes any JDRF metadata validation errors and writes them out to an 
        Excel file with cells containing errors denoted.
    """    
    def _highlight_error(s):
        return ['background-color: red']
    def _color_error(s):
        return ['color: white' if v.startswith('ERROR') else 'black' for v in s]

    def _map_errors_to_df(err):
        """ Quick little closure to handle mapping our errors to the dataframe """
        metadata_df.loc[err.row, err.column] = "ERROR;%s;%s" % (err.value, err.message)
    
    map(_map_errors_to_df, errors)

    errors_file = os.path.join(output_folder, settings.METADATA_VALIDATION_FILE_NAME)
    metadata_df.style.apply(_highlight_error)
    metadata_df.to_excel(errors_file, index=False, engine='openpyxl')

    return errors_file
    

def validate_study_metadata(metadata_dict, logger):
    """ Validates the provded JDRF study metadata form and returns any errors
        present.
    """
    metadata_df = pd.DataFrame(metadata_dict)
    schema = schemas['study']

    (is_valid, error_context) = _validate_metadata(metadata_df, schema, logger)
    return (is_valid, metadata_df, error_context)


def _is_csv_file(in_file):
    """ Verifies whether or not the supplied file is in CSV format.
    """
    dialect = csv.Sniffer().sniff(in_file.read().decode('utf-8'), [',', '\t'])
    sep = dialect.delimiter
    in_file.seek(0)

    return True if sep == "," else False


def _is_excel_file(in_file):
    """ Verifies whether or not the supplied file is an Excel spreadsheet """
    is_excel = False

    try:
        book = open_workbook(filename=None, file_contents=in_file.read())
        is_excel = True
    except XLRDError as e:
        pass
    finally:
       in_file.seek(0)

    return is_excel


def write_manifest_file(output_folder, user, user_email, user_full_name):
    """ Upon successful study and sample metadata validation writes a manifest 
    file containing the owner and contact information for the study. 
    """
    manifest_file = os.path.join(output_folder, 'MANIFEST')

    if not os.path.exists(manifest_file):
        with open(manifest_file, 'w') as manifest_fh:
           yaml.safe_dump({'user': user, 'name': user_full_name, 'lab': "", 'email': user_email}, manifest_fh, default_flow_style=False)


def validate_sample_metadata(metadata_file, output_folder, logger, action="upload", sep=None):
    """ Validates the provided JDRF sample metadata file and returns any errors
        presesnt.
    """

    def record_unexpected_error(e, error_context=None):
        try:
            error_message = str(e)
        except ValueError:
            error_message = ""

        # If we have an error here we don't want to leave the user hanging
        if not error_context:
            error_context={}
            error_context['error_msg'] = ("An unexpected error occurred. This error has been logged; " 
                                          "Please contant JDRF support for help with your metadata upload. " +  error_message)
        logger.error(error_message)
        logger.error(error_context['error_msg'])
        return error_context

    logger=logging.getLogger('jdrf1')

    is_valid = False
    is_excel = False
    error_context = {}
    metadata_df = None

    if not sep:
        is_excel = _is_excel_file(metadata_file)

        if not is_excel:
            sep = "," if _is_csv_file(metadata_file) else "\t"

    try:
        if is_excel:
            # When opening an Excel spreadsheet we only look at the first worksheet and ignore any others.
            metadata_df = pd.read_excel(metadata_file, keep_default_na=False, parse_dates=['collection_date'])
        else:
            metadata_df = pd.read_csv(metadata_file, keep_default_na=False, parse_dates=['collection_date'], sep=sep)

        ## Before we get to validation we need to be able to handle "slim" metadata spreadsheets that 
        ## include just the required fields.
        metadata_cols = set(metadata_df.columns.tolist())

        missing_cols = sample_optional_cols - metadata_cols
        logger.debug(missing_cols)
        for col in missing_cols:
            metadata_df[col] = ""

        schema = schemas['sample']
        (is_valid, error_context) = _validate_metadata(metadata_df, schema, logger, output_folder)
    except pd.errors.ParserError as pe:
        if "Error tokenizing data" in pe.message:
            line_elts = pe.message.split()
            line_number = int(line_elts[-3].replace(',', '')) - 1
            expected_fields = line_elts[-1]
            observed_fields = line_elts[-7]

            error_context['error_msg'] = "Line %s contained %s columns, expected %s columns" % (line_number, observed_fields, expected_fields)
            record_unexpected_error(pe, error_context)
        else:
            error_context=record_unexpected_error(pe)
    except ValueError as ve:
        if "collection_date" in ve.message:
            error_context['error_msg'] = "Metadata file is malformed and does not match JDRF metadata schema."
            record_unexpected_error(ve, error_context)
        else:
            error_context=record_unexpected_error(ve)
    except Exception as e:
        error_context=record_unexpected_error(e)

    return (is_valid, metadata_df, error_context)


def _get_mismatched_columns(metadata_df, schema):
    """Compares the list of columns supplied in the metadata spreadsheet with the list 
    of valid columns in the corresponding metadata schema.
    """
    valid_columns = set([c.name for c in schema.columns])
    metadata_columns = set(metadata_df.columns.tolist())

    extra_cols = list(metadata_columns.difference(valid_columns))
    missing_cols = list(valid_columns.difference(metadata_columns))

    return [extra_cols, missing_cols]


def _validate_md5_checksums(metadata_df, errors):
    """Verifies whether or not all MD5 checksums in an uploaded sample metadata sheet
    are unique when paired with a unique filename. Multiple rows may reference the same 
    filename - md5 pair without triggering an error.
    """
    # This is kind of ugly and probably could be achieved in a cleaner fashion...
    for (filename, rows) in metadata_df.groupby('filename'):
        if rows.md5_checksum.nunique() > 1:
            last_md5sum = rows.md5_checksum.iloc[0]

            for (idx, md5sum) in rows.md5_checksum.to_dict().iteritems():
                if last_md5sum != md5sum:
                    errors.append(ValidationWarning(
                        row=idx,
                        column="md5_checksum",
                        value=md5sum,
                        message=("Multiple MD5 checksums for file %s are not "
                                 "allowed. Please check all MD5 checksum rows "
                                 "for this file." 
                                 % (filename))
                    ))

                    last_md5sum = md5sum

    return errors


def _validate_metadata(metadata_df, schema, logger, output_folder=None):
    """ Validates the provided JDRF metadata DataFrame and returns any errors 
        if they are present.
    """
    logger=logging.getLogger('jdrf1')

    error_context = {}
    logger.debug("About to validate!")
    errors = schema.validate(metadata_df)
    logger.debug("Validated base schema!")
    errors = _validate_md5_checksums(metadata_df, errors) if 'md5_checksum' in [c.name for c in schema.columns] else errors

    # check for period in sample name
    if 'filename' in metadata_df:
        for (row_number, filename) in metadata_df['filename'].to_dict().iteritems():
            if len(filename.replace(".gz","").split(".")) > 2 and ("fastq" in filename or "fq" in filename):
                errors.append(ValidationWarning(
                    row=row_number,
                    column="filename",
                    value=filename,
                    message="Periods in sample names are not supported in file {}".format(filename)))
 
    is_valid = False if errors else True
    if errors:
        if len(errors) == 1 and "columns" in str(errors[0]):
            error_context['error_msg'] = str(errors[0])
            error_context['mismatch_cols'] = _get_mismatched_columns(metadata_df, schema)
        else:
            (errors_metadata_df, errors_json) = errors_to_json(errors, metadata_df.copy(deep=True))
            error_context['errors_datatable'] = errors_json
            error_context['errors_list'] = [dict(row=err.row, col=err.column, mesg=err.message) for err in errors]

            if output_folder:
                error_context['errors_file'] = errors_to_excel(errors, metadata_df.copy(deep=True), output_folder)

                # Kinda hacky but in order to do in-line editing we need a copy of the error'd 
                # CSV in a temporary location.
                metadata_df.to_csv(os.path.join(output_folder, settings.METADATA_VALIDATION_FILE_NAME_CSV), index=False)

    return (is_valid, error_context)


def update_metadata_file(field_updates_raw, upload_folder, logger):
    """Receives any inline edits done to a metadata file by the user via the DataTable Editor
    on the upload metadta page.
    """
    logger = logging.getLogger('jdrf1')

    updated_metadata_file = os.path.join(upload_folder, settings.METADATA_EDIT_FILE_NAME)
    metadata_error_df = pd.read_csv(os.path.join(upload_folder, settings.METADATA_VALIDATION_FILE_NAME_CSV), parse_dates=['collection_date'])

    field_updates = mr_parse(field_updates_raw)

    for (row_num, row_data) in field_updates.get('data').items():
        row_num = int(row_num.replace('row_', '')) - 1
        test_df = pd.Series(row_data)
        logger.debug(row_num)
        logger.debug(test_df['collection_date'])
        metadata_error_df.loc[row_num] = test_df

    metadata_error_df.to_csv(updated_metadata_file, index=False)

    return updated_metadata_file


def check_metadata_files_complete(user,folder,metadata_file,study_file):
    """ Read the metadata and find all raw files for user.
        Then check that all files have metadata.
        Finally check that all files in the metadata exist. 
    """
    message=""
    error_code = 1

    # get the study metadata
    try:
        study_metadata = get_study_metadata(study_file)
    except EnvironmentError:
        return 1, "ERROR: Unable to find metadata file. Please upload metadata file."

    # get all of the files that have been uploaded
    all_raw_files = set(get_recursive_files_nonempty(folder,recursive=False))

    # check if there are not any raw files
    if len(list(all_raw_files)) == 0:
        return 1, "ERROR: Unable to find any uploaded raw files. Please upload files."

    # get the file names from the metadata
    try:
        metadata_files = set(get_metadata_file_names(metadata_file))
    except IndexError:
        return 1, "ERROR: Unable to find files in metadata file. Please update metadata."
    except EnvironmentError:
        return 1, "ERROR: Unable to find metadata file. Please upload metadata file."

    # check if there are not any files in the metadata
    if len(list(metadata_files)) == 0:
        return 1, "ERROR: Unable to find any file names in the metadata. Please update metadata."


    # If study type is "other" data type we expect a tabular data file and we want
    # to check to ensure at the minimum that the columns in the file match the 
    # samples in the metadata.
    #
    # TODO: In the future we may want to come up with some way to validate any extra columns
    # that exist in the uploaded file. We particularly want to make sure that no extra samples
    # exist that should be in the sample metadata
    if study_metadata.sample_type == "other":
        all_raw_files = [os.path.join(folder, raw_file) for raw_file in all_raw_files]

        # filter out files of unexpected type
        if all(map(lambda x: x.endswith(".tsv"), all_raw_files)) or all(map(lambda x: x.endswith(".raw"), all_raw_files)):
            metadata_samples = get_metadata_samples(metadata_file)
            missing_samples=verify_samples_in_analysis_files(all_raw_files, metadata_samples)

            if missing_samples:
                message="ERROR: The following samples are missing from uploaded files: " + ",".join(missing_samples)
                error_code = 1
        else:
            message="ERROR: Only provide data files with extensions '.tsv', for tab-delimited data, or '.raw', for other types, for the 'other' study type."
            error_code = 1
    else:
        missing_from_metadata=all_raw_files.difference(metadata_files)
        missing_from_raw=metadata_files.difference(all_raw_files)

        if missing_from_metadata:
            message="ERROR: The following raw files do not have metadata. Please update the metadata. Files: "+",".join(list(missing_from_metadata))
        if missing_from_raw:
            if message:
                message+=" "
            message+="ERROR: The following files in the metadata have not been uploaded. Please upload these files: "+",".join(list(missing_from_raw))

        error_code = 1

    if not message:
        message="VERIFIED: All raw files have metadata.\n"
        message+="VERIFIED: All files in the metadata have been uploaded.\n"
        message+="SUCCESS! The metadata and raw files match.\n"
        message+="NEXT STEP: The files are now ready to be processed.\n"
        error_code = 0

    # email status of verify
    subject="data verify run by user "+user
    send_email_update(subject,message)

    # return the error code and message
    return error_code, message

def create_folder(folder):
    """ Create a folder if it does not exist """
    # get the logger instance
    logger=logging.getLogger('jdrf1')

    # create the user process folder if it does not already exist
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except EnvironmentError:
            logger.info("Unable to create folder: " + folder)
            raise

def send_email_update(subject,message,to=None):
    """ Send an email to update the status of workflows """
    # get the logger instance
    logger=logging.getLogger('jdrf1')

    # create email message
    msg = MIMEText(message)
    msg['From'] = EMAIL_FROM
    if to:
        msg['To'] = to
        msg['Cc'] = EMAIL_TO
        msg['Subject'] = "JDRF1 MIBC USER: " + subject
        mail_to = [to, EMAIL_TO]
    else:
        msg['To'] = EMAIL_TO
        msg['Subject'] = "JDRF1 MIBC DEVELOPER: " + subject
        mail_to = EMAIL_TO

    logger.info("Sending email")
    logger.info("Email subject: " + subject)
    logger.info("Email message: " + message)

    # send the message
    try:
        s = smtplib.SMTP(EMAIL_SERVER,timeout=3)
        s.sendmail(msg['From'], mail_to, msg.as_string())
        s.quit()
        logger.info("Email sent successfully")
    except (smtplib.SMTPRecipientsRefused, socket.gaierror, socket.timeout):
        logger.error("Unable to send email")

def subprocess_capture_stdout_stderr(command,output_folder,shell=False):
    """ Run the command and capture stdout and stderr to files """
    # get the logger instance
    logger=logging.getLogger('jdrf1')

    stdout_file = os.path.join(output_folder, WORKFLOW_STDOUT)
    stderr_file = os.path.join(output_folder, WORKFLOW_STDERR)

    try:
        # use line buffering to write stdout/stderr
        with open(stdout_file,"wt",buffering=1) as stdout:
            with open(stderr_file,"wt",buffering=1) as stderr:
                if shell:
                    command=" ".join(command)
                subprocess.check_call(command,stderr=stderr,stdout=stdout,shell=shell)
    except (EnvironmentError, subprocess.CalledProcessError):
        logger.error("Unable to run subprocess command: " + " ".join(command))

    # check for error in stderr file
    time.sleep(2)
    try:
        with open(stderr_file) as file_handle:
            stderr_output = "".join(file_handle.readlines())
    except EnvironmentError:
        logger.error("Unable to read stderr file")
        stderr_output = ""

    if "ERROR" in stderr_output or "Failed" in stderr_output:
        logger.error("Error found in subprocess command stderr: " + " ".join(command))
        raise EnvironmentError

    logger.info("Subprocess command terminated")

def email_workflow_status(user,command,output_folder,workflow,user_name=None,user_email=None,shell=False):
    """ Run the subprocess and send status emails """

    # start the subprocess
    subject="workflow "+workflow+" for user "+user
    message="The following subprocess was run to execute "+\
        "workflow "+workflow+" for user "+user+".\n\n"+" ".join(command)

    if user_name and user_email:
        user_message = "Hello "+user_name+",\n\n"
        user_end = "\n\nThank you for using JDRF1,\nThe JDRF MIBC Development Team\n"+\
            "\nPlease do not respond to this email as it was sent from an automated source.\n"+\
            "If you have questions, please email the JDRF MIBC Development Team."
        user_start_message = user_message+"Your workflow "+workflow+" has started running. "+\
            "You will be sent another email when the workflow has finished running. "+user_end
        user_end_message = user_message+"Your workflow "+workflow+" has finished running. "+user_end
        user_end_error_message =  user_message+"Your workflow "+workflow+" has finished running. "+\
            "However, it ended with an error. The development team has been sent additional information about this error. "+\
            "They will reach out to you to help. If you do not hear from them shortly, "+\
            "please feel free to email them directly."+user_end

    start_message = "Workflow started.\n\n"+message
    end_message = "Workflow finished running.\n\n"+message
    error_message = "Workflow error.\n\n"+message+\
        "\n\nPlease review the workflow logs to determine the error."+\
        "\n\nThe workflow stdout with error messages, if avaliable, is included "+\
        "at the end of this message for debugging.\n\n"

    error = False
    try:
        send_email_update("Starting "+subject,start_message) 
        if user_name and user_email:
            send_email_update("Starting workflow "+workflow,user_start_message,user_email)
        subprocess_capture_stdout_stderr(command,output_folder,shell=shell)
        send_email_update("Completed "+subject,end_message)
        if user_name and user_email:
            send_email_update("Completed workflow "+workflow,user_end_message,user_email)
    except (EnvironmentError, subprocess.CalledProcessError):
        error = True

    if error:
        # try to read the workflow stdout file to send data with the error
        stdout_file = os.path.join(output_folder, WORKFLOW_STDOUT)
        try:
            with open(stdout_file) as file_handle:
                workflow_stdout = "".join(file_handle.readlines())
        except EnvironmentError:
            workflow_stdout = ""
        # send the error messages
        send_email_update("Ended with error "+subject,error_message+workflow_stdout)
        if user_name and user_email:
            send_email_update("Ended with error workflow "+workflow,user_end_error_message,user_email)


    return error

def get_study_metadata(study_file):
    """ Parses study metadata file and returns a pandas DataFrame representation of metadata """
    return pd.read_csv(study_file, keep_default_na=False).ix[0]

def get_metadata_samples(metadata_file):
    """ Parses the sample metadata file and returns a list of all sample names """
    return pd.read_csv(metadata_file)['sample_id'].tolist()

def verify_samples_in_analysis_files(raw_files, metadata_samples):
    """ Parses over all analysis files uploaded of data type "other" and verifies that all samples 
    listed in the sample metadata file are present across the analysis files.
    For raw files where the sample names are not readable, do not check for missing samples.
    """
    analysis_cols = []

    raw_format = False
    for raw_file in raw_files: 
        with open(raw_file, 'rb') as raw_fh:
            if _is_excel_file(raw_fh):
                raw_df = pd.read_excel(raw_fh)
                analysis_cols.extend(raw_df.columns.tolist())
            elif raw_file.endswith("raw"):
                raw_format = True
            else:
                sep = "," if _is_csv_file(raw_fh) else "\t"
                raw_df = pd.read_csv(raw_fh, sep=sep)
                analysis_cols.extend(raw_df.columns.tolist())

    if raw_format:
        missing_samples = []
    else:
        missing_samples = set(metadata_samples).difference(set(analysis_cols))

    return missing_samples

def run_workflow(user,user_name,user_email,upload_folder,process_folder,metadata_file,study_file):
    """ First run the md5sum steps then run the remainder of the workflow """

    # get the logger instance
    logger=logging.getLogger('jdrf1')

    # get the location of the workflow file
    folder = os.path.dirname(os.path.realpath(__file__))

    # get the workflow subfolders
    md5sum_check = os.path.join(process_folder,WORKFLOW_MD5SUM_FOLDER)
    data_products = os.path.join(process_folder,WORKFLOW_DATA_PRODUCTS_FOLDER)
    visualizations = os.path.join(process_folder,WORFLOW_VISUALIZATIONS_FOLDER)
 
    # get the study metadata 
    study_metadata = get_study_metadata(study_file)
    logger.info("Starting workflow for study type: " + study_metadata.sample_type)

    create_folder(md5sum_check)
    if study_metadata.sample_type != "other":
        create_folder(visualizations) 
        create_folder(data_products)

    # get the input file extensions
    # get all of the files that have been uploaded
    all_raw_files = set(get_recursive_files_nonempty(upload_folder,include_path=True,recursive=False))

    # remove the metadata file from the set of raw files
    input_files = list(all_raw_files.difference([metadata_file]))

    if input_files[0].endswith(".gz"):
        extension = ".".join(input_files[0].split(".")[-2:])
    else:
        extension = input_files[0].split(".")[-1]

    # run the checksums
    command=["python",os.path.join(folder,"md5sum_workflow.py"),
        "--input",upload_folder,"--output",md5sum_check,"--input-metadata",
        metadata_file,"--input-extension",extension]
    error_state = False
    error_state = email_workflow_status(user,command,md5sum_check,"md5sum",user_name,user_email)

    # run the 16S workflow
    if study_metadata.sample_type == "16S":
        command=["PATH=$PICRUST_ENV:$PATH ","biobakery_workflows","16s","--input",
            upload_folder,"--output",data_products,"--input-extension",
            extension,"--local-jobs",SixteenS_PROCESSES,"--threads",SixteenS_THREADS,"--method","usearch",
            "--picrust-version","2"]

        if study_metadata.paired and study_metadata.paired_id:
            command.extend(['--pair-identifier', study_metadata.paired_id])

        if not error_state:
            error_state = email_workflow_status(user,command,data_products,"16s_uparse",user_name,user_email,shell=True)

        dada2_data_products = data_products+"_dada2"
        create_folder(dada2_data_products)
        dada2_visualizations = visualizations+"_dada2"
        create_folder(dada2_visualizations)

        dada2_command=["PATH=$PICRUST_ENV:$PATH ","biobakery_workflows","16s","--input",
            upload_folder,"--output",dada2_data_products,"--input-extension",
            extension,"--local-jobs",SixteenS_PROCESSES,"--threads",SixteenS_THREADS,"--method","dada2",
            "--picrust-version","2"]

        if study_metadata.paired and study_metadata.paired_id:
            dada2_command.extend(['--pair-identifier', study_metadata.paired_id])

        if not error_state:
            email_workflow_status(user,dada2_command,dada2_data_products,"16s_dada2",user_name,user_email,shell=True)

        # run the vis workflow
        command=["biobakery_workflows","16s_vis",
            "--input",data_products,"--output",visualizations,"--project-name",
            "JDRF MIBC Generated"]
        if not error_state:
            error_state = email_workflow_status(user,command,visualizations,"visualization_uparse",user_name,user_email)

        dada2_vis_command=["biobakery_workflows","16s_vis",
            "--input",dada2_data_products,"--output",dada2_visualizations,"--project-name",
            "JDRF MIBC Generated"]
        if not error_state:
            email_workflow_status(user,dada2_vis_command,dada2_visualizations,"visualization_dada2",user_name,user_email)
    elif study_metadata.sample_type != "other":
        command=["biobakery_workflows","wmgx","--input",
            upload_folder,"--output",data_products,"--input-extension",
            extension,"--remove-intermediate-output",
            "--local-jobs",WMGX_PROCESSES,"--threads",WMGX_THREADS,"--run-strain-gene-profiling",
            "--max-strains",MAX_STRAINS]

        if study_metadata.paired and study_metadata.paired_id:
            command.extend(['--pair-identifier', study_metadata.paired_id])

        if not error_state:
            error_state = email_workflow_status(user,command,data_products,"wmgx",user_name,user_email)

        # run the vis workflow
        command=["biobakery_workflows","wmgx_vis",
            "--input",data_products,"--output",visualizations,"--project-name",
            "JDRF MIBC Generated"]
        if not error_state:
            error_state = email_workflow_status(user,command,visualizations,"visualization",user_name,user_email)
    else:
        # if study type is other, then just copy uploaded files to processed folder
        # since the uploaded files have already been processed
        command=["cp",upload_folder+"/*.*",process_folder+"/"]
        subprocess_capture_stdout_stderr(" ".join(command),process_folder,shell=True)

    archive_folder = os.path.join(settings.ARCHIVE_FOLDER,user)
    create_folder(archive_folder)
    # run the archive and transfer workflow
    command=["python",os.path.join(folder,"archive_workflow.py"),
        "--input-upload",upload_folder,"--input-processed",process_folder,
        "--key",settings.SSH_KEY,"--remote",settings.REMOTE_TRANSFER_SERVER,
        "--user",settings.REMOTE_TRANSFER_USER,
        "--study",study_metadata.study_id,"--output",archive_folder,"--output-transfer",
        os.path.join(settings.REMOTE_TRANSFER_FOLDER,user)+"/",
        "--count-script",os.path.join(folder,"count_data_deposited.py")]
    if not error_state:
        email_workflow_status(user,command,archive_folder,"archive, update stats, and transfer",user_name,user_email)

def check_workflow_running(user, process_folder):
    """ Check if any of the process workflows are running for a user """

    # get the logger instance
    logger=logging.getLogger('jdrf1')

    try:
        ps_output = subprocess.check_output(["ps","aux"]).split("\n")
    except EnvironmentError:
        ps_output = []

    logger.info("Checking if workflow is running for user: " + user)
    user_workflow_processes = list(filter(lambda x: process_folder in x and "workflow" in x, ps_output))
    
    if user_workflow_processes:
        logger.info("Workflows running for user: ", "\n".join(user_workflow_processes))
        return True
    else:
        logger.info("No workflows running for user")
        return False

def check_md5sum_and_process_data(user,user_name,user_email,upload_folder,process_folder,metadata_file,study_file):
    """ Run the files through the md5sum check, biobakery workflow (data and vis) """

    # run the workflows
    try:
        thread = threading.Thread(target=run_workflow, args=[user,user_name,user_email,upload_folder,process_folder,metadata_file,study_file])
        thread.daemon = True
        thread.start()
    except threading.ThreadError:
        return 1, "ERROR: Unable to run workflow"
    
    return 0, "Success! The first workflow is running. It will take at least a few hours to run through all processing steps. The progress for each of the workflows will be shown below. Refresh this page to get the latest progress or check your inbox for status emails."


def rename_file(target_file, target_fname, rename_file, logger):
    """ Renames the supplied file using the passed in new filename  """
    data = {}

    with fasteners.InterProcessLock('/tmp/rename_file_lock_' + target_fname):
        logger.debug("Acquired process lock for file %s" % target_fname)
        logger.info("Renaming file %s to %s" % (target_file, rename_file))

        try:
            os.rename(target_file, rename_file)

            data['success'] = True
        except OSError as e:
            # If we get an error here we want to record that the rename failed 
            # and try the rest of the files. We can pass on partial success to
            # the user
            data['success'] = False
            data['error_msg'] = str(e);
            pass
        finally:
            data['renamed_file'] = os.path.basename(rename_file)
            data['original_file'] = target_fname

    return data

def _validate_file_path(file_name, target_folder):
    """ Verifies whether or not the provided file path contains any malicious characters (i.e. '*') 
        or attemps to traverse outside of the desired directories (using relative paths) 
        
        CREDIT - https://stackoverflow.com/a/6803714
    """
    requested_path = os.path.relpath(file_name, start=target_folder)
    requested_path = os.path.abspath(requested_path)
    common_prefix = os.path.commonprefix([requested_path, target_folder])
    return common_prefix != target_folder


def delete_file(target_file, target_fname, target_folder, logger):
    """ Deletes the supplied file from the JDRF1 docker instance """
    data = {}

    with fasteners.InterProcessLock('/tmp/delete_file_lock_' + target_fname):
        logger.debug("Acquired process lock for file %s" % target_fname)
        logger.info("Deleting file %s" % target_file)

        try:
            if not _validate_file_path(target_fname, target_folder):
                raise OSError('Malformed filename. Please contact JDRF MIBC support.')

            if os.path.isfile(target_file):
                os.remove(target_file)

                data['success'] = True
            else:
                raise OSError('File does not exist')
        except OSError as e:
            data['success'] = False
            data['error_msg'] = str(e);
            pass
        finally:
            data['target_file'] = target_fname

    return data
