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
import os
import sys
import time
import oauthlib.oauth2
import requests
import requests_oauthlib
from oauthlib.oauth2.rfc6749.errors import OAuth2Error  # noqa: E402

def create_oauth_session(oauth_client_id, oauth_client_secret, ssl_cert, 
                         token_url, timeout, logger=None):  # noqa: E501
    """
    Create a session for this client when connecting with Shasta services
    """
    if not all([oauth_client_id, oauth_client_secret, token_url]):
        raise ValueError(
            'Invalid oauth configuration. Please check that the oauth_client_id, '  # noqa: E501
            'oauth_client_secret and token_url parameters are being specified and '  # noqa: E501
            'are correct. Determine the specific information that '
            'is missing or invalid and then re-run the request with valid'
        )

    oauth_client = oauthlib.oauth2.BackendApplicationClient(
        client_id=oauth_client_id)

    session = requests_oauthlib.OAuth2Session(
        client=oauth_client, auto_refresh_url=token_url,
        auto_refresh_kwargs={
            'client_id': oauth_client_id,
            'client_secret': oauth_client_secret,
        },
        token_updater=lambda t: None)

    session.verify = ssl_cert
    session.timeout = timeout

    hookLogger = RequestLogger(logger)
    session.hooks['response'].append(hookLogger.log_request)
    session.hooks['response'].append(hookLogger.log_response)

    token = None
    attempt_timeout = 0
    sleep_ceiling = 64
    while True:
        try:
            token = session.fetch_token(
                token_url=token_url, client_id=oauth_client_id,
                client_secret=oauth_client_secret, timeout=500)
        except OAuth2Error as oa2e:
            # In practice, this can fail for a very large number of reasons
            # from the underlying oauth lib. Rather than special casing each
            # and every one, we simply verify that a token was successfully
            # generated and then log the raising exception. We otherwise do not
            # want to get into the business of special casing the kinds of
            # failures that the oauthlib2 library can raise.
            if logger != None:
                logger.warning(oa2e)
        if not token:
            time.sleep(attempt_timeout)
            if attempt_timeout != sleep_ceiling:
                attempt_timeout += 1
            if logger != None:
                logger.info(
                    "Unable to obtain token from auth service, retrying in %s seconds", attempt_timeout
            )
        else:
            break
    return session

def get_admin_client_auth(logger=None):
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
        if logger != None:
            logger.error("Invalid oauth configuration. Determine the specific information that "
                     "is missing or invalid and then re-run the request with valid information.")
        sys.exit(1)

    return oauth_client_id, oauth_client_secret, oauth_client_endpoint

class RequestLogger(object):
    """
    Helper class to wrap an external logger with funtions that can be
    used with session hooks for request logging.
    """
    
    def __init__(self, logger: logging.Logger):
        self.LOGGER = logger
    
    def log_request(self, resp, *args, **kwargs):
        """
        This function logs the request.

        Args:
            resp : The response
        """
        if self.LOGGER != None and self.LOGGER.isEnabledFor(logging.DEBUG):
            self.LOGGER.debug('\n%s\n%s\n%s\n\n%s',
                        '-----------START REQUEST-----------',
                        resp.request.method + ' ' + resp.request.url,
                        '\n'.join('{}: {}'.format(k, v) for k, v in list(resp.request.headers.items())),
                        resp.request.body)


    def log_response(self, resp, *args, **kwargs):
        """
        This function logs the response.

        Args:
            resp : The response
        """
        if self.LOGGER !=None and self.LOGGER.isEnabledFor(logging.DEBUG):
            self.LOGGER.debug('\n%s\n%s\n%s\n\n%s',
                        '-----------START RESPONSE----------',
                        resp.status_code,
                        '\n'.join('{}: {}'.format(k, v) for k, v in list(resp.headers.items())),
                        resp.content)