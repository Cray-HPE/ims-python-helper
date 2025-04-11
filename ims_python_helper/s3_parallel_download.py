#
# MIT License
#
# (C) Copyright 2025 Hewlett Packard Enterprise Development LP
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#

import gevent
from gevent.pool import Pool
import logging
import os

LOGGER = logging.getLogger(__file__)
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

DEFAULT_CHUNK_SIZE_BYTES = 10 * 1024 * 1024
NO_OF_GREENLETS = 10

class S3ParallelDownload:
    def __init__(self, bucket_name, s3_key, local_path, s3_client=None, s3_resource=None):
        self.bucket_name = bucket_name
        self.s3_key = s3_key
        self.s3_client = s3_client
        self.chunk_size = DEFAULT_CHUNK_SIZE_BYTES
        self.local_path = local_path
        self.s3_resource = s3_resource

    def get_file_size(self):
        response = self.s3_client.head_object(Bucket=self.bucket_name, Key=self.s3_key)
        LOGGER.info("File size %s", response['ContentLength'])
        return response['ContentLength']

    def download_small_file(self):
        self.s3_client.download_file(self.bucket_name, self.s3_key, self.local_path)

    def download_file_in_chunks(self, start_idx, file_size):
        start = start_idx
        end = min(start + self.chunk_size, file_size)
        # LOGGER.info("Downloading bytes %s to %s", start, end)
        response = self.s3_client.get_object(Bucket=self.bucket_name, Key=self.s3_key, Range=f'bytes={start}-{end}')
        with open(self.local_path, 'r+b') as f:
            f.seek(start)
            f.write(response['Body'].read())

    def download_file(self):
        file_size = self.get_file_size()
        LOGGER.info("File size %s", file_size)

        # Create a local file with the same size as the S3 object
        with open(self.local_path, 'wb') as f:
            f.truncate(file_size)

        if file_size < self.chunk_size:
            self.download_small_file()
        else:
            LOGGER.info("Downloading %s in chunks of %s bytes", self.s3_key, self.chunk_size)
             # Create a list of chunk ranges
             # Use gevent to download each chunk in parallel
             # Use a generator to yield the chunks
            chunk_list = range(0, file_size, self.chunk_size)
            pool = Pool(NO_OF_GREENLETS)
            gevent.joinall([
                pool.spawn(self.download_file_in_chunks, chunk, file_size)
                for chunk in chunk_list
            ])