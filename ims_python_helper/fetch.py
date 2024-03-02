#
# MIT License
#
# (C) Copyright 2023 Hewlett Packard Enterprise Development LP
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

import logging
from multiprocessing.connection import wait
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

import jinja2
import oauthlib.oauth2
import requests
import requests_oauthlib
import yaml
from ims_python_helper import ImsHelper
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from requests.packages.urllib3.util.retry import Retry

LOGGER = logging.getLogger(__file__)
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

IMS_URL = os.environ.get("IMS_URL", "https://api-gw-service-nmn.local/apis/ims")
CA_CERT = os.environ.get("CA_CERT", "")

class FetchBase(object):

    def __init__(self):
        try:
            self.IMS_JOB_ID = os.environ["IMS_JOB_ID"]
            LOGGER.info("IMS_JOB_ID=%s", self.IMS_JOB_ID)
        except KeyError as key_error:
            LOGGER.error("Missing environment variable IMS_JOB_ID.", exc_info=key_error)
            sys.exit(1)

        self.oauth_session = FetchBase.create_oauth_session()
        # Remove insecure session once CASMCMS-4521 (Update IMS to talk via HTTPS to ceph rados gateway) is unblocked
        self.insecure_session = FetchBase.create_session()
        self.ims_helper = ImsHelper(
            ims_url=IMS_URL,
            session=self.oauth_session,
            s3_host=os.environ.get('S3_HOST', None),
            s3_secret_key=os.environ.get('S3_SECRET_KEY', None),
            s3_access_key=os.environ.get('S3_ACCESS_KEY', None),
            s3_bucket=os.environ.get('S3_BUCKET', None)
        )

    @staticmethod
    def _get_admin_client_auth():
        """
        This function loads the information necessary to authenticate and obtain an oauth
        credential needed to talk to various services behind the api-gateway.
        :return: tuple of oauth_client_id, oauth_client_secret, oauth_client_endpoint
        """
        default_oauth_client_id = ""
        default_oauth_client_secret = ""
        default_oauth_endpoint = ""

        oauth_config_dir = os.environ.get("OAUTH_CONFIG_DIR", "/etc/admin-client-auth")
        if os.path.isdir(oauth_config_dir):
            oauth_client_id_path = os.path.join(oauth_config_dir, 'client-id')
            if os.path.exists(oauth_client_id_path):
                with open(oauth_client_id_path) as auth_client_id_f:
                    default_oauth_client_id = auth_client_id_f.read().strip()
            oauth_client_secret_path = os.path.join(oauth_config_dir, 'client-secret')
            if os.path.exists(oauth_client_secret_path):
                with open(oauth_client_secret_path) as oauth_client_secret_f:
                    default_oauth_client_secret = oauth_client_secret_f.read().strip()
            oauth_endpoint_path = os.path.join(oauth_config_dir, 'endpoint')
            if os.path.exists(oauth_endpoint_path):
                with open(oauth_endpoint_path) as oauth_endpoint_f:
                    default_oauth_endpoint = oauth_endpoint_f.read().strip()

        oauth_client_id = os.environ.get("OAUTH_CLIENT_ID", default_oauth_client_id)
        oauth_client_secret = os.environ.get("OAUTH_CLIENT_SECRET", default_oauth_client_secret)
        oauth_client_endpoint = os.environ.get("OAUTH_CLIENT_ENDPOINT", default_oauth_endpoint)

        if not all([oauth_client_id, oauth_client_secret, oauth_client_endpoint]):
            LOGGER.error("Invalid oauth configuration. Determine the specific information that "
                         "is missing or invalid and then re-run the request with valid information.")
            sys.exit(1)

        return oauth_client_id, oauth_client_secret, oauth_client_endpoint

    @staticmethod
    def log_request(resp, *args, **kwargs):
        """
        This function logs the request.

        Args:
            resp : The response
        """
        if LOGGER.isEnabledFor(logging.DEBUG):
            LOGGER.debug('\n%s\n%s\n%s\n\n%s',
                         '-----------START REQUEST-----------',
                         resp.request.method + ' ' + resp.request.url,
                         '\n'.join('{}: {}'.format(k, v) for k, v in list(resp.request.headers.items())),
                         resp.request.body)

    @staticmethod
    def log_response(resp, *args, **kwargs):
        """
        This function logs the response.

        Args:
            resp : The response
        """
        if LOGGER.isEnabledFor(logging.DEBUG):
            LOGGER.debug('\n%s\n%s\n%s\n\n%s',
                         '-----------START RESPONSE----------',
                         resp.status_code,
                         '\n'.join('{}: {}'.format(k, v) for k, v in list(resp.headers.items())),
                         resp.content)

    @staticmethod
    def create_oauth_session():
        """
        Create and return an oauth2 python requests session object
        """

        oauth_client_id, oauth_client_secret, oauth_client_endpoint = FetchBase._get_admin_client_auth()

        oauth_client = oauthlib.oauth2.BackendApplicationClient(
            client_id=oauth_client_id)

        session = requests_oauthlib.OAuth2Session(
            client=oauth_client,
            auto_refresh_url=oauth_client_endpoint,
            auto_refresh_kwargs={
                'client_id': oauth_client_id,
                'client_secret': oauth_client_secret,
            },
            token_updater=lambda t: None)

        # Creates a URL retry object and HTTP adapter to use with our session;
        # this allows us to interact with services in a more resilient manner
        retries = Retry(total=10, backoff_factor=2, status_forcelist=[502, 503, 504])
        session.mount("http://", HTTPAdapter(max_retries=retries))
        session.mount("https://", HTTPAdapter(max_retries=retries))

        session.verify = CA_CERT
        session.hooks['response'].append(FetchBase.log_request)
        session.hooks['response'].append(FetchBase.log_response)

        retries = 0
        while True:
            try:
                session.fetch_token(
                    token_url=oauth_client_endpoint, client_id=oauth_client_id,
                    client_secret=oauth_client_secret, timeout=500)
                return session

            except RequestException as exc:
                retries = retries + 1
                LOGGER.info("Received exception:", exc_info=exc)
                LOGGER.info("Retrying (%s) in 7 seconds", retries)
                time.sleep(7)

    @staticmethod
    def create_session():
        """
        Create and return a python requests session object
        """
        session = requests.Session()

        # Creates a URL retry object and HTTP adapter to use with our session;
        # this allows us to interact with services in a more resilient manner
        retries = Retry(total=10, backoff_factor=2, status_forcelist=[502, 503, 504])
        session.mount("http://", HTTPAdapter(max_retries=retries))
        session.mount("https://", HTTPAdapter(max_retries=retries))

        # CASMCMS-6551 Disable session SSL Verification. In CASMCMS-6552 we need to
        # implement SSL verification once the RADOS GW implements a signed certificate.
        session.verify = False
        session.hooks['response'].append(FetchBase.log_request)
        session.hooks['response'].append(FetchBase.log_response)

        return session

    def download_file(self, download_url, filename):
        """
        Download file using python requests session.
        Args:
            download_url : URL of the file to be downloaded
            filename : The filename where the file is to be stored
        """

        # insure the parent dirs exist
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        # allow multiple failures while tring to download file
        LOGGER.info("Saving file as '%s'", filename)
        numAttempts=0
        sleepTime=10
        maxAttempts=20
        while numAttempts<maxAttempts:
            try:
                response = self.insecure_session.get(download_url, stream=True, allow_redirects=True)
                response.raise_for_status()
                if response.ok:
                    with open(filename, 'wb') as fout:
                        for chunk in response.iter_content(chunk_size=1024*1024):
                            if chunk:
                                fout.write(chunk)
                LOGGER.info("File download complete.")
                break
            except RequestException as err:
                # catch the exception so we can try again
                LOGGER.warning(f"Error {err} downloading {download_url}")

            numAttempts += 1
            LOGGER.warning(f"Sleeping {sleepTime} sec and trying again...")
            time.sleep(sleepTime)

        # if we have hit number of attempts without succeeding bail
        if numAttempts >= maxAttempts:
            LOGGER.error(f"Failed to download {download_url} after {numAttempts} tries.")
            self.ims_helper.image_set_job_status(self.IMS_JOB_ID, "error")
            sys.exit(1)

        # verify the md5 sum of the downloaded file
        download_md5sum = os.environ.get("DOWNLOAD_MD5SUM", "")
        if download_md5sum:
            LOGGER.info("Verifying md5sum of the downloaded file.")
            if download_md5sum != ImsHelper._md5(filename):
                LOGGER.error("The calculated md5sum does not match the expected value.")
                self.ims_helper.image_set_job_status(self.IMS_JOB_ID, "error")
                sys.exit(1)
            LOGGER.info("Successfully verified the md5sum of the downloaded file.")

    def run(self):
        pass


