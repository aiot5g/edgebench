#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Feb 24 14:34:12 2019

@author: "Anirban Das"
"""

from timeit import default_timer as timer
import sys
import os
import json
import csv
import logging
import datetime
from PIL import Image
from io import BytesIO
from iothub_client import IoTHubMessage
from azure.storage.blob import BlockBlobService, PublicAccess

# Initialize global variables -----------------------------------------------------------
IMAGE_DIRECTORY = os.getenv('IMAGE_DIRECTORY', default='/home/moduleuser/Images')
STATS_DIRECTORY = os.getenv('STATS_DIRECTORY', default='/home/moduleuser/Statistics')
container_name = os.getenv('CONTAINER_NAME')
thumbnail_size = int(os.getenv('THUMBNAIL_SIZE', default=128)), int(os.getenv('THUMBNAIL_SIZE', default=128))
ACC_NAME = os.getenv('ACC_NAME')
ACC_KEY = os.getenv('ACC_KEY')


block_blob_service = BlockBlobService(account_name=ACC_NAME, 
				account_key=ACC_KEY)
#block_blob_service = BlockBlobService(account_name='edgebench8561', 
#				account_key='0i7buxxEJ8gMW3XcMu11JBNcZllkJGdm3UkHuy24Sxj+x1iQv7bf62SKJwSBiYIZ/xhjp9zXkf3yfWtgfud1oA==')
block_blob_service.create_container(container_name)

csvfilename = "Thumbnail_stats_local_{}_{}.csv".format(str(datetime.datetime.now().date()), "Azure")

# Get all the file paths from the directory specified
def get_file_paths(dirname):
    file_paths = []  
    for root, directories, files in os.walk(dirname):
        for filename in files:
            filepath = os.path.join(root, filename)
            file_paths.append(filepath)  
    return file_paths


def stall_for_connectivity():
    import time
    """
        Implements a stalling function so that message
        sending starts much after edgeHub is initialized
    """
    if os.getenv('STALLTIME'):
        stalltime=int(os.getenv('STALLTIME'))
    else:
        stalltime=60
    print("Stalling for {} seconds for all TLS handshake and other stuff to get done!!! ".format(stalltime))
    for i in range(stalltime):
        print("Waiting for {} seconds".format(i))
        time.sleep(1)
    print("\n\n---------------Will Start in another 5 seconds -------------------\n\n")
    time.sleep(5)
    
# write local stats in a csv file
def write_local_stats(filename, stats_list):
    global STATS_DIRECTORY
    try:
        filepath = STATS_DIRECTORY.rstrip(os.sep) + os.sep + filename
        with open(filepath, 'a') as file:
            writer = csv.writer(file, delimiter=',')
            writer.writerows(stats_list)
    except :
        e = sys.exc_info()[0]
        print("Exception occured during writting Statistics File: %s" % e)        
        #sys.exit(0)
        
def image_resizer(hubmanager, callback_function, outputQueueName='thumbnailpipeline', context=0):
    stall_for_connectivity()
    global IMAGE_DIRECTORY
    global csvfilename
    try:
        t0 = timer()
        all_file_paths = get_file_paths(IMAGE_DIRECTORY)
        local_stats = [['imagefilename', 'payloadsize', 'imagefilesize', 'imagefileobjectsize', 
                        'imagewidth', 'imageheight', 'count', 
                        't0', 
                        't1', 
                        'f_t0',
                        'f_t1', 
                        'f_t2']]
        write_local_stats(csvfilename, local_stats)
        t1 = timer()
        count = 1
        for file in all_file_paths:
            f_t0 = timer()
            dictionary = {}

            filename = file.split(os.sep)[-1]
            extension = os.path.splitext(filename)[1].lower()
            # Set buffer format for image saving
            if extension in ['.jpeg', '.jpg']:
                format = 'JPEG'
            if extension in ['.png']:
                format = 'PNG'
            
            # Creating thumbnail of the image
            img = Image.open(file)
            height, width = img.size
            img = img.resize(thumbnail_size, Image.LANCZOS)
            # Save in buffer as bytes type object for uploading to S3    
            buffer = BytesIO()
            img.save(buffer, format)
            buffer.seek(0)
            # Create the Payload JSON with the necessary fields
            dictionary["imagefilename"] = filename
            dictionary["imagewidth"] = str(width)
            dictionary["imageheight"] = str(height)
            dictionary["func_start"] = str(f_t0)
            dictionary["totalcomputetime"] = str(timer() - f_t0) 
            dictionary["funccompleteutctime"] = datetime.datetime.utcnow().isoformat()
                
            f_t1 = timer()
            # Publish the Payload in the specific topic
            block_blob_service.create_blob_from_stream(container_name, 
                                    "{}^{}".format(filename, datetime.datetime.utcnow().isoformat()), buffer, metadata=dictionary)
            
            message = IoTHubMessage(bytearray(json.dumps(dictionary), 'utf8'))                                            
            hubmanager.client.send_event_async(outputQueueName, message, callback_function, 0)                                    
            
            f_t2 = timer()

            local_stats.append([file, sys.getsizeof(buffer), os.path.getsize(file), sys.getsizeof(file), 
                                width, height, count, 
                                t0, 
                                t1, 
                                f_t0, 
                                f_t1, 
                                f_t2])
            print("Resized image file  {} in {} seconds\n".format(filename, f_t2 - f_t0))     
            

            if count%200==0:
                write_local_stats(csvfilename, local_stats)
                local_stats = []
            count+=1
    except:
       e = sys.exc_info()[0]
       print("Exception occured during resizing: %s" % e)

    finally:
       write_local_stats(csvfilename, local_stats)
