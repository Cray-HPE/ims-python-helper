#
# MIT License
#
# (C) Copyright 2018-2019, 2021-2023 Hewlett Packard Enterprise Development LP
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

"""
Unit tests for resources/images.py
"""

import json
import os
import sys
import unittest
import uuid
from unittest.mock import patch

import botocore.exceptions
import mock
import requests
import responses

# Add ims_python_helper to path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ims_python_helper import ImsHelper, ImsImagesExistWithName
from testtools import TestCase

UPLOAD_TIMEOUT = 500


class BaseTestImage(TestCase):

    def setUp(self):
        super().setUp()

        self.test_domain = 'https://api-gw-service-nmn.local'
        self.ims_url = '{}/apis/ims'.format(self.test_domain)
        self.session = requests.session()

        self.test_image_job_id = str(uuid.uuid4())
        self.test_artifact_name = "test_image"
        self.test_rootfs = ['/tmp/rootfs.sqsh']
        self.test_kernel = ['/tmp/vmlinuz']
        self.test_initrd = ['/tmp/initramfs']
        self.test_debug = []
        self.test_other = []
        self.test_job_status = "waiting_on_user"

        self.existing_ims_images = [
            {
                "created": "2022-01-01T00:00:00.00000+00:00",
                "id": "f6c13ec7-89d1-4420-8f1d-1736b2d235cb",
                "link": {
                    "etag": "d3b07384d113edec49eaa6238ad5ff00",
                    "path": "s3://boot-images/f6c13ec7-89d1-4420-8f1d-1736b2d235cb/manifest.json",
                    "type": "s3"
                },
                "name": "image_that_has_been_uploaded"
            },
            {
                "created": "2022-01-01T00:00:00.00000+00:00",
                "id": "d8a34ae4-ff5d-4ff7-b625-27e89006a428",
                "name": "image_created_but_not_uploaded"
            },
        ]
        self.new_ims_image = {
            "created": "2022-01-01T00:00:00.00000+00:00",
            "id": "602f9848-835c-49c8-833c-0fd4bb5c526f",
            "name": "newly_created_image"
        }

        self.rootfs = 'rootfs.squashfs'
        self.kernel = 'vmlinuz'
        self.initrd = 'barebones.initrd'

        self.rootfs_md5 = "29f6a020e682ea8ef6f7728cc8e055a3"
        self.kernel_md5 = "6fc418e57f3d86c9b66e522f74cc1909"
        self.initrd_md5 = "42488bf5d1400e6f563a39aab66292a6"
        self.debug_md5 = "213c06c51ed7df6f08e02866c7758cb8"
        self.params_md5 = "88e292b9447efefa8460bb2b17d043c0"
        self.manifest = {
            "artifacts": [
                {
                    "link": {
                        "etag": self.rootfs_md5,
                        "path": "s3://boot-images/da370218-b174-4b48-bdb1-f85d0b5fbccb/rootfs",
                        "type": "s3"
                    },
                    "md5": self.rootfs_md5,
                    "type": "application/vnd.cray.image.rootfs.squashfs"
                },
                {
                    "link": {
                        "etag": self.kernel_md5,
                        "path": "s3://boot-images/da370218-b174-4b48-bdb1-f85d0b5fbccb/kernel",
                        "type": "s3"
                    },
                    "md5": self.kernel_md5,
                    "type": "application/vnd.cray.image.kernel"
                },
                {
                    "link": {
                        "etag": self.initrd_md5,
                        "path": "s3://boot-images/da370218-b174-4b48-bdb1-f85d0b5fbccb/initrd",
                        "type": "s3"
                    },
                    "md5": self.initrd_md5,
                    "type": "application/vnd.cray.image.initrd"
                },
                {
                    "link": {
                        "etag": self.debug_md5,
                        "path": "s3://boot-images/da370218-b174-4b48-bdb1-f85d0b5fbccb/debug_kernel",
                        "type": "s3"
                    },
                    "md5": self.debug_md5,
                    "type": "application/vnd.cray.image.debug.kernel",
                },
                {
                    "link": {
                        "etag": self.params_md5,
                        "path": "s3://boot-images/da370218-b174-4b48-bdb1-f85d0b5fbccb/boot_parameters",
                        "type": "s3"
                    },
                    "md5": self.params_md5,
                    "type": "application/vnd.cray.image.parameters.boot",
                },
            ],
            "created": "2023-02-07 21:38:50.567059",
            "version": "1.0"
        }


