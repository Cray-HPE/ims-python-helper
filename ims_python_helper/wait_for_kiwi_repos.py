#
# MIT License
#
# (C) Copyright 2023-2025 Hewlett Packard Enterprise Development LP
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
import os
import sys
import time
import xml.etree.ElementTree as ET
import requests

from ims_python_helper import ImsHelper
from ims_python_helper.session import create_oauth_session, get_admin_client_auth

IMS_JOB_STATUS = "waiting_for_repos"

def wait_for_kiwi_repos(ims_job_id: str, ims_url: str, ca_cert:str,
                        recipe_root: str, timeout: int,
                        logger: logging.Logger) -> int:
    """Verify all the repos in the recipe are present and available

    Args:
        ims_job_id (str): IMS job id
        ims_url (str): URL to access the IMS service
        ca_cert (str): Cert for authenticated access
        recipe_root (str): Directory root of the recipe
        timeout (int): Wait in seconds before failing repo access
        logger (logging.Logger): Logger object to report status

    Returns:
        int: 0 on success
    """
    # if the user provides a logger, use it
    myLogger = logging.getLogger()
    if logger != None:
        myLogger = logger

    # create an oauth session
    oauth_client_id, oauth_client_secret, oauth_client_endpoint = get_admin_client_auth(myLogger)
    session = create_oauth_session(oauth_client_id, oauth_client_secret, ca_cert, oauth_client_endpoint, myLogger)

    # set ims job status to 'waiting for repos'
    _set_ims_job_status(ims_job_id, ims_url, session, myLogger)

    # check repo availability
    ret_val = _wait_for_kiwi_ng_repos(recipe_root, session, myLogger, timeout)

    if ret_val != 0:
        _set_ims_job_status(ims_job_id, ims_url, session, myLogger, job_status="error")
    return ret_val


def _set_ims_job_status(ims_job_id: str, ims_url: str, session, logger: logging.Logger, job_status=IMS_JOB_STATUS) -> None:
    try:
        if ims_job_id:
            logger.info("Setting job status to '%s'", job_status)
            result = ImsHelper(
                ims_url=ims_url,
                session=session,
                s3_host=os.environ.get('S3_HOST', None),
                s3_secret_key=os.environ.get('S3_SECRET_KEY', None),
                s3_access_key=os.environ.get('S3_ACCESS_KEY', None),
                s3_bucket=os.environ.get('S3_BUCKET', None)
            )._ims_job_patch_job_status(ims_job_id, job_status)
            logger.info("Result of setting job status: %s", result)
    except requests.exceptions.HTTPError as exc:
        logger.warning("Error setting job status %s" % exc)


def _wait_for_kiwi_ng_repos(recipe_root, session, logger: logging.Logger, timeout: int)-> int:
    """ Load kiwi-ng recipe and introspect to find list of repos """
    # Load config.xml file
    config_xml_file = os.path.join(recipe_root, 'config.xml')
    if not os.path.isfile(config_xml_file):
        sys.exit("%s does not exist." % config_xml_file)

    retVal = 0
    try:
        # introspect the recipe and look for any defined repos
        root = ET.parse(config_xml_file).getroot()
        repos = [type_tag.get('path') for type_tag in root.findall('repository/source')
                 if type_tag is not None and type_tag.get('path') and
                 type_tag.get('path').lower().startswith(('http://', 'https://'))]

        retVal = _wait_for_repos(repos, session, logger, timeout)
    except ET.ParseError as xml_err:
        logger.error('Failed to parse config.xml to determine repo URLs. %s', xml_err)
        return 1
    return retVal


def _wait_for_repos(repos: list, session, logger: logging.Logger, timeout: int)-> int:
    """ Wait for all the defined repos to become available. """
    if repos:
        logger.info("Recipe contains the following repos: %s" % repos)
        stTime = time.perf_counter()
        # Wait for all the defined repos to be available via HTTP/HTTPS
        while not all([is_repo_available(session, repo, logger, 10) for repo in repos]):
            if time.perf_counter() - stTime > timeout:
                logger.info("Repos failed to be ready before timeout")
                return 1
            logger.info("Sleeping for 10 seconds")
            time.sleep(10)
    else:
        logger.info("No matching http(s) repos found. Exiting.")
        return 1
    return 0


def is_repo_available(session, repo_url, logger, timeout):
    """ Try to determine if the repo is available by getting the repodata/repomd.xml file"""
    try:
        repo_md_xml = "/".join(arg.strip("/") for arg in [repo_url, 'repodata', 'repomd.xml'])
        logger.info("Attempting to get {}".format(repo_md_xml))
        response = session.head(repo_md_xml, timeout=timeout)
        response.raise_for_status()
        logger.info("{} response getting {}".format(response.status_code, repo_md_xml))
        return True
    except requests.exceptions.RequestException as err:
        logger.warning(err)
        if hasattr(err, "response") and hasattr(err.response, "text"):
            logger.debug(err.response.text)
    return False

