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
#
"""
Cray Image Management Service helper functions
"""

# pylint: disable=ungrouped-imports

from __future__ import print_function

import argparse
import json
import logging
import os
import re

import sys
import time

# CASMCMS-4926: Adjust import path while using this library to find
# provided, version pinned libraries outside of the context of the Base OS
# installed locations. Insert at position 0 so provided source is always
# preferred; this allows fallback to the nominal system locations once
# the base OS provided RPM content reaches parity.
sys.path.insert(0, '/opt/cray/crayctl/lib')

# pylint: disable=wrong-import-position
import oauthlib.oauth2  # noqa: E402
import requests  # noqa: E402
import requests_oauthlib  # noqa: E402

from requests.packages.urllib3.exceptions import InsecureRequestWarning  # noqa: E402
from oauthlib.oauth2.rfc6749.errors import OAuth2Error  # noqa: E402
from ims_python_helper import ImsHelper, DEFAULT_IMS_API_URL  # noqa: E402
# pylint: enable=wrong-import-position

UUID_PATTERN = \
    re.compile(r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}")  # noqa: E501

LOGGER = logging.getLogger('ims_python_helper.cli')
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# OAuth Defaults
DEFAULT_OAUTH_ENDPOINT = None
DEFAULT_OAUTH_CLIENT_ID = None
DEFAULT_OAUTH_CLIENT_SECRET = None
DEFAULT_OAUTH_CONFIG_DIR = "/etc/admin-client-auth"
OAUTH_CONFIG_DIR = os.environ.get(
    "OAUTH_CONFIG_DIR",
    DEFAULT_OAUTH_CONFIG_DIR if os.path.isdir(DEFAULT_OAUTH_CONFIG_DIR) else ""
)

if OAUTH_CONFIG_DIR:
    oauth_endpoint_path = os.path.join(OAUTH_CONFIG_DIR, 'endpoint')
    with open(oauth_endpoint_path) as oauth_endpoint_f:
        DEFAULT_OAUTH_ENDPOINT = oauth_endpoint_f.read().strip()
    oauth_client_id_path = os.path.join(OAUTH_CONFIG_DIR, 'client-id')
    with open(oauth_client_id_path) as auth_client_id_f:
        DEFAULT_OAUTH_CLIENT_ID = auth_client_id_f.read().strip()
    oauth_client_secret_path = os.path.join(OAUTH_CONFIG_DIR, 'client-secret')
    with open(oauth_client_secret_path) as oauth_client_secret_f:
        DEFAULT_OAUTH_CLIENT_SECRET = oauth_client_secret_f.read().strip()


def my_uuid4_regex_type(string_input, pat=UUID_PATTERN):
    """ Validate input is a UUID value """
    if not pat.match(string_input):
        raise argparse.ArgumentTypeError
    return string_input


def add_image_upload_artifacts_parser(subparsers, parent_parser):
    """ Add image create sub-parser and arguments """
    parser = subparsers.add_parser(
        'upload_artifacts', parents=[parent_parser],
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'image_name', type=str, help='Descriptive name for the image'
    )

    parser.add_argument(
        'ims_job_id', type=my_uuid4_regex_type,
        default=os.environ.get('IMS_JOB_ID'), nargs='?', help='IMS Job ID'
    )

    parser.add_argument(
        '-r', '--rootfs', type=str,
        action='append',
        help='filename of root file system archive to upload and register'
    )

    parser.add_argument(
        '-k', '--kernel', type=str,
        action='append',
        help='filename of kernel to upload and register'
    )

    parser.add_argument(
        '-i', '--initrd', type=str,
        action='append',
        help='filename of initrd to upload and register'
    )

    parser.add_argument(
        '-d', '--debug', type=str,
        action='append',
        help='filename of debug artifact to upload and register'
    )

    parser.add_argument(
        '-p', '--boot-parameters', type=str,
        action='append',
        help='filename of boot parameters file to upload and register'
    )


