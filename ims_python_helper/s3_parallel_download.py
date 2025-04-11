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
import logging
import os

LOGGER = logging.getLogger(__file__)
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

_DEFAULT_CHUNK_SIZE_B = 20 * 1024 * 1024

class S3ParallelDownload:
    def __init__(self, bucket_name, s3_key, local_path, s3_client=None, s3_resource=None):
        self.bucket_name = bucket_name
        self.s3_key = s3_key
        self.s3_client = s3_client
        self.chunk_size = _DEFAULT_CHUNK_SIZE_B
        self.local_path = local_path
        self.s3_resource = s3_resource

    def get_bucket_obj(self):
        return self.s3_client.head_object(Bucket=self.bucket_name, Key=self.s3_key)

    def get_key(self):
        bucket = self.get_bucket_obj()
        LOGGER.info(f"Getting key %s from bucket %s", self.s3_key, self.bucket_name)
        key_object = bucket.get_key(self.s3_key)
        if key_object is None:
            raise ValueError(f"Key {self.s3_key} not found in bucket {self.bucket_name}")
        return key_object

    def get_file_size(self):
        response = self.s3_client.head_object(Bucket=self.bucket_name, Key=self.s3_key)
        LOGGER.info("File size %s", response['ContentLength'])
        return response['ContentLength']

    def download_small_file(self):
        self.s3_client.download_file(self.bucket_name, self.s3_key, self.local_path)

    def download_file_in_parts(self, start_idx, file_size):
        start = start_idx
        end = min(start + self.chunk_size, file_size)
        LOGGER.info("Downloading bytes %s to %s", start, end)
        self.s3_client.download_fileobj(
            self.bucket_name,
            self.s3_key,
            self.local_path,
            ExtraArgs={'Range': f'bytes={start}-{end}'}
        )

    def download_file(self):
        file_size = self.get_file_size()
        LOGGER.info("File size %s", file_size)
        if file_size < self.chunk_size:
            self.download_small_file()
        else:
            LOGGER.info("Downloading %s in chunks of %s bytes", self.s3_key, self.chunk_size)
             # Create a list of chunk ranges
             # Use gevent to download each chunk in parallel
             # Use a generator to yield the chunks
            chunk_list = range(0, file_size, self.chunk_size)
            gevent.joinall([
                gevent.spawn(self.download_file_in_parts, chunk, file_size)
                for chunk in chunk_list
            ])