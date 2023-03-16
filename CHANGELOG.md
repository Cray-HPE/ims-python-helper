# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.12.0] - 2023-03-27
### Changed
- Changed the behavior of `ImsHelper.recipe_upload()` to only skip uploading a
  recipe if the artifact MD5 sums match, not just of the IMS image names match.


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

## [Unreleased]

## [2.10.1] - 2022-12-02
### Added
- Add a note in the README about authenticating to CSM's artifactory.

## [2.10.0] - 2022-08-01
### Changed
- CASMCMS-7970 - update dev.cray.com server addresses.

## [2.9.0] - 2022-06-27

### Added
- Add support for registering template variables when creating an IMS recipe