def add_image_set_job_status(subparsers, parent_parser):
    """ Add image create sub-parser and arguments """
    parser = subparsers.add_parser(
        'set_job_status', parents=[parent_parser],
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'ims_job_id', type=my_uuid4_regex_type,
        default=os.environ.get('IMS_JOB_ID'), help='IMS Job ID'
    )

    parser.add_argument(
        'job_status', type=str, help='Job Status to set'
    )


def add_image_sub_parsers(subparsers, parent_parser):
    """ Add image sub-parsers """
    add_image_upload_artifacts_parser(subparsers, parent_parser)
    add_image_set_job_status(subparsers, parent_parser)


def add_image_parser(subparsers, parent_parser):
    """ Add image sub-parser and arguments """
    parser = subparsers.add_parser(
        'image', parents=[parent_parser],
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    image_subparsers = parser.add_subparsers(
        title='subcommands', dest='command'
    )

    add_image_sub_parsers(image_subparsers, parent_parser)


def add_sub_parsers(subparsers, parent_parser):
    """ Adds all image command subparsers. """
    add_image_parser(subparsers, parent_parser)


def create_parent_parser(program_name):
    """
    Sets up the argparse parent parser and establishes the common options.
    """
    parent_parser = argparse.ArgumentParser(prog=program_name, add_help=False)
    parent_parser.add_argument(
        '-l', '--log-level', type=str, default="WARNING",
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Set the logging level'
    )
    parent_parser.add_argument(
        '-t', '--timeout', type=int, default=720, help="timeout in seconds"
    )
    parent_parser.add_argument(
        '--ims-url', type=str,
        default=DEFAULT_IMS_API_URL,
        help='Specify the base URL to IMS; e.g. %s' % DEFAULT_IMS_API_URL
    )

    parent_parser.add_argument(
        '--cert', type=str, default=os.environ.get("CA_CERT"),
        help="Path to System CA Certificate"
    )
    parent_parser.add_argument(
        '--oauth-client-id', type=str, default=DEFAULT_OAUTH_CLIENT_ID,
        help="OAuth Client ID"
    )
    parent_parser.add_argument(
        '--oauth-client-secret', type=str, default=DEFAULT_OAUTH_CLIENT_SECRET,
        help='OAuth Client Secret'
    )
    parent_parser.add_argument(
        '--token-url', type=str, default=DEFAULT_OAUTH_ENDPOINT,
        help='Specify the base URL to the OAuth token endpoint; e.g. '
             'https://api-gw-service-nmn.local/keycloak/realms/shasta/protocol/openid-connect/token'  # noqa: E501
    )

    parent_parser.add_argument(
        '--s3-endpoint', type=str,
        default=os.environ.get('S3_ENDPOINT', os.environ.get('S3_HOST', None)),
        help='Host of S3 instance, e.g. https://s3.shasta.local:8080. Uses S3_ENDPOINT environment variable as a default.'  # noqa: E501
    )
    parent_parser.add_argument(
        '--s3-access-key', type=str,
        default=os.environ.get('S3_ACCESS_KEY', None),
        help='S3 Access Key. Uses S3_ACCESS_KEY environment variable as a default.'  # noqa: E501
    )
    parent_parser.add_argument(
        '--s3-secret-key', type=str,
        default=os.environ.get('S3_SECRET_KEY', None),
        help='S3 Secret Access Key. Uses S3_SECRET_KEY environment variables as a default.'  # noqa: E501
    )
    parent_parser.add_argument(
        '--s3-ssl-verify', type=str,
        default=os.environ.get('S3_SSL_VERIFY', "False"),
        help='Whether or not to verify S3 SSL certificates.'  # noqa: E501
    )
    parent_parser.add_argument(
        '--s3-bucket', type=str,
        default=os.environ.get('S3_BUCKET', None),
        help='S3 Bucket to store artifacts/recipes. Uses S3_BUCKET environment variable as a default.'  # noqa: E501
    )

    return parent_parser


def create_parser(program_name):
    """ Creates the parent parser and adds the subparsers """
    epilog = '''
    details:
        Detailed usage for subcommands can be displayed by providing
        -h or --help anywhere after the subcommand. For example,
        'image list -h' will display detailed usage information for
        image list.
    '''
    parent_parser = create_parent_parser(program_name)

    parser = argparse.ArgumentParser(
        parents=[parent_parser], epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Passing dest='command' to add_subparsers will include the
    # subcommand name itself 'create', 'list', etc in the argument
    # map. This is used by the dispatch code to execute the appropriate
    # command once the args have been parsed.
    subparsers = parser.add_subparsers(title='subcommands', dest='resource')

    add_sub_parsers(subparsers, parent_parser)
    return parser


def log_request(resp, *_args, **_kwargs):  # pylint: disable=unused-argument
    """
    This function logs the request.

    Args:
        resp : The response
    """
    if LOGGER.isEnabledFor(logging.DEBUG):
        LOGGER.debug('\n%s\n%s\n%s\n\n%s',
                     '-----------START REQUEST-----------',
                     resp.request.method + ' ' + resp.request.url,
                     '\n'.join('{}: {}'.format(k, v) for k, v in resp.request.headers.items()),  # noqa: E501
                     resp.request.body)


def log_response(resp, *_args, **_kwargs):  # pylint: disable=unused-argument
    """
    This function logs the response.

    Args:
        resp : The response
    """
    if LOGGER.isEnabledFor(logging.DEBUG):
        LOGGER.debug('\n%s\n%s\n%s\n\n%s',
                     '-----------START RESPONSE----------',
                     resp.status_code,
                     '\n'.join('{}: {}'.format(k, v) for k, v in resp.headers.items()),  # noqa: E501
                     resp.content)


def create_session(oauth_client_id, oauth_client_secret, ssl_cert, token_url, timeout):  # noqa: E501
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

    session.hooks['response'].append(log_request)
    session.hooks['response'].append(log_response)

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
            LOGGER.warning(oa2e)
        if not token:
            time.sleep(attempt_timeout)
            if attempt_timeout != sleep_ceiling:
                attempt_timeout += 1
            LOGGER.info(
                "Unable to obtain token from auth service, retrying in %s seconds", attempt_timeout
            )
        else:
            break
    return session


def main(program_name, args):
    """ Main function """

    parser = create_parser(program_name)
    args = parser.parse_args(args)
    logging.basicConfig(level=args.log_level)

    ims_helper_kwargs = {
        'ims_url': args.ims_url,
        's3_endpoint': args.s3_endpoint,
        's3_secret_key': args.s3_secret_key,
        's3_access_key': args.s3_access_key,
        's3_ssl_verify': args.s3_ssl_verify,
        's3_bucket': args.s3_bucket,
        'session': create_session(
            args.oauth_client_id, args.oauth_client_secret, args.cert,
            args.token_url, args.timeout
        ),
    }

    if not args.cert:
        LOGGER.warning(
            "Warning: Unverified HTTPS request is being made. Use --cert "
            "to add certificate verification."
        )

    argsmap = dict(vars(args))
    del argsmap['s3_endpoint']
    del argsmap['s3_secret_key']
    del argsmap['s3_access_key']
    del argsmap['s3_ssl_verify']
    del argsmap['s3_bucket']
    del argsmap['cert']
    del argsmap['command']
    del argsmap['ims_url']
    del argsmap['log_level']
    del argsmap['oauth_client_id']
    del argsmap['oauth_client_secret']
    del argsmap['resource']
    del argsmap['timeout']
    del argsmap['token_url']

    # Dispatch the command using getattr. Print the json response
    try:
        ims_helper = ImsHelper(**ims_helper_kwargs)
        print(json.dumps(
            getattr(ims_helper, "%s_%s" % (args.resource, args.command))(**argsmap),  # noqa: E501
            indent=4,
            sort_keys=True
        ))
        return 0

    except Exception as e:  # pylint: disable=bare-except, broad-except
        print(json.dumps(
            {'result': 'failure', 'error': str(e)},
            indent=4, sort_keys=True
        ))
        return 1


sys.exit(main("ims-python-helper", sys.argv[1:]))
