#
# MIT License
#
# (C) Copyright 2018-2023, 2025 Hewlett Packard Enterprise Development LP
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
import io
import json
import logging
import sys
import tempfile
from datetime import datetime
from time import sleep
from typing import Dict, List, Optional
from urllib.parse import urlparse

from importlib.metadata import version

# CASMCMS-4926: Adjust import path while using this library to find
# provided, version pinned libraries outside of the context of the Base OS
# installed locations. Insert at position 0 so provided source is always
# preferred; this allows fallback to the nominal system locations once
# the base OS provided RPM content reaches parity.
sys.path.insert(0, '/opt/cray/crayctl/lib/python2.7/site-packages')

# pylint: disable=wrong-import-position
import boto3  # noqa: E402
from botocore.config import Config
from boto3.s3.transfer import TransferConfig
import requests  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402
from requests.adapters import HTTPAdapter  # noqa: E402
from requests.packages.urllib3.util.retry import Retry  # noqa: E402

# pylint: enable=wrong-import-position

LOGGER = logging.getLogger(__name__)

DEFAULT_IMS_API_URL = 'https://api-gw-service-nmn.local/apis/ims'

INITRD_ARTIFACT_TYPE = 'application/vnd.cray.image.initrd'
KERNEL_ARTIFACT_TYPE = 'application/vnd.cray.image.kernel'
SQUASHFS_ARTIFACT_TYPE = 'application/vnd.cray.image.rootfs.squashfs'
DEBUG_KERNEL_ARTIFACT_TYPE = 'application/vnd.cray.image.debug.kernel'
BOOT_PARAMS_ARTIFACT_TYPE = 'application/vnd.cray.image.parameters.boot'

# Set up transfer configuration for large file downloads
boto3_transfer_config = TransferConfig(
    multipart_threshold=8 * 1024 * 1024,  # Files above 8MB will be multipart
    max_concurrency=20,  # Maximum number of threads to use for parallel downloads
    multipart_chunksize=8 * 1024 * 1024,  # Each part of the file is 8MB
    use_threads=True  # Enable multi-threading for downloads
)

# Define boto3 retry settings
boto3_retry_config = Config(
    retries={
        'max_attempts': 20,  # Number of retries
        'mode': 'standard',  # Retry mode, 'standard' is most common
    },
    connect_timeout = 10,    # Connection timeout in seconds
    read_timeout = 20,       # Read timeout in seconds
    max_pool_connections=20  # Maximum number of connections in the pool
)


class ImsImagesExistWithName(Exception):
    """A populated image with some given name already exists in IMS."""

    def __init__(self, name: str, image_records: List[Dict], *args):
        super().__init__(*args)
        self.name = name
        self.image_records = image_records

    def __str__(self):
        return "images with name \"{}\" already exist in IMS (ID(s): {})".format(
            self.name,
            ', '.join(r.get("id") for r in self.image_records)
        )


