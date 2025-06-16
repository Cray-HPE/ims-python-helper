# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Dependencies
- CASMCMS-8022:  update python modules

### Fixed
- CASMCMS-9455: Building image from recipe Job stuck at waiting_for_repos status
- CASMCMS-9364: Confirm exposed SSH private key impact in ims-python-helper

## [3.1.2] - 2024-09-19

### Changed
- CASMCMS-9142: Install Python modules with `--user` to avoid build failures, and build inside Docker container.

## [3.1.0] - 2024-06-10
### Dependencies
Bumped dependency patch versions:
| Package             | From     | To       |
|---------------------|----------|----------|
| `boto3`             | 1.17.53  | 1.34.114 |
| `botocore`          | 1.20.53  | 1.34.114 |
| `chardet`           | 4.0.0    | 5.2.0    |
| `idna`              | 3.1      | 3.7      |
| `jmespath`          | 0.10.0   | 1.0.1    |
| `oauthlib`          | 3.1.1    | 3.2.2    |
| `requests`          | 2.26.0   | 2.31.0   |
| `s3transfer`        | 0.3.7    | 0.10.1   |
| `six`               | 1.15.0   | 1.16.0   |
| `urllib3`           | 1.26.16  | 1.26.18  |

## [3.0.0] - 2024-03-02
### Added
- CASMCMS-8821 - add argument to disable unsquashing downloaded image file.

## [2.15.0] - 2023-09-26
### Added
- CASMCMS-8739 - move common functions here from ims-utils.
### Changed
- Disabled concurrent Jenkins builds on same branch/commit
- Added build timeout to avoid hung builds

### Dependencies
Bumped dependency patch versions:
| Package                  | From     | To       |
|--------------------------|----------|----------|
| `boto3`                  | 1.17.46  | 1.17.53  |
| `botocore`               | 1.20.46  | 1.20.53  |
| `oauthlib`               | 3.1.0    | 3.1.1    |
| `python-dateutil`        | 2.8.1    | 2.8.2    |
| `requests-oauthlib`      | 1.3.0    | 1.3.1    |
| `s3transfer`             | 0.3.6    | 0.3.7    |
| `urllib3`                | 1.26.2   | 1.26.16  |

## [2.14.0] - 2023-06-01
### Changed
CASM-4232: Enhanced logging for [`__init__.py`](ims-python-helper/__init__.py) for use with IUF.
 
## [2.13.0] - 2023-05-02
### Removed
- Removed defunct files leftover from previous versioning system

### Added
- CASMCMS-8459 - add support for arm64 images.
- CASMCMS-8595 - rename platform to arch

## [2.12.0] - 2023-04-18
### Changed
- Changed the behavior of `ImsHelper.recipe_upload()` to only skip uploading a
  recipe if the artifact MD5 sums match, not just if the IMS image names match.
- Change `ImsHelper.image_upload_artifacts()` to check equality of images
  based on artifact checksums in addition to image names.

## [2.11.1] - 2023-02-06
### Fixed
- Fix bug where an `"ims_image_record"` key was not being returned in
  the dict returned by `ImsHelper.image_upload_artifacts()`.

## [2.11.0] - 2023-01-17
### Changed
- Change `ImsHelper.image_upload_artifacts()` to add an option to skip
  uploading an image for which there is already an image with a matching
  name in IMS which has associated artifacts.

## [2.10.2] - 2022-12-20
### Added
- Add Artifactory authentication to Jenkinsfile

## [2.10.1] - 2022-12-02
### Added
- Add a note in the README about authenticating to CSM's artifactory.

## [2.10.0] - 2022-08-01
### Changed
- CASMCMS-7970 - update dev.cray.com server addresses.

## [2.9.0] - 2022-06-27

### Added
- Add support for registering template variables when creating an IMS recipe