class FetchImage(FetchBase):

    def __init__(self, path, url):
        super(FetchImage, self).__init__()

        self.path = path
        self.url = url
        self.image_sqshfs = os.path.join(self.path, "image.sqsh")

    def delete_signal_files(self):
        """ The signal files should not exist. If they do, remove them. """
        for signal_file in ("ready", "complete", "exiting"):
            try:
                fn = os.path.join(self.path, signal_file)
                if os.path.isfile(fn):
                    os.remove(fn)
            except OSError as exc:
                LOGGER.error("Error while trying to remove signal file %s.", signal_file, exc_info=exc)
                self.ims_helper.image_set_job_status(self.IMS_JOB_ID, "error")
                sys.exit(1)

    def unsquash_image(self):
        # Expand the image root from its archive (squashfs) and remove the archive
        try:
            subprocess.check_output(["unsquashfs", "-f", "-d",
                                     "{}".format(os.path.join(self.path, "image-root")),
                                     self.image_sqshfs])
        except subprocess.CalledProcessError as exc:
            LOGGER.error("Error unsquashing image root.", exc_info=exc)
            self.ims_helper.image_set_job_status(self.IMS_JOB_ID, "error")
            sys.exit(1)

    def run(self, unpack: bool = True):
        try:
            LOGGER.info("Setting job status to 'fetching_image'.")
            self.ims_helper.image_set_job_status(self.IMS_JOB_ID, "fetching_image")
            if not os.path.exists(self.path):
                os.makedirs(self.path)
            LOGGER.info("Fetching image %s", self.url)
            self.download_file(self.url, self.image_sqshfs)
            LOGGER.info("Deleting signal files")
            self.delete_signal_files()
            if unpack:
                LOGGER.info("Uncompressing image into %s", self.path)
                self.unsquash_image()
            else:
                LOGGER.info("Skipping image unsquash")
        except Exception as exc:
            LOGGER.error("Error unhandled exception while fetching image root.", exc_info=exc)
            self.ims_helper.image_set_job_status(self.IMS_JOB_ID, "error")
            sys.exit(1)
        finally:
            if os.path.isfile(self.image_sqshfs) and unpack:
                LOGGER.info("Deleting compressed image %s", self.image_sqshfs)
                os.remove(self.image_sqshfs)
            LOGGER.info("Done")