class ImsHelper(object):
    """
    IMS Helper routines
    """

    def __init__(
            self, ims_url=DEFAULT_IMS_API_URL, session=None, s3_access_key=None,  # pylint: disable=unused-argument
            s3_secret_key=None, s3_endpoint=None, s3_bucket=None, s3_ssl_verify=None, **_kwargs
    ):
        LOGGER.info("S3 End Point %s", s3_endpoint)
        module_version = version('ims-python-helper')
        self.ims_url = ims_url.lstrip('/')
        self.session = session or requests.session()
        self.session.headers.update(
            {'User-Agent': 'ims-python-helper/%s' % module_version}
        )

        # Creates a URL retry object and HTTP adapter to use with our session.
        # This allows us to interact with other services in a more resilient
        # manner.
        retries = Retry(total=10, backoff_factor=2, status_forcelist=[502, 503, 504])
        self.session.mount(self.ims_url, HTTPAdapter(max_retries=retries))

        # Setup the connection to S3
        self.s3_bucket = s3_bucket
        LOGGER.info("S3 Bucket=%s", self.s3_bucket)
        s3args = ('s3', )
        s3kwargs = {
            'endpoint_url': s3_endpoint,
            'aws_access_key_id': s3_access_key,
            'aws_secret_access_key': s3_secret_key,
            'verify': False if not s3_ssl_verify or s3_ssl_verify.lower() in ('false', 'off', 'no', 'f', '0') else s3_ssl_verify  # noqa: E402
        }

        self.s3_client = boto3.client(service_name='s3', config=boto3_retry_config, **s3kwargs)
        self.s3_resource = boto3.resource(*s3args, **s3kwargs)

    @staticmethod
    def _md5(filename):
        """ Utility for efficient md5sum of a file """
        hashmd5 = hashlib.md5()
        with open(filename, "rb") as afile:
            for chunk in iter(lambda: afile.read(4096), b""):
                hashmd5.update(chunk)
        return hashmd5.hexdigest()

    def get_image_manifest(self, record: dict) -> Optional[dict]:
        """Get a parsed manifest for an IMS image

        Args:
            record: an image record from IMS

        Returns:
            the parsed JSON manifest which the image points to,
            or None if there is no associated manifest or link,
            or if there is a problem retrieving the manifest
            from S3.
        """
        link = record.get('link')
        if not link:
            return None

        with io.BytesIO() as manifest_buffer:
            manifest_url = link.get('path')
            if not manifest_url:
                return None
            parsed_manifest_path = urlparse(manifest_url)
            bucket_name = parsed_manifest_path.netloc
            manifest_path = parsed_manifest_path.path.strip('/')

            try:
                LOGGER.debug("Retrieving manifest; bucket: %s, path: %s",
                             bucket_name, manifest_path)
                self.s3_client.download_fileobj(bucket_name, manifest_path, manifest_buffer)
            except ClientError as err:
                LOGGER.warning('Could not retrieve manifest from URL "%s"; skipping image (%s)',
                               manifest_url, err)
                return None
            return json.loads(manifest_buffer.getvalue().decode())

    def artifacts_match_image_record(
            self,
            record: dict,
            name: str,
            rootfs_path: Optional[str] = None,
            kernel_path: Optional[str] = None,
            initrd_path: Optional[str] = None,
            debug_kernel: Optional[str] = None,
            boot_params: Optional[str] = None,
    ) -> bool:
        """Check if all the artifacts match a single image record.

        Args:
            record: an image record from IMS
            name: the name of the image associated with the artifacts
                given in the paths in the following arguments
            rootfs_path: path to the rootfs artifact, if provided
            kernel_path: path to the kernel artifact, if provided
            initrd_path: path to the initrd artifact, if provided
            debug_kernel: path to the debug kernel artifact, if provided
            boot_params: path to the kernel boot parameters, if provided

        Returns:
            True if the artifacts at the given paths have the same MD5
            checksums listed in the image record, and the name matches,
            or False otherwise.
        """
        manifest = self.get_image_manifest(record)
        if manifest is None:
            return False

        cmp_dict = {'name': name}
        if rootfs_path:
            cmp_dict['rootfs'] = self._md5(rootfs_path)
        if kernel_path:
            cmp_dict['kernel'] = self._md5(kernel_path)
        if initrd_path:
            cmp_dict['initrd'] = self._md5(initrd_path)
        if debug_kernel:
            cmp_dict['debug_kernel'] = self._md5(debug_kernel)
        if boot_params:
            cmp_dict['boot_params'] = self._md5(boot_params)

        cmp_dict_key_to_artifact_type = {
            'rootfs': SQUASHFS_ARTIFACT_TYPE,
            'kernel': KERNEL_ARTIFACT_TYPE,
            'initrd': INITRD_ARTIFACT_TYPE,
            'debug_kernel': DEBUG_KERNEL_ARTIFACT_TYPE,
            'boot_params': BOOT_PARAMS_ARTIFACT_TYPE,
        }

        manifest_cmp_dict = {'name': name}
        for key, artifact_type in cmp_dict_key_to_artifact_type.items():
            for artifact in manifest.get('artifacts', []):
                if artifact.get('type') == artifact_type:
                    manifest_cmp_dict[key] = artifact['md5']
        return manifest_cmp_dict == cmp_dict

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

        # Upload the file until it successfully takes. Note: This means we could
        # be waiting indefinitely for s3 to succeed
        attempt = 1
        while True:
            if attempt <= 300:
                attempt+=1
            try:
                response = self.s3_client.upload_file(
                    artifact, self.s3_bucket, key, ExtraArgs=ExtraArgs
                )
                break
            except Exception as err:  # pylint: disable=bare-except, broad-except
                LOGGER.error("Error uploading %s: %s", key, err)
                LOGGER.error("Re-attempting in %s seconds..." %(attempt))
                sleep(attempt)

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

    def _ims_images_get(self) -> List[Dict]:
        """Get a list of images from IMS"""
        url = '/'.join([self.ims_url, 'images'])
        LOGGER.debug("GET %s", url)
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()

    def _ims_image_get(self, image_id: str) -> Dict:
        """Get a specific image from IMS"""
        url = '/'.join([self.ims_url, 'images', image_id])
        LOGGER.debug("GET %s", url)
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()

    def _ims_image_create(self, name, arch=None):
        """ Create a new image record """
        url = '/'.join([self.ims_url, 'images'])
        LOGGER.debug("POST %s name=%s", url, name)
        jsonData = {'name': name}
        if arch != None:
            jsonData = {'name': name, 'arch':arch}
        resp = self.session.post(url, json=jsonData)
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
        LOGGER.debug("DELETE %s", url)
        resp = self.session.delete(url)
        resp.raise_for_status()
        return resp

    def get_empty_image_record_for_name(
            self,
            image_name: str,
            skip_existing: bool,
            arch=None
    ) -> Dict:
        """Get an empty record for an image in IMS with the given name.

        If an image with the given name does not exist, an empty image
        record will be created. If an empty image record exists, it will
        be returned. If an uploaded image record exists, then
        ImsImageExistsWithName will be raised with the given image record
        if `skip_existing` is True, and a new image will be created and
        returned if `skip_existing` is False.

        Args:
            image_name: the desired name of the image
            skip_existing: if True, check if an image exists with the name
                `image_name`. If it exists, check if it has a `link` attribute
            arch: arch of the image

        Returns:
            dict: the empty IMS image record for the image, containing e.g.
                the name, the id, and the creation timestamp

        Raises:
            ImsImageExistsWithName: if the image already exists and
                has been uploaded, and `skip_existing` is True
        """
        if skip_existing:
            matching_uploaded_images = []
            matching_empty_images = []
            try:
                existing_images = self._ims_images_get()
                for image in existing_images:
                    if image.get("name") == image_name:
                        if image.get("link"):
                            matching_uploaded_images.append(image)
                        else:
                            matching_empty_images.append(image)
                if matching_uploaded_images:
                    raise ImsImagesExistWithName(image_name, matching_uploaded_images)
                if matching_empty_images:
                    LOGGER.info("Found image(s) without artifact links: %s"
                                ", ".join(i["id"] for i in matching_empty_images))
                    empty_image = matching_empty_images.pop()
                    LOGGER.info("Uploading image artifacts to empty image with ID \"%s\"",
                                empty_image["id"])
                    return empty_image
            except requests.HTTPError as err:
                LOGGER.warning("Could not retrieve existing images: %s", err)

        LOGGER.info("Creating image with name \"%s\"", image_name)
        return self._ims_image_create(image_name, arch=arch)

    def image_upload_artifacts(
            self, image_name, ims_job_id=None, rootfs=None, kernel=None,
            initrd=None, debug=None, boot_parameters=None, skip_existing=False, arch=None
    ):
        """
        Utility function to upload and register any image artifacts with the
        IMS service. The rootfs, kernel, initrd, debug and boot_parameters
        values are expected to be full paths to readable files. Only squashfs
        is currently supported for the rootfs parameter.

        If `skip_existing` is True and any number of images with name
        `image_name` and a `link` attribute already exist in IMS, then this
        function will return one of those existing image record without
        uploading anything if the checksums of all artifacts in any of those
        images matches the checksums of the artifacts passed into this function
        (i.e. `rootfs`, `kernel`, `initrd`, `debug`, and `boot_parameters`.)
        """

        if rootfs:
            rootfs = rootfs[0]
        if kernel:
            kernel = kernel[0]
        if initrd:
            initrd = initrd[0]
        if debug:
            debug = debug[0]
        if boot_parameters:
            boot_parameters = boot_parameters[0]

        # Stub out the return value of this method
        ret = {
            'result': 'success',
            'ims_image_artifacts': []
        }

        try:
            image_record = self.get_empty_image_record_for_name(image_name, skip_existing, arch=arch)
        except ImsImagesExistWithName as exc:
            for matching_image_record in exc.image_records:
                LOGGER.debug("Image with name \"%s\" already exists in IMS with ID \"%s\"; "
                            "checking contents", image_name, matching_image_record['id'])
                if self.artifacts_match_image_record(matching_image_record, image_name, rootfs, kernel,
                                                     initrd, debug, boot_parameters):
                    LOGGER.info("Artifacts match checksums listed in manifest for image with name \"%s\"; skipping",
                                   image_name)
                    ret["ims_image_record"] = matching_image_record
                    return ret
                else:
                    LOGGER.info("Artifacts in existing image with ID \"%s\" do not match; checking other images",
                                matching_image_record["id"])
            LOGGER.info("No existing image with name \"%s\" contains matching artifacts",
                        image_name)
            image_record = self._ims_image_create(image_name, arch=arch)

        ret["ims_image_record"] = image_record
        image_id = ret["ims_image_record"]["id"]

        # Generate the arguments (artifacts) to be sent for upload
        key = "{}/%s".format(image_id)
        to_upload = []
        if rootfs:
            to_upload.append((SQUASHFS_ARTIFACT_TYPE, key % 'rootfs', rootfs))  # noqa: E501
        if kernel:
            to_upload.append((KERNEL_ARTIFACT_TYPE, key % 'kernel', kernel))  # noqa: E501
        if initrd:
            to_upload.append((INITRD_ARTIFACT_TYPE, key % 'initrd', initrd))  # noqa: E501
        if debug:
            to_upload.append((DEBUG_KERNEL_ARTIFACT_TYPE, key % 'debug_kernel', debug))  # noqa: E501
        if boot_parameters:
            to_upload.append((BOOT_PARAMS_ARTIFACT_TYPE, key % 'boot_parameters',
                              boot_parameters))  # noqa: E501
        if not to_upload:
            LOGGER.info("No image artifacts supplied for image %s; not uploading anything", image_name)
            return ret

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
                LOGGER.error("Failed upload of artifact=%s", upload[1])
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

    def recipe_upload(self, name, filepath, distro, template_dictionary=None, 
                      arch=None, require_dkms=None):
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
        def artifact_path(recipe_id: str) -> str:
            """Get the artifact path within an S3 bucket.

            Args:
                recipe_id: IMS ID of the recipe

            Returns:
                the path to the recipe artifact within some S3 bucket.
            """
            return 'recipes/{}/recipe.tar.gz'.format(recipe_id)

        def s3_upload_recipe(name, recipe_id, filepath):
            """
            Helper function to upload a recipe to S3 and handle errors of the
            upload failed.
            """
            try:
                return self._artifact_processor(
                    'application/x-compressed-tar',
                    artifact_path(recipe_id), filepath
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

        if template_dictionary:
            LOGGER.debug(
                "Starting recipe_upload; name=%s, file=%s, distro=%s, template_dictionary=%s",
                name, filepath, distro, template_dictionary
            )
        else:
            LOGGER.debug(
                "Starting recipe_upload; name=%s, file=%s, distro=%s",
                name, filepath, distro
            )

        # Get all recipes and filter for the current recipe
        recipes = self._ims_recipes_get()
        LOGGER.debug("Existing recipes: %s", recipes)
        filtered_recipes = [r for r in recipes if r['name'] == name]

        # At least one recipe matched the given name. Check if any have the same artifacts.
        empty_recipe = None
        for recipe in filtered_recipes:
            if recipe['link']:
                try:
                    recipe_template_dict = {pair['key']: pair['value'] for pair in recipe.get('template_dictionary', [])}
                    recipe_obj = self.s3_resource.Object(self.s3_bucket, artifact_path(recipe['id']))
                    if recipe_obj.metadata.get('md5sum') == self._md5(filepath) \
                            and template_dictionary == recipe_template_dict:
                        LOGGER.info('Recipe "%s" has already been uploaded (IMS recipe with ID "%s" and template '
                                    'dictionary %r already exists); nothing to do',
                                    name, recipe['id'], template_dictionary)
                        return recipe

                except ClientError as err:
                    LOGGER.error("Could not retrieve S3 object metadata for recipe %s; %s", recipe['id'], err)
            else:
                empty_recipe = recipe

        # Recipe exists, but no link info exists, meaning it was created but
        # was not successfully uploaded and associated.
        if empty_recipe:
            LOGGER.info(
                "The %r recipe already exists with ID %s but has not been uploaded yet. "
                "Uploading now", name, empty_recipe['id']
            )

            # Go on, upload it
            recipe_meta = s3_upload_recipe(name, empty_recipe['id'], filepath)

            # Patch the recipe record with the link information
            patch_data = {'link': recipe_meta['link']}
            if template_dictionary:
                patch_data['template_dictionary'] = template_dictionary

            return self._ims_recipe_patch(
                empty_recipe['id'],
                patch_data,
            )

        LOGGER.info("No recipe with matching name, artifacts, and template "
                    "dictionary was found. Creating new recipe...")
        new_recipe = self._ims_recipe_create(name, distro, template_dictionary, arch=arch, require_dkms=require_dkms)
        LOGGER.info("New recipe created: %s", new_recipe)

        # Go on, upload it
        recipe_meta = s3_upload_recipe(name, new_recipe['id'], filepath)

        # Patch the recipe record with the link information
        return self._ims_recipe_patch(
            new_recipe['id'], {'link': recipe_meta['link']}
        )

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
        LOGGER.debug("GET %s", url)
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()

    def _ims_recipe_create(self, name, linux_distribution=None, template_dictionary=None, arch=None, require_dkms=None):
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
            LOGGER.debug(
                "POST %s name=%s, linux_distribution=%s, template_dictionary=%s",
                name, url, linux_distribution, template_dictionary
            )
        else:
            LOGGER.debug(
                "POST %s name=%s, linux_distribution=%s",
                name, url, linux_distribution
            )

        body = {
            'recipe_type': 'kiwi-ng',
            'linux_distribution': linux_distribution,
            'name': name,
        }

        if template_dictionary:
            body['template_dictionary'] = template_dictionary

        if arch:
            body['arch'] = arch

        if require_dkms:
            body['require_dkms'] = require_dkms

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
        LOGGER.debug("DELETE %s", url)
        resp = self.session.delete(url)
        resp.raise_for_status()
        return resp
