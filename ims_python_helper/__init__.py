#
# MIT License
#
# (C) Copyright 2018-2022 Hewlett Packard Enterprise Development LP
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

"""
Cray Image Management Service ImsHelper Class
"""
import hashlib
import json
import logging
import tempfile
from datetime import datetime

import sys
from pkg_resources import get_distribution

# CASMCMS-4926: Adjust import path while using this library to find
# provided, version pinned libraries outside of the context of the Base OS
# installed locations. Insert at position 0 so provided source is always
# preferred; this allows fallback to the nominal system locations once
# the base OS provided RPM content reaches parity.
sys.path.insert(0, '/opt/cray/crayctl/lib/python2.7/site-packages')

# pylint: disable=wrong-import-position
from botocore.exceptions import ClientError  # noqa: E402
import boto3  # noqa: E402
import requests  # noqa: E402
from requests.adapters import HTTPAdapter  # noqa: E402
from requests.packages.urllib3.util.retry import Retry  # noqa: E402
# pylint: enable=wrong-import-position

LOGGER = logging.getLogger(__name__)

DEFAULT_IMS_API_URL = 'https://api-gw-service-nmn.local/apis/ims'


class ImsHelper(object):
    """
    IMS Helper routines
    """

    def __init__(
            self, ims_url=DEFAULT_IMS_API_URL, session=None, s3_access_key=None,  # pylint: disable=unused-argument
            s3_secret_key=None, s3_endpoint=None, s3_bucket=None, s3_ssl_verify=None, **_kwargs
    ):
        version = get_distribution('ims-python-helper').version
        self.ims_url = ims_url.lstrip('/')
        self.session = session or requests.session()
        self.session.headers.update(
            {'User-Agent': 'ims-python-helper/%s' % version}
        )

        # Creates a URL retry object and HTTP adapter to use with our session.
        # This allows us to interact with other services in a more resilient
        # manner.
        retries = Retry(total=10, backoff_factor=2, status_forcelist=[502, 503, 504])
        self.session.mount(self.ims_url, HTTPAdapter(max_retries=retries))

        # Setup the connection to S3
        self.s3_bucket = s3_bucket
        s3args = ('s3',)
        s3kwargs = {
            'endpoint_url': s3_endpoint,
            'aws_access_key_id': s3_access_key,
            'aws_secret_access_key': s3_secret_key,
            'verify': False if not s3_ssl_verify or s3_ssl_verify.lower() in ('false', 'off', 'no', 'f', '0') else s3_ssl_verify  # noqa: E402
        }

        self.s3_client = boto3.client(*s3args, **s3kwargs)
        self.s3_resource = boto3.resource(*s3args, **s3kwargs)

    @staticmethod
    def _md5(filename):
        """ Utility for efficient md5sum of a file """
        hashmd5 = hashlib.md5()
        with open(filename, "rb") as afile:
            for chunk in iter(lambda: afile.read(4096), b""):
                hashmd5.update(chunk)
        return hashmd5.hexdigest()

    def _artifact_processor(
            self, artifact_type, key, artifact, image_id=None, image_name=None,
            ims_job_id=None
    ):
        """
        Utility to upload the artifact to S3 and return the manifest.json
        entry for the artifact. IMS-specific metadata is added to the S3
        object for images.

        Args:
            artifact_type: MIME-type of the artifact
            key: Key to place the artifact in S3
            artifact: String path on filesystem of artifact file

            image_id: id of IMS image, if artifact is associated with an image
            image_name: name of image, if artifact is associated with an image
            ims_job_id: IMS job id, if artifact is associated with an IMS job

        Returns:
            The 1.0 version of the IMS manifest.json file entry for this
            specific artifact like:

            {
                "link": {
                    "path": "s3://boot-images/F6C1CC79-9A5B-42B6-AD3F-E7EFCF22CAE8/initrd",  # noqa: E501
                    "etag": "5a7531766b4fa34dfb475de137285d81",
                    "type": "s3"
                },
                "type": "Application/vnd.cray.image.initrd",
                "md5": "5a7531766b4fa34dfb475de137285d81",
            }
        """
        s3_path = 's3://%s/%s' % (self.s3_bucket, key)
        LOGGER.debug(
            "Preparing to upload: path=%s; image_id=%s", s3_path, image_id
        )

        # Add image metadata to the s3 object, if appropriate
        md5sum = self._md5(artifact)
        ExtraArgs = {'Metadata': {'md5sum': md5sum}}
        if image_name:
            ExtraArgs['Metadata']['x-shasta-ims-image-name'] = image_name
        if image_id:
            ExtraArgs['Metadata']['x-shasta-ims-image-id'] = image_id
        if ims_job_id:
            ExtraArgs['Metadata']['x-shasta-ims-job-id'] = ims_job_id

        # Upload the file
        try:
            response = self.s3_client.upload_file(
                artifact, self.s3_bucket, key, ExtraArgs=ExtraArgs
            )
        except ClientError as err:
            LOGGER.error("Error uploading %s: %s", key, err)
            raise err

        # Retrieve Object ETag
        try:
            response = self.s3_client.head_object(
                Bucket=self.s3_bucket, Key=key
            )
        except ClientError as err:
            LOGGER.error("Error retrieving %s metadata: %s", key, err)
            raise err

        return {  # 1.0 manifest file schema
            'link': {
                'path': s3_path,
                'etag': response['ETag'].replace('"', ''),
                'type': 's3',
            },
            'type': artifact_type,
            'md5': md5sum,
        }

    def _ims_job_patch_resultant_image_id(self, ims_job_id, result_id):
        """
        Update the job creation/customization record with the
        resultant_image_id
        """
        url = '/'.join([self.ims_url, 'jobs', ims_job_id])
        LOGGER.info(
            "PATCH %s resultant_image_id=%s", ims_job_id, result_id
        )
        resp = self.session.patch(url, json={'resultant_image_id': result_id})
        LOGGER.debug(resp.json())
        resp.raise_for_status()
        return resp.json()

    def _ims_job_patch_job_status(self, ims_job_id, ims_job_status):
        """ Update job creation/customization record with a new status """
        url = '/'.join([self.ims_url, 'jobs', ims_job_id])
        LOGGER.info("PATCH %s status=%s", url, ims_job_status)
        resp = self.session.patch(url, json={'status': ims_job_status})
        LOGGER.debug(resp.json())
        resp.raise_for_status()
        return resp.json()

    def _ims_image_create(self, name):
        """ Create a new image record """
        url = '/'.join([self.ims_url, 'images'])
        LOGGER.info("POST %s name=%s", url, name)
        resp = self.session.post(url, json={'name': name})
        resp.raise_for_status()
        return resp.json()

    def _ims_image_patch(self, image_id, data):
        """ PATCH an image record with the data provided """
        url = '/'.join([self.ims_url, 'images', image_id])
        LOGGER.info("PATCH %s id=%s, data=%s", url, image_id, data)
        resp = self.session.patch(url, json=data)
        LOGGER.debug(resp.json())
        resp.raise_for_status()
        return resp.json()

    def _ims_image_delete(self, image_id):
        """ Delete IMS image record by id """
        url = '/'.join([self.ims_url, 'images', image_id])
        LOGGER.info("DELETE %s", url)
        resp = self.session.delete(url)
        resp.raise_for_status()
        return resp

    def image_upload_artifacts(
            self, image_name, ims_job_id=None, rootfs=None, kernel=None,
            initrd=None, debug=None, boot_parameters=None
    ):
        """
        Utility function to upload and register any image artifacts with the
        IMS service. The rootfs, kernel, initrd, debug and boot_parameters
        values are expected to be full paths to readable files. Only squashfs
        is currently supported for the rootfs parameter.
        """
        # Stub out the return value of this method
        ret = {
            'result': 'success',
            'ims_image_record': self._ims_image_create(image_name),
            'ims_image_artifacts': []
        }

        # Create a skeleton image to get an image id
        image_id = ret['ims_image_record']['id']

        # Generate the arguments (artifacts) to be sent for upload
        key = "{}/%s".format(image_id)
        to_upload = []
        if rootfs:
            to_upload.append(('application/vnd.cray.image.rootfs.squashfs', key % 'rootfs', rootfs[0]))  # noqa: E501
        if kernel:
            to_upload.append(('application/vnd.cray.image.kernel', key % 'kernel', kernel[0]))  # noqa: E501
        if initrd:
            to_upload.append(('application/vnd.cray.image.initrd', key % 'initrd', initrd[0]))  # noqa: E501
        if debug:
            to_upload.append(('application/vnd.cray.image.debug.kernel', key % 'debug_kernel', debug[0]))  # noqa: E501
        if boot_parameters:
            to_upload.append(('application/vnd.cray.image.parameters.boot', key % 'boot_parameters',
                              boot_parameters[0]))  # noqa: E501

        # Upload the files in series
        LOGGER.info(
            "Uploading %s files for image_id=%s", len(to_upload), image_id
        )
        upload_results = []
        for upload in to_upload:
            try:
                upload_results.append(self._artifact_processor(
                    *upload, image_id=image_id, image_name=image_name,
                    ims_job_id=ims_job_id
                ))
            except ClientError as err:
                LOGGER.error("Failed upload of artifact=%s.", upload[1])
                LOGGER.info(
                    "Removing image_id=%s; image_name=%s", image_id, image_name
                )

                # Try to remove the artifacts that were uploaded as well as the
                # image itself. If either of these fail, raise the original
                # exception.
                try:
                    self._ims_image_delete(image_id)
                except Exception:  # pylint: disable=bare-except, broad-except
                    pass

                try:
                    bucket = self.s3_resource.Bucket(self.s3_bucket)
                    bucket.objects.filter(Prefix=image_id + "/").delete()
                except Exception:  # pylint: disable=bare-except, broad-except
                    pass

                raise err

        # Build the manifest file with the results from the uploads
        manifest = {
            'version': '1.0',
            'created': str(datetime.now()),
            'artifacts': upload_results,
        }
        with tempfile.NamedTemporaryFile(delete=False) as manifest_file:
            with open(manifest_file.name, 'w') as f:
                json.dump(manifest, f, sort_keys=True, indent=4)
            manifest_file_name = manifest_file.name
        LOGGER.info(
            "Generated manifest file for image_id=%s; ims_job_id=%s",
            image_id, ims_job_id
        )
        LOGGER.debug("%s", manifest)

        # Upload the manifest file itself
        try:
            manifest_meta = self._artifact_processor(
                'application/json', key % 'manifest.json', manifest_file_name
            )
        except ClientError as err:
            LOGGER.error("Failed to upload %s", key % 'manifest.json')
            LOGGER.info(
                "Removing image_id=%s; image_name=%s", image_id, image_name
            )
            # Try to remove the artifacts that were uploaded as well as the
            # image itself. If either of these fail, raise the original
            # exception.
            try:
                self._ims_image_delete(image_id)
            except Exception:  # pylint: disable=bare-except, broad-except
                pass

            try:
                bucket = self.s3_resource.Bucket(self.s3_bucket)
                bucket.objects.filter(Prefix=image_id + "/").delete()
            except Exception:  # pylint: disable=bare-except, broad-except
                pass

            raise err

        # Update the image record with the manifest info
        ret['ims_image_record'] = self._ims_image_patch(
            image_id, {'link': manifest_meta['link']}
        )

        # If this was part of a job, update the job with the new image id
        if ims_job_id:
            ret['ims_job_record'] = self._ims_job_patch_resultant_image_id(
                ims_job_id, image_id
            )

        ret['ims_image_artifacts'] = upload_results + [manifest_meta]
        return ret

    def image_set_job_status(self, ims_job_id, job_status):
        """
        Utility function to set the job status in the IMS service.
        """
        LOGGER.info(
            "image_set_job_status: {{ims_job_id: %s, job_status: %s}}",
            ims_job_id, job_status
        )
        return {
            'result': 'success',
            'ims_job_record': self._ims_job_patch_job_status(
                ims_job_id, job_status
            ),
        }

    def recipe_upload(self, name, filepath, distro, template_dictionary):
        """
        Utility function that uploads a recipe to S3 and registers it with IMS.
        Only gzipped tar recipe archives are supported.

        This attempts to perform the recipe upload in an idempotent manner,
        such that calling this function again will either:
          a) upload the recipe if it's not present, or
          2) upload the recipe if a previous recipe upload failed
          c) do nothing if it's already present.

        Args:
            name: name of the recipe.
            filepath: path to the recipe .tar.gz file.
            distro: one of `sles12`, `sle15`, or `centos7`

        Returns:
            The [new/updated/existing] recipe in json format.
        """

        def s3_upload_recipe(name, recipe_id, filepath):
            """
            Helper function to upload a recipe to S3 and handle errors of the
            upload failed.
            """
            try:
                return self._artifact_processor(
                    'application/x-compressed-tar',
                    'recipes/{}/recipe.tar.gz'.format(recipe_id), filepath
                )
            except ClientError as err:
                LOGGER.error("Error occurred trying to upload recipe: %s", err)
                LOGGER.info(
                    "Removing recipe_id=%s; recipe_name=%s", recipe_id, name
                )
                try:
                    self._ims_recipe_delete(recipe_id)
                except Exception as delete_err:
                    LOGGER.error("Unable to delete recipe: %s", delete_err)
                    raise err

        LOGGER.info(
            "Starting recipe_upload; name=%s, file=%s, distro=%s, template_dictionary=%s",
            name, filepath, distro, template_dictionary
        )

        # Get all recipes and filter for the current recipe
        recipes = self._ims_recipes_get()
        LOGGER.debug("Existing recipes: %s", recipes)
        filtered_recipes = [r for r in recipes if r['name'] == name]

        # No recipe match, this is a new one that needs to be uploaded.
        if not filtered_recipes:
            LOGGER.info(
                "A recipe with the %r name wasn't found. "
                "Creating initial recipe...", name
            )

            # Create the recipe record
            recipe_data = self._ims_recipe_create(name, distro, template_dictionary)
            LOGGER.info("New recipe created: %s", recipe_data)

            # Go on, upload it
            recipe_meta = s3_upload_recipe(name, recipe_data['id'], filepath)

            # Patch the recipe record with the link information
            return self._ims_recipe_patch(
                recipe_data['id'], {'link': recipe_meta['link']}
            )

        # A recipe matched, hopefully only one.
        recipe = filtered_recipes[0]

        # Recipe exists, but no link info exists, meaning it was created but
        # was not successfully uploaded and associated.
        if recipe['link'] is None:
            LOGGER.info(
                "The %r recipe already exists. But has not been uploaded yet. "
                "Uploading now.", name
            )

            # Go on, upload it
            recipe_meta = s3_upload_recipe(name, recipe['id'], filepath)

            # Patch the recipe record with the link information
            return self._ims_recipe_patch(
                recipe['id'], {'link': recipe_meta['link']}
            )

        LOGGER.info("The %r recipe already exists; nothing to do.", name)
        return recipe

    def _ims_recipes_get(self):
        """
        Get all recipes in IMS

        Args: None
        Returns:
            Collection of recipes, which should be a list of dicts
        Raises:
            requests.exceptions.HTTPError
        """
        url = '/'.join([self.ims_url, 'recipes'])
        LOGGER.info("GET %s", url)
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()

    def _ims_recipe_create(self, name, linux_distribution=None, template_dictionary=None):
        """
        Create an IMS Recipe record of a kiwi-ng recipe.

        Args:
            name: recipe name
            linux_distribution: one of `sles12`, `sle15`, or `centos7`
        Returns:
            IMS recipe response
        Raises:
            requests.exceptions.HTTPError
        """
        url = '/'.join([self.ims_url, 'recipes'])

        if template_dictionary:
            template_dictionary = [{'key': k, 'value': v} for k, v in template_dictionary.items()]

        LOGGER.info(
            "POST %s name=%s, linux_distribution=%s, template_dictionary=%s",
            name, url, linux_distribution, template_dictionary
        )

        body = {
            'recipe_type': 'kiwi-ng',
            'linux_distribution': linux_distribution,
            'template_dictionary': template_dictionary,
            'name': name,
        }
        resp = self.session.post(url, json=body)
        resp.raise_for_status()
        return resp.json()

    def _ims_recipe_patch(self, recipe_id, data):
        """ PATCH an recipe record with the data provided """
        url = '/'.join([self.ims_url, 'recipes', recipe_id])
        LOGGER.info("PATCH %s id=%s, data=%s", url, recipe_id, data)
        resp = self.session.patch(url, json=data)
        resp.raise_for_status()
        return resp.json()

    def _ims_recipe_delete(self, ident):
        """
        Delete IMS recipe record by id

        Args:
            ident: IMS recipe id
        Returns:
            IMS recipe DELETE response.
        Raises:
            requests.exceptions.HTTPError
        """
        url = '/'.join([self.ims_url, 'recipes', ident])
        LOGGER.info("DELETE %s", url)
        resp = self.session.delete(url)
        resp.raise_for_status()
        return resp
