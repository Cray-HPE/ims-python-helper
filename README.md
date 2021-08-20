# IMS Python Helper

## Getting Started

### Installation

Install the package via pip with the Cray internal pip index url:

```bash
pip install ims-python-helper --trusted-host dst.us.cray.com --index-url http://dst.us.cray.com/piprepo/simple
```

### Assumptions

When calling the ims-python-helper as a python module, the ims-python-helper
requires the `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_ENDPOINT`, `OAUTH_CLIENT_SECRET` and
root SMS CA Certificate.
  
If running within a container, these values are normally brought into the container
via a volumeMount where IMS will look for them.  

```yaml
containers:
- image:
  ...
  env:
  - name: CA_CERT
    value: /etc/cray/ca/certificate_authority.crt
  volumeMounts:
  - name: ca-pubkey
    mountPath: /etc/cray/ca
    readOnly: true
  - name: admin-client-auth
    mountPath: '/etc/admin-client-auth'
    readOnly: true
...
volumes:
- name: ca-pubkey
  configMap:
    name: cray-configmap-ca-public-key
- name: admin-client-auth
  secret:
    secretName: "{{ keycloak_admin_client_auth_secret_name }}"
```

If these mounts are not available, the following command line options can be used:

```asciidoc
--cert CERT         Path to SMS CA Certificate
--oauth-client-id OAUTH_CLIENT_ID
                    OAuth Client ID
--oauth-client-secret OAUTH_CLIENT_SECRET
                    OAuth Client Secret
--token-url TOKEN_URL
                    Specify the base URL to the Keycloak token endpoint;
                    eg. https://api-gateway.default.svc.cluster.local/keycloak/realms/shasta/protocol/openid-connect/token
```

### Example Usage

#### Upload Image Artifacts

```bash
IMS_JOB_ID=e3a46cf3-1150-4bbf-b7c9-504993917f7d
python -m ims_python_helper image upload_artifacts "my new image" $IMS_JOB_ID \
      -r /tmp/rootfs.sqsh -k /tmp/vmlinuz -i /tmp/initramfs
{
    "ims_image_artifacts": [
        {
            "ars_artifact_id": "8702710b-bf38-4407-ae13-5331eff226f7",
            "artifact_type": "rootfs",
            "created": "2018-12-18T21:32:22.671439+00:00",
            "id": "ca7ea62e-1d5d-4400-a196-36631e73f838",
            "ims_image_id": "0c1a7c95-2a60-492c-bc81-cc225b4ee46a",
            "name": "rootfs.sqsh"
        },
        {
            "ars_artifact_id": "447695d8-f0a6-4659-b0a8-80767137d24c",
            "artifact_type": "kernel",
            "created": "2018-12-18T21:32:22.688525+00:00",
            "id": "c99300de-fd04-4a74-bb89-4b38258a6d50",
            "ims_image_id": "0c1a7c95-2a60-492c-bc81-cc225b4ee46a",
            "name": "vmlinuz"
        },
        {
            "ars_artifact_id": "e0ca12b8-631a-48c3-8d3c-d90285221f1b",
            "artifact_type": "initrd",
            "created": "2018-12-18T21:32:22.705351+00:00",
            "id": "7425b7fa-725f-45d9-a67b-7f653087a1a5",
            "ims_image_id": "0c1a7c95-2a60-492c-bc81-cc225b4ee46a",
            "name": "initramfs"
        }
    ],
    "ims_image_record": {
        "artifact_id": "8702710b-bf38-4407-ae13-5331eff226f7",
        "created": "2018-12-18T21:32:22.637793+00:00",
        "id": "0c1a7c95-2a60-492c-bc81-cc225b4ee46a",
        "name": "my new image"
    },
    "ims_job_record": {
        "artifact_id": "2233c82a-5081-4f67-bec4-4b59a60017a6",
        "build_env_size": 10,
        "created": "2018-12-17T15:44:17.389010+00:00",
        "enable_debug": false,
        "id": "e3a46cf3-1150-4bbf-b7c9-504993917f7d",
        "image_root_archive_name": "sles12sp3_barebones_image",
        "initrd_file_name": "initramfs-cray.img",
        "job_type": "create",
        "kernel_file_name": "vmlinuz",
        "kubernetes_configmap": "cray-ims-e3a46cf3-1150-4bbf-b7c9-504993917f7d-configmap",
        "kubernetes_job": "cray-ims-e3a46cf3-1150-4bbf-b7c9-504993917f7d-create",
        "kubernetes_service": "cray-ims-e3a46cf3-1150-4bbf-b7c9-504993917f7d-service",
        "public_key_id": "612d6148-588d-44a6-b0cf-60877f26ec4e",
        "resultant_image_id": "0c1a7c95-2a60-492c-bc81-cc225b4ee46a",
        "ssh_port": 0,
        "status": "creating"
    },
    "result": "success"
}
```

