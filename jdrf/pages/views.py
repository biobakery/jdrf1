# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import sys
import time
import json

import pandas as pd
import whoosh.index as index

from django.conf import settings

from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from django.core.urlresolvers import reverse
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponseRedirect, HttpResponse, JsonResponse, QueryDict
from django.template import RequestContext
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.csrf import requires_csrf_token

from django.http import FileResponse

from whoosh.qparser import QueryParser

from jdrf import process_data

from .forms import UploadForm


import logging


def get_user_and_folders_plus_logger(request, full_user_info=False):
    """ Get the user and all of the user folders """

    # get the default logger
    logger=logging.getLogger('jdrf1')

    # get the list of raw files to process
    user = request.user.username
    logger.info("Current user: %s", user)
    user_full_name = request.user.first_name+" "+request.user.last_name
    logger.info("User full name: %s", user_full_name)
    user_email = request.user.email
    logger.info("User email: %s", user_email)
    # get the location of the upload file for the user
    upload_folder = os.path.join(settings.UPLOAD_FOLDER,user)
    logger.info("Upload folder: %s", upload_folder)
    # get the location of the process folder for the user
    process_folder = os.path.join(settings.PROCESS_FOLDER,user)
    logger.info("Process folder: %s", process_folder)

    if full_user_info:
        return logger, user, user_full_name, user_email, upload_folder, process_folder
    else:
        return logger, user, upload_folder, process_folder


@login_required(login_url='/login/')
@csrf_exempt
@requires_csrf_token
def upload_files(request):
    # get the user, folders, and logger
    logger, user, upload_folder, process_folder = get_user_and_folders_plus_logger(request)
    if request.method == 'POST':
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            # save the file as chunks
            # use chunking from plupload (so request.FILES['file'] might be blob)
            # write to temp file then move when all chunks are written
            file = request.FILES['file']
            file_name = request.POST['name']
            file_name_part = file_name+".part"
            logger.info("Uploading file in chunks: %s", file_name_part)
            upload_folder = os.path.join(settings.UPLOAD_FOLDER,user)
            # if a folder does not exist for the user, then create
            if not os.path.isdir(upload_folder):
                try:
                    os.makedirs(upload_folder)
                except EnvironmentError:
                    logger.info("Unable to create upload folder")
                    raise

            upload_file = os.path.join(upload_folder,file_name_part)
            logger.info("Starting to upload file in chunks: %s", upload_file)
            with open(upload_file, 'a') as destination:
                for chunk in file.chunks():
                    destination.write(chunk)

            logger.info("Finished uploading file chunk")

            # move the file if all chunks have been written
            chunks = int(request.POST['chunks'])
            chunk = int(request.POST['chunk'])
            if chunks == 0 or chunk == chunks -1:
                os.rename(upload_file, os.path.join(upload_folder,file_name))
                logger.info("Finished uploading file")
                process_data.send_email_update("File uploaded","The user "+user+" has successfully uploaded the file " + file_name)
    else:
        form = UploadForm()

    return render(request,'upload.html', {'form': form})


@login_required(login_url='/login/')
@csrf_exempt
@requires_csrf_token
def upload_metadata(request):
    """ Generic view here just to handle authentication and redirect in case 
    the user is not logged in"""
    logger, user, upload_folder, process_folder = get_user_and_folders_plus_logger(request)
    return render(request, 'upload_metadata.html')


@login_required(login_url='/login/')
@csrf_exempt
@requires_csrf_token
def upload_study_metadata(request):
    """ Validates and saves study metadata provided by the logged in user. """
    (logger, user, upload_folder, process_folder) = get_user_and_folders_plus_logger(request)
    data = {}
    response_code = 200

    metadata_folder = os.path.join(upload_folder, process_data.METADATA_FOLDER)
    study_csv_file = os.path.join(metadata_folder, settings.METADATA_GROUP_FILE_NAME)

    if request.method == 'GET':
        # Read in our CSV and populate our form field values.
        if os.path.exists(study_csv_file):
            study_metadata_df = pd.read_csv(study_csv_file, keep_default_na=False)

            data['study_form'] = study_metadata_df.to_dict(orient='records')[0]
        else:
            response_code = 500
            data['error_msg'] = "Could not find study metadata file at path %s" % study_csv_file
    elif request.method == 'POST':
        for folder in [upload_folder, metadata_folder]:
            if not os.path.isdir(folder):
                try:
                    os.makedirs(folder)
                except EnvironmentError:
                    logger.info("Unable to create folder %s" % folder)
                    raise

        post_dict = dict(request.POST.iterlists())
        (is_valid, metadata_df, error_context) = process_data.validate_study_metadata(post_dict, logger)
        logger.info("Study Metadata validation: %s" % is_valid)
        if is_valid:
            metadata_df.to_csv(study_csv_file, index=False)
        else:
           response_code = 500
           data['error_msg'] = "Validation failed!"
           data.update(error_context)

    return JsonResponse(data, status=response_code)