class TestImage(BaseTestImage):
    @responses.activate
    def test_image_set_job_status(self):
        """ Test image_upload_artifacts method of the IMS Helper class """

        def patch_ims_job_response(request):
            payload = json.loads(request.body)
            resp_body = {
                'artifact_id': str(uuid.uuid4()),
                'build_env_size': '10',
                'created': '2018-11-16T21:18:56.306420+00:00',
                'id': request.path_url[15:]
            }
            if 'resultant_image_id' in payload:
                resp_body['resultant_image_id'] = payload['resultant_image_id']
            if 'status' in payload:
                resp_body['status'] = payload['status']
            return 200, {}, json.dumps(resp_body)

        patch_url = '{}/jobs/{}'.format(self.ims_url, self.test_image_job_id)
        responses.add_callback(
            responses.PATCH,
            patch_url,
            callback=patch_ims_job_response,
            content_type="application/json"
        )

        responses.add(
            responses.GET, '{}/version'.format(self.ims_url), json={"version": "1.2.3"})

        result = ImsHelper(self.ims_url, self.session).image_set_job_status(
            self.test_image_job_id,
            self.test_job_status
        )

        self.assertItemsEqual(result.keys(),
                              ['result', 'ims_job_record'],
                              'returned keys not the same')
        self.assertEqual(result['result'], 'success')
        self.assertEqual(self.test_image_job_id, result['ims_job_record']['id'])
        self.assertEqual(result['ims_job_record']['status'], self.test_job_status)

    @responses.activate
    def test_get_empty_image_record_for_new_image(self):
        """Test images are created when getting an empty image that doesn't exist"""
        responses.add(
            responses.GET, f'{self.ims_url}/images', json=self.existing_ims_images
        )
        responses.add(responses.POST, f'{self.ims_url}/images', status=201, json=self.new_ims_image)
        result = ImsHelper(self.ims_url, self.session).get_empty_image_record_for_name('newly_created_image', skip_existing=True)
        assert result == self.new_ims_image

    @responses.activate
    def test_get_empty_image_record_for_existing_empty_image(self):
        """Test images are not uploaded when an empty image of the same name already exists in IMS."""
        responses.add(
            responses.GET, f'{self.ims_url}/images', json=self.existing_ims_images
        )
        responses.add(responses.POST, f'{self.ims_url}/images', status=201)
        result = ImsHelper(self.ims_url, self.session).get_empty_image_record_for_name('image_created_but_not_uploaded', skip_existing=True)
        assert result == self.existing_ims_images[1]

    def test_get_existing_image_record(self):
        """Test that an "ims_image_record" key is returned by image_upload_artifacts()"""
        image_name = self.new_ims_image['name']
        with mock.patch('ims_python_helper.ImsHelper.get_empty_image_record_for_name',
                        return_value=self.new_ims_image):
            result = ImsHelper(self.ims_url, self.session).image_upload_artifacts(image_name, skip_existing=False)
            self.assertEqual(result['ims_image_record'], self.new_ims_image)

    @responses.activate
    def test_get_empty_image_record_for_existing_uploaded_image(self):
        """Test images are not uploaded when a populated image of the same name already exists in IMS."""
        responses.add(
            responses.GET, f'{self.ims_url}/images', json=self.existing_ims_images
        )
        responses.add(responses.POST, f'{self.ims_url}/images', status=201)

        def should_raise():
            ImsHelper(self.ims_url, self.session).get_empty_image_record_for_name('image_that_has_been_uploaded', skip_existing=True)

        self.assertRaises(ImsImagesExistWithName, should_raise)

    @responses.activate
    def test_ims_recipes_get(self):
        """ Test _ims_recipes_get method when get a valid response from IMS. """
        exp_recipes = [{'name': 'example'}]
        responses.add(
            responses.GET, '{}/recipes'.format(self.ims_url), json=exp_recipes)
        responses.add(
            responses.GET, '{}/version'.format(self.ims_url), json={"version": "1.2.3"})
        responses.add(
            responses.GET, '{}/version'.format(self.ims_url), json={"version": "1.2.3"})

        ims_helper = ImsHelper(self.ims_url, self.session)
        recipes = ims_helper._ims_recipes_get()
        self.assertEqual(exp_recipes, recipes)

    @responses.activate
    def test_ims_recipes_get_error(self):
        """ Test _ims_recipes_get method when get an invalid response from IMS. """
        exp_error = {'title': 'Not Found'}
        responses.add(
            responses.GET, '{}/recipes'.format(self.ims_url), json=exp_error,
            status=404)
        responses.add(
            responses.GET, '{}/version'.format(self.ims_url), json={"version": "1.2.3"})

        ims_helper = ImsHelper(self.ims_url, self.session)
        self.assertRaises(
            requests.exceptions.HTTPError, ims_helper._ims_recipes_get)

    @responses.activate
    def test_ims_recipe_create(self):
        """ Test _ims_recipe_create method when get a valid response from IMS. """

        recipe_name = str(mock.sentinel.name)

        fake_recipe_data = {'name': recipe_name}
        responses.add(responses.POST, '{}/recipes'.format(self.ims_url),
                      json=fake_recipe_data)

        responses.add(
            responses.GET, '{}/version'.format(self.ims_url), json={"version": "1.2.3"})

        ims_helper = ImsHelper(self.ims_url, self.session)

        linux_distribution = str(mock.sentinel.linux_distribution)
        resp = ims_helper._ims_recipe_create(
            recipe_name, linux_distribution)

        exp_req_data = {
            'recipe_type': 'kiwi-ng',
            'linux_distribution': linux_distribution,
            'name': recipe_name,
        }
        self.assertEqual(
            exp_req_data, json.loads(responses.calls[0].request.body))

        self.assertEqual(fake_recipe_data, resp)

    @responses.activate
    def test_ims_recipe_create_with_template_dictionary(self):
        """ Test _ims_recipe_create method when get a valid response from IMS. """

        recipe_name = str(mock.sentinel.name)

        fake_recipe_data = {'name': recipe_name}
        responses.add(responses.POST, '{}/recipes'.format(self.ims_url),
                      json=fake_recipe_data)

        responses.add(
            responses.GET, '{}/version'.format(self.ims_url), json={"version": "1.2.3"})

        ims_helper = ImsHelper(self.ims_url, self.session)

        linux_distribution = str(mock.sentinel.linux_distribution)
        template_dictionary = {'CSM_VERSION': '1.0.0'}
        resp = ims_helper._ims_recipe_create(
            recipe_name, linux_distribution, template_dictionary)

        exp_req_data = {
            'recipe_type': 'kiwi-ng',
            'linux_distribution': linux_distribution,
            'template_dictionary': [{'key': k, 'value': v} for k, v in template_dictionary.items()],
            'name': recipe_name,
        }
        self.assertEqual(
            exp_req_data, json.loads(responses.calls[0].request.body))

        self.assertEqual(fake_recipe_data, resp)

    @responses.activate
    def test_ims_recipe_create_error(self):
        """ Test _ims_recipe_create method when get an invalid response from the server. """

        fake_error_data = {'title': 'Bad Request'}
        responses.add(responses.POST, '{}/recipes'.format(self.ims_url),
                      json=fake_error_data, status=400)
        responses.add(
            responses.GET, '{}/version'.format(self.ims_url), json={"version": "1.2.3"})

        ims_helper = ImsHelper(self.ims_url, self.session)

        recipe_name = str(mock.sentinel.name)
        linux_distribution = str(mock.sentinel.linux_distribution)
        self.assertRaises(
            requests.exceptions.HTTPError, ims_helper._ims_recipe_create,
            recipe_name, linux_distribution)

    @responses.activate
    def test_ims_recipe_delete(self):
        """ Test _ims_recipe_delete method when get a valid response from IMS. """
        recipe_id = str(uuid.uuid4())
        responses.add(
            responses.DELETE, '{}/recipes/{}'.format(self.ims_url, recipe_id))
        responses.add(
            responses.GET, '{}/version'.format(self.ims_url), json={"version": "1.2.3"})

        ims_helper = ImsHelper(self.ims_url, self.session)
        ims_helper._ims_recipe_delete(recipe_id)

    @responses.activate
    def test_ims_recipe_delete_error(self):
        """ Test _ims_recipe_delete method when get an invalid response from IMS. """
        recipe_id = str(uuid.uuid4())
        responses.add(
            responses.DELETE, '{}/recipes/{}'.format(self.ims_url, recipe_id),
            status=404)
        responses.add(
            responses.GET, '{}/version'.format(self.ims_url), json={"version": "1.2.3"})

        ims_helper = ImsHelper(self.ims_url, self.session)
        self.assertRaises(
            requests.exceptions.HTTPError, ims_helper._ims_recipe_delete,
            recipe_id)