class FetchRecipe(FetchBase):

    def __init__(self, path, url):
        super(FetchRecipe, self).__init__()

        self.path = path
        self.url = url
        self.recipe_tgz = os.path.join(self.path, "recipe.tgz")

    def untar_recipe(self):
        # Expand the image root from its archive (squashfs) and remove the archive
        try:
            tar = tarfile.open(self.recipe_tgz)
            tar.extractall(path=self.path)
        except subprocess.CalledProcessError as exc:
            LOGGER.error("Error unsquashing image root.", exc_info=exc)
            self.ims_helper.image_set_job_status(self.IMS_JOB_ID, "error")
            sys.exit(1)

    def template_recipe(self):
        """
        Optionally apply jinja2 templating to one or more files within the uncompressed recipe.
        """
        ims_recipe_template_yaml = os.path.join(self.path, '.ims_recipe_template.yaml')

        # Compile a list of key/value pairs from the environment
        template_values = {}
        try:
            with open("/etc/cray/template_dictionary") as inf:
                template_values = yaml.safe_load(inf)
        except FileNotFoundError:
            LOGGER.warning("/etc/cray/template_dictionary was not found. Will continue without templating the recipe.")
            return

        if not os.path.isfile(ims_recipe_template_yaml) and not template_values:
            LOGGER.info("The recipe does not need to be templated.")
            return

        if os.path.isfile(ims_recipe_template_yaml) and not template_values:
            LOGGER.error("The recipe expects to be templated, but the IMS recipe record "
                         "does not specify any values in the template_dictionary.")
            sys.exit(1)

        if template_values and not os.path.isfile(ims_recipe_template_yaml):
            LOGGER.warning("The IMS recipe record has values in the template_dictionary, but the recipe does "
                           "not expect to be templated. Will continue without templating the recipe.")
            return

        with open(ims_recipe_template_yaml) as inf_yaml:
            try:
                loader = jinja2.FileSystemLoader(self.path)
                env = jinja2.Environment(loader=loader)

                ims_recipe_template = yaml.safe_load(inf_yaml)
                for template_file in ims_recipe_template['template_files']:

                    # Make sure that we're looking at a file within the recipe directory
                    absolute_file_name = os.path.abspath(
                        os.path.expanduser(os.path.join(self.path, template_file))
                    )

                    if not absolute_file_name.startswith(self.path):
                        LOGGER.error(
                            f"The recipe is trying to template a file '{absolute_file_name}' "
                            "outside of the IMS recipe directory.")
                        sys.exit(1)

                    # Check that the file exists
                    if not os.path.isfile(absolute_file_name):
                        LOGGER.error(
                            f"The recipe is trying to template a file '{absolute_file_name}' that does not exist.")
                        sys.exit(1)

                    # Apply the template modifications
                    template = env.get_template(absolute_file_name[len(self.path) + 1:])
                    with tempfile.NamedTemporaryFile("w", delete=False) as outf:
                        outf.write(template.render(**template_values))

                    # remove the original file replace with the templated version - preserve the permissions
                    shutil.copymode(absolute_file_name, outf.name)
                    os.remove(absolute_file_name)
                    shutil.move(outf.name, absolute_file_name)
            except KeyError as keyerror:
                LOGGER.error("Error: Missing key while reading .ims_recipe_template.yaml file.", exc_info=keyerror)

            except yaml.YAMLError as exc:
                LOGGER.error("Error reading .ims_recipe_template.yaml in the recipe.", exc_info=exc)

    def run(self):
        try:
            LOGGER.info("Setting job status to 'fetching_recipe'.")
            self.ims_helper.image_set_job_status(self.IMS_JOB_ID, "fetching_recipe")
            LOGGER.info("Fetching recipe %s", self.url)
            self.download_file(self.url, self.recipe_tgz)
            LOGGER.info("Uncompressing recipe into %s", self.path)
            self.untar_recipe()
            LOGGER.info("Templating recipe")
            self.template_recipe()
        except Exception as exc:
            LOGGER.error("Error unhandled exception while fetching recipe.", exc_info=exc)
            self.ims_helper.image_set_job_status(self.IMS_JOB_ID, "error")
            sys.exit(1)
        finally:
            if os.path.isfile(self.recipe_tgz):
                LOGGER.info("Deleting compressed recipe %s", self.recipe_tgz)
                os.remove(self.recipe_tgz)
            LOGGER.info("Done")
