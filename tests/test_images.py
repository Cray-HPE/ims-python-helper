#
# MIT License
#
# (C) Copyright 2018-2019, 2021-2022 Hewlett Packard Enterprise Development LP
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

import mock
import requests
import responses

# Add ims_python_helper to path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from ims_python_helper import ImsHelper
from testtools import TestCase

UPLOAD_TIMEOUT = 500


class TestImage(TestCase):

    def setUp(self):
        super(TestImage, self).setUp()

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
