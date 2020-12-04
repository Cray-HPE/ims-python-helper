# setup.py for ims-python-helper
# Copyright 2018, 2019, Cray Inc. All Rights Reserved.
import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

with open('.rpm_version', 'r') as fh:
    version = fh.read().strip()

setuptools.setup(
    name="ims-python-helper",
    version=version,
    install_requires=[
      'boto3',
      'oauthlib',
      'requests',
      'requests-oauthlib',
    ],
    author="Cray Inc.",
    author_email="sps@cray.com",
    description="Utility for interacting with the Cray Image Management Service",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://stash.us.cray.com/projects/SCMS/repos/ims-python-helper/browse",
    packages=setuptools.find_packages(),
    keywords="Cray IMS",
    classifiers=(
      "Programming Language :: Python :: 3.6",
    ),
)