## Contributing

To develop, clone this git repo and install the prerequisites. A
`requirements.txt` and `constraints.txt` file are provided for you.

```bash
git clone <repo url> $REPO
cd $REPO
pip install -r requirements.txt
```

You are now ready to make changes to the codebase (preferably in a virtual
environment).

### Testing

```bash
(ims-python-helper) $ pip install -r requirements.txt
(ims-python-helper) $ pip install -r requirements-test.txt
(ims-python-helper) $ python tests/test_images.py
.
----------------------------------------------------------------------
Ran 1 test in 0.013s

OK
```

## Build Helpers
This repo uses some build helpers from the 
[cms-meta-tools](https://github.com/Cray-HPE/cms-meta-tools) repo. See that repo for more details.

## Local Builds
If you wish to perform a local build, you will first need to clone or copy the contents of the
cms-meta-tools repo to `./cms_meta_tools` in the same directory as the `Makefile`. When building
on github, the cloneCMSMetaTools() function clones the cms-meta-tools repo into that directory.

For a local build, you will also need to manually write the .version, .docker_version (if this repo
builds a docker image), and .chart_version (if this repo builds a helm chart) files. When building
on github, this is done by the setVersionFiles() function.

## Versioning
The version of this repo is generated dynamically at build time by running the version.py script in 
cms-meta-tools. The version is included near the very beginning of the github build output. 

In order to make it easier to go from an artifact back to the source code that produced that artifact,
a text file named gitInfo.txt is added to Docker images built from this repo. For Docker images,
it can be found in the / folder. This file contains the branch from which it was built and the most
recent commits to that branch. 

For helm charts, a few annotation metadata fields are appended which contain similar information.

For RPMs, a changelog entry is added with similar information.

## New Release Branches
When making a new release branch:
    * Be sure to set the `.x` and `.y` files to the desired major and minor version number for this repo for this release. 
    * If an `update_external_versions.conf` file exists in this repo, be sure to update that as well, if needed.

## Authors

* **Randy Kleinman** - *v2.0.0 - ARS -> S3 support* - CASM-1453, [CASMCMS-4342](https://connect.us.cray.com/jira/browse/CASMCMS-4342), [CASMCMS-4344](https://connect.us.cray.com/jira/browse/CASMCMS-4344)
* **Eric Cozzi** - *Initial work* - [SHASTACMS-1191](https://connect.us.cray.com/jira/browse/SHASTACMS-1191)

## Copyright and License
This project is copyrighted by Hewlett Packard Enterprise Development LP and is under the MIT
license. See the [LICENSE](LICENSE) file for details.

When making any modifications to a file that has a Cray/HPE copyright header, that header
must be updated to include the current year.

When creating any new files in this repo, if they contain source code, they must have
the HPE copyright and license text in their header, unless the file is covered under
someone else's copyright/license (in which case that should be in the header). For this
purpose, source code files include Dockerfiles, Ansible files, RPM spec files, and shell
scripts. It does **not** include Jenkinsfiles, OpenAPI/Swagger specs, or READMEs.

When in doubt, provided the file is not covered under someone else's copyright or license, then
it does not hurt to add ours to the header.