@login_required(login_url='/login/')
@csrf_exempt
@requires_csrf_token
def upload_sample_metadata(request):
    """ Validates the user-provided JDRF metadata file and if valid saves to the users 
        data storage directory.
    """ 
    data = {} 
    (logger, user, user_full_name, user_email, upload_folder, process_folder) = get_user_and_folders_plus_logger(request, full_user_info=True)
    metadata_folder = os.path.join(upload_folder, process_data.METADATA_FOLDER)
    study_file = os.path.join(metadata_folder,settings.METADATA_GROUP_FILE_NAME)

    if request.method == 'POST':
        if request.FILES and request.FILES['metadata_file']:
            file = request.FILES['metadata_file']
            file_name = file.name

            # if a folder does not exist for the user, then create
            for folder in [upload_folder, metadata_folder]:
                if not os.path.isdir(folder):
                    try:
                        os.makedirs(folder)
                    except EnvironmentError:
                        logger.info("Unable to create folder %s" % folder)
                        raise

            # When we receive a sample metadata file where the study has been tagged as the 
            # "Other" data type we need to forego any validation checks (for the time being)
            study_metadata = process_data.get_study_metadata(study_file)
            is_other_datatype = True if study_metadata.sample_type == "other" else False

            # We need to validate this file and if any errors exist prevent 
            # the user from saving this file.
            (is_valid, metadata_df, error_context) = process_data.validate_sample_metadata(file, upload_folder, logger)
               
            if not is_valid:
                data['error'] = 'Metadata validation failed!'
                data.update(error_context)
            else:
                ## Once we've uploaded a sample metadata file successfully let's nuke any
                ## validation spreadsheets we have left over.
                process_data.delete_validation_files(upload_folder, logger)

                metadata_file = os.path.join(metadata_folder, settings.METADATA_FILE_NAME)
                try:
                    metadata_df.to_csv(metadata_file, index=False)
                    ## If we are valid here we want to write a MANIFEST file containing our user contact info
                    process_data.write_manifest_file(metadata_folder, user, user_email, user_full_name)
                except Exception as e:
                    error_context['error_msg'] = ("An unexpected error occurred. This error has been logged; "
                                                  "Please contant JDRF support for help with your metadata upload")
                    logger.error(str(e))
                    logger.error(error_context['error_msg'])
                    data['error'] = 'Metadata validation failed!'
                    data.update(error_context)

            return JsonResponse(data)

        # If we get a POST request and it contains the editor parameter we know that 
        # we are attempting to modify an existing metadata file in place.
        elif request.POST.get('action') == "edit":
            logger.info('Processing metadata EDIT action')

            field_updates = request.POST.copy()
            del field_updates['action']

            updated_metadata_file = process_data.update_metadata_file(field_updates, upload_folder, logger)
            (is_valid, metadata_df, error_context) = process_data.validate_sample_metadata(updated_metadata_file, upload_folder, logger, sep=",")
            
            if not is_valid:
                data['error'] = 'Metadata validation failed!'
                data.update(error_context)
            else: 
                process_data.delete_validation_files(upload_folder, logger)

                metadata_file = os.path.join(metadata_folder, settings.METADATA_FILE_NAME)
                metadata_df.to_csv(metadata_file, index=False)

                process_data.write_manifest_file(metadata_folder, user, user_email, user_full_name)

            return HttpResponse(json.dumps(data), content_type="application/json")
        else:
            data['error'] = 'Oops something went wrong here.'                
    else :
        form = UploadForm()
        return render(request, 'upload_metadata.html', {'form': form})


def try_read_file(file_name):
    """ Try to read the file if it exists """

    lines=""
    try:
        with open(file_name) as file_handle:
            lines="".join(file_handle.readlines())
    except EnvironmentError:
        pass

    return lines

def read_stdout_stderr(folder):
    """ Read the stdout and stderr files from a workflow folder """

    stdout_file=process_data.WORKFLOW_STDOUT
    stderr_file=process_data.WORKFLOW_STDERR

    # if stdout is empty check for stderr
    stdout = try_read_file(os.path.join(folder,stdout_file))
    if not stdout:
        stderr = try_read_file(os.path.join(folder,stderr_file))
        # only include if error messages are present
        if "error" in stderr.lower() or "fail" in stderr.lower():
            stdout = stderr

    return stdout