class TestDuplicateImages(BaseTestImage):
    def setUp(self):
        super().setUp()
        self.ims_helper = ImsHelper(self.ims_url, self.session)

        self.mock_get_image_manifest = patch.object(
            self.ims_helper,
            'get_image_manifest',
            return_value=self.manifest).start()
        self.mock_md5 = patch.object(
            self.ims_helper,
            '_md5',
            side_effect=[
                self.rootfs_md5,
                self.kernel_md5,
                self.initrd_md5,
                self.debug_md5,
                self.params_md5
            ]
        ).start()

    def test_compare_image_manifest_matches(self):
        """Test that artifacts that match existing image records are detected"""
        result = self.ims_helper.artifacts_match_image_record(
            self.existing_ims_images[0],
            self.existing_ims_images[0]['name'],
            '/path/to/rootfs',
            '/path/to/kernel',
            '/path/to/initrd',
            '/path/to/debug/kernel',
            '/path/to/boot/parameters',
        )
        self.assertTrue(result)

    def test_compare_image_manifest_does_not_match(self):
        """Test that artifacts that don't match are not returned as matches"""
        self.mock_md5.side_effect = ["ba0bab", "deadc0de", "c0ffee", "badcode", "b0bacafe"]
        result = self.ims_helper.artifacts_match_image_record(
            self.existing_ims_images[1],
            self.existing_ims_images[1]['name'],
            '/path/to/rootfs',
            '/path/to/kernel',
            '/path/to/initrd',
            '/path/to/debug/kernel',
            '/path/to/boot/parameters',
        )
        self.assertFalse(result)


class TestRetrievingManifest(BaseTestImage):
    def setUp(self):
        super().setUp()
        self.ims_helper = ImsHelper(self.ims_url, self.session)

        self.throw_error = False

        def mock_download_fileobj(bucket, path, buf):
            if self.throw_error:
                raise botocore.exceptions.ClientError({}, "GET")
            else:
                buf.write(json.dumps(self.manifest).encode())

        self.mock_s3_client = patch.object(
            self.ims_helper.s3_client,
            'download_fileobj',
            mock_download_fileobj).start()

    def test_retrieve_manifest_successful(self):
        """Test retrieving the image manifest successfully"""
        manifest = self.ims_helper.get_image_manifest(self.existing_ims_images[0])
        self.assertEqual(manifest, self.manifest)

    def test_retrieve_manifest_s3_fails(self):
        """Test that getting a manifest retrieves None if there is an S3 error"""
        self.throw_error = True
        manifest = self.ims_helper.get_image_manifest(self.existing_ims_images[0])
        self.assertIsNone(manifest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