@login_required(login_url='/login/')
@csrf_exempt
@requires_csrf_token
def process_files(request):
    # get the user, folders, and logger
    logger, user, user_full_name, user_email, upload_folder, process_folder = get_user_and_folders_plus_logger(request, full_user_info=True)
    metadata_folder = os.path.join(upload_folder, process_data.METADATA_FOLDER)
   
    files_nonempty = process_data.get_recursive_files_nonempty(upload_folder,include_path=False,recursive=False)

    # Var to keep track of our workflow status. Needed so we can clear our some cookies
    # on workflow success.
    success = False 

    # set the default responses
    responses={"message1":[],"message2":[]}
 
    responses["raw_input"]="The following raw files have been uploaded and are ready to verify:\n"
    responses["raw_input"]+="\n".join(files_nonempty)+"\n"

    if request.method == 'POST' and not "refresh" in request.POST:
        logger.info("Post from process page received")
        metadata_file = os.path.join(metadata_folder,settings.METADATA_FILE_NAME)
        study_file = os.path.join(metadata_folder,settings.METADATA_GROUP_FILE_NAME)
        logger.info("Metadata file: %s", metadata_file)
        process_folder = os.path.join(settings.PROCESS_FOLDER,user)
        logger.info("Process folder: %s", process_folder)

        if "verify" in request.POST:
            # check the metadata matches the raw uploads
            responses["message1"] = process_data.check_metadata_files_complete(user,upload_folder,metadata_file,study_file)
        elif "process" in request.POST:
            responses["message2"] = process_data.check_md5sum_and_process_data(user,user_full_name,user_email,upload_folder,process_folder,metadata_file,study_file)

    # log messages
    for message_name, message in responses.items():
        if message and not message_name == "raw_input":
            logger.info("Error code: %s", message[0])
            logger.info("Message: %s", message[1])

    # check if the workflow is running
    responses["workflow_running"] = process_data.check_workflow_running(user, process_folder)

    # get the stdout for the processing workflows
    responses["md5sum_stdout"]=read_stdout_stderr(os.path.join(process_folder,process_data.WORKFLOW_MD5SUM_FOLDER))
    responses["data_products_stdout"]=read_stdout_stderr(os.path.join(process_folder,process_data.WORKFLOW_DATA_PRODUCTS_FOLDER))
    responses["visualizations_stdout"]=read_stdout_stderr(os.path.join(process_folder,process_data.WORFLOW_VISUALIZATIONS_FOLDER))

    # if the workflow just started, wait for a refresh before updating status
    if not responses["message2"]:
        if not responses["workflow_running"]:
            if list(filter(lambda x: "fail" in x.lower() or "error" in x.lower(), [responses["md5sum_stdout"],responses["data_products_stdout"],responses["visualizations_stdout"]])):
                # one of the workflows had a task that failed
                responses["message2"]=(1, "ERROR: The workflows have finished running. One of the tasks failed.")
            elif len(list(filter(lambda x: "Finished" in x, [responses["md5sum_stdout"],responses["data_products_stdout"],responses["visualizations_stdout"]])))  == 3:
                responses["message2"]=(0, "Success! All three workflows (md5sum check, data processing, and visualization) finished without error.")
                success = True
            elif ( responses["md5sum_stdout"] and not ( responses["data_products_stdout"] or responses["visualizations_stdout"] ) or 
                responses["md5sum_stdout"] and responses["data_products_stdout"] and not responses["visualizations_stdout"] ):
                # add the case where we are in between workflows running
                responses["message2"]=(0, "The processing workflows (md5sum check, data processing, and visualization) are still running.")
        elif responses["md5sum_stdout"] or responses["data_products_stdout"] or responses["visualizations_stdout"]:
            responses["message2"]=(0, "The processing workflows (md5sum check, data processing, and visualization) are still running.")

    # determine which buttons should be active
    responses["verify_button"] = 1
    if ( responses["message1"] and responses["message1"][0] == 0 ) or ( responses["message2"] and responses["message2"][0] in [0,1] ):
        responses["verify_button"] = 0
    if responses["verify_button"] == 1:
        responses["process_button"] = 0
        responses["refresh_button"] = 0
    elif ( responses["message1"] and responses["message1"][0] == 0 ) or ( responses["message2"] and responses["message2"][0] == 1 ):
        responses["process_button"] = 1
        responses["refresh_button"] = 0
    else:
        responses["process_button"] = 0
        responses["refresh_button"] = 1
    
    response = render(request, 'process.html', responses)
    if success and request.COOKIES.get('sample_metadata', False):
        response.set_cookie('study_metadata', max_age=1)
        response.set_cookie('sample_metadata', max_age=1)

    return response

def get_file_size(file):
    """ Get the size of the file """

    size = 0 
    try:
        size = os.stat(file).st_size
    except EnvironmentError:
        pass

    # change units based on total size
    units = " "
    for type in ["K","M","G"]:
        if size / 1024.0 > 1.0:
            size = size / 1024
            units = type

    return str(size)+" "+units


def get_mtime(file):
    """ Get the last time a file was modified as a date string """

    return time.ctime(os.path.getmtime(file))

def list_file_in_folder(folder,exclude_files=[".anadama"]):
    """ Get a list of all of the files in the folder, formatted for page, exclude some folders """

    # get all of the files in the user process folder, with directories
    list_files = []
    for path, directories, files in os.walk(folder, followlinks=True):
        # remove the base process folder form the path
        reduced_path = path.replace(folder,"")
        # remove path sep if first character
        if reduced_path.startswith(os.sep):
            reduced_path = reduced_path[1:]
        current_set = []
        for file in files:
            file_path = os.path.join(path,file)
            # check that this is a file with an extension
            if os.path.isfile(file_path) and "." in file:
                current_set.append((os.path.join(reduced_path,file), os.path.join(path,file), get_file_size(file_path), get_mtime(file_path)))
        # add the files sorted
        if current_set:
            list_files+=sorted(current_set, key=lambda x: x[0])

    # remove any of the files/folder to exclude
    list_files_reduced = []
    for file_info in list_files:
        include = True
        for exclude in exclude_files:
            if exclude in file_info[0]:
                include = False
                break
        if include:
            list_files_reduced.append(file_info)

    return list_files_reduced


@login_required(login_url='/login/')
@csrf_exempt
@requires_csrf_token
def rename_file(request, file_name):
    """ Handle a request to rename any uploaded file that is not being processed or is an archived file. """
    logger, user, upload_folder, process_folder = get_user_and_folders_plus_logger(request)
    logger.info("Renaming file for user: %s", user)

    data = {}

    # Files we are renaming should be lists with the first item being the file name 
    # and the second item being the new filename to rename too and the third item being the 
    # category of file (uploaded, archived, md5sum, viz, data_product) 
    put_dict = QueryDict(request.body)
    rename_fname = put_dict.get('rename_file');
    file_type = put_dict.get('type'); 

    logger.info('Variables passed in: %s %s %s' % (file_name, rename_fname, file_type))

    file_folder = os.path.join(settings.FILE_FOLDER_MAP.get(file_type), user)
    file = os.path.join(file_folder, file_name)
    renamed_file = os.path.join(file_folder, rename_fname)

    is_workflow_running = process_data.check_workflow_running(user, process_folder)

    if not is_workflow_running:
        data = process_data.rename_file(file, file_name, renamed_file, logger)
    else: 
        data['success'] = False
        data['error_msg'] = "Files cannot be renamed when a workflow is running."
        data['renamed_file'] = rename_fname
        data['original_file'] = file_name

    return JsonResponse(data)


@login_required(login_url='/login/')
@csrf_exempt
@requires_csrf_token
def delete_file(request, file_name):
    """ Deletes a single uploaded file. """
    logger, user, upload_folder, process_folder = get_user_and_folders_plus_logger(request)
    logger.info("Deleting file %s for user: %s" % (file_name, user))

    data = {}
    file_type = 'upload'

    file_folder = os.path.join(settings.FILE_FOLDER_MAP.get(file_type), user)
    target_file = os.path.join(file_folder, file_name)

    # Check if we have any workflows running. If so we want to prevent rename or delete operations 
    # here since they will interfere with the workflows running
    is_workflow_running = process_data.check_workflow_running(user, process_folder)

    if not is_workflow_running:
        data = process_data.delete_file(target_file, file_name, file_folder, logger)
    else: 
        data['success'] = False
        data['error_msg'] = "Files cannot be deleted when a workflow is running."

    return JsonResponse(data)


@login_required(login_url='/login/')
@csrf_exempt
@requires_csrf_token
def delete_files(request):
    """ Deletes multiple uploaded files. """
    logger, user, upload_folder, process_folder = get_user_and_folders_plus_logger(request)
    logger.info("Deleting files for user: %s" % user)

    data = {}
    data['results'] = []
    data['success'] = False 

    del_dict = QueryDict(request.body)

    target_fnames = del_dict.getlist('delete_file[]');
    file_type = 'upload'

    file_folder = os.path.join(settings.FILE_FOLDER_MAP.get(file_type), user)

    # Prevent files from being renamed/deleted if the workflow is running
    is_workflow_running = process_data.check_workflow_running(user, process_folder)

    if not is_workflow_running: 
        for target_fname in target_fnames:
            logger.info("Deleting file %s" % target_fname)
            target_file = os.path.join(file_folder, target_fname)
            data['results'].append(process_data.delete_file(target_file, target_fname, file_folder, logger))

        data['success'] = all([file['success'] for file in data['results']]) if data['results'] else False
    else:
        data['success'] = False
        data['target_files'] = target_fnames;
        data['error_msg'] = "Files cannot be deleted when a workflow is running."

    return JsonResponse(data)

@login_required(login_url='/login/')
def download_files(request):
    """ List all of the processed files available for the user to download """

    # get the user, folders, and logger
    logger, user, upload_folder, process_folder = get_user_and_folders_plus_logger(request)
    logger.info("Listing files for user: %s", user)

    # get all of the upload and archive files/folders
    archive_folder = os.path.join(settings.ARCHIVE_FOLDER, user)
    response={}
    response["uploaded_files"] = list_file_in_folder(upload_folder,exclude_files=["metadata"])
    response["archived_files"] = list_file_in_folder(archive_folder,exclude_files=[".anadama","workflow.stderr","workflow.stdout","anadama.log"])

    # get all of the files in the user process folder, with directories
    list_files = list_file_in_folder(process_folder)

    # organize the files into the three workflow folders
    response["md5sum_files"] = [(file.replace(process_data.WORKFLOW_MD5SUM_FOLDER+os.sep,""), full_path_file, size, mtime) for file, full_path_file, size, mtime in list(filter(lambda x: x[0].startswith(process_data.WORKFLOW_MD5SUM_FOLDER), list_files))]
    response["data_product_files"] = [(file.replace(process_data.WORKFLOW_DATA_PRODUCTS_FOLDER+os.sep,""), full_path_file, size, mtime) for file, full_path_file, size, mtime in list(filter(lambda x: x[0].startswith(process_data.WORKFLOW_DATA_PRODUCTS_FOLDER), list_files))]
    response["visualization_files"] = [(file.replace(process_data.WORFLOW_VISUALIZATIONS_FOLDER+os.sep,""), full_path_file, size, mtime) for file, full_path_file, size, mtime in list(filter(lambda x: x[0].startswith(process_data.WORFLOW_VISUALIZATIONS_FOLDER), list_files))]

    return render(request,'download.html',response)

@login_required(login_url='/login/')
def download_file(request, file_name):
    """ Download the file from the user's processed files folder """
    # get the user, folders, and logger
    logger, user, upload_folder, process_folder = get_user_and_folders_plus_logger(request)
    logger.info("Downloading file for user: %s", user)

    # get file path
    if file_name == "sample_metadata.errors.xlsx":
        download_file = os.path.join(upload_folder, file_name)
    elif file_name[0] != os.sep:
        download_file = os.path.join(process_folder,file_name)
    else:
        download_file = file_name

    logger.info("File to download: %s", download_file)

    response = FileResponse(open(download_file, 'rb'))
    response['Content-Length'] = os.path.getsize(download_file)
    response['Content-Disposition'] = 'attachment; filename="'+os.path.basename(download_file)+'"'

    return response


@login_required(login_url='/login/')
def search_ontology(request, ontology_name, term_query):
    """ Searches the specified ontology for the provided query """
    logger, user, upload_folder, process_folder = get_user_and_folders_plus_logger(request)
    logger.info("Searching ontology %s for term: %s", (ontology_name, term_query))

    response_code = 200
    response = {}

    index_dir = os.path.join(settings.INDEX_BASE_DIR, ontology_name, "index")
    if not os.path.exists(index_dir):
        response['success'] = False
        response['error_msg'] = "Could not find index for ontology %s at location %s" % (ontology_name, index_dir)
        response_code = 404
    else:
        ix = index.open_dir(index_dir)

        with ix.searcher() as searcher:
            parser = QueryParser("name", ix.schema)
            query = parser.parse(term_query)
            results = searcher.search(query)

            response['success'] = True
            response['num_results'] = len(results)
            response['results'] = [dict(res) for res in results]

    return JsonResponse(response, status=response_code)
    
