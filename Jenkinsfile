// Jenkinsfile for ims-python-helper Python package
 
@Library('dst-shared@release/shasta-1.4') _

pipeline {
    agent {
        kubernetes {
            label "cray-ims-python-helper-test-pod"
            containerTemplate {
                name "cray-ims-python-helper-test-cont"
                image "arti.dev.cray.com/internal-docker-master-local/cray-alpine3_build_environment:latest"
                ttyEnabled true
                command "cat"
            }
        }
    }

    // Configuration options applicable to the entire job
    options {
        // This build should not take long, fail the build if it appears stuck
        timeout(time: 10, unit: 'MINUTES')

        // Don't fill up the build server with unnecessary cruft
        buildDiscarder(logRotator(numToKeepStr: '5'))

        // Add timestamps and color to console output, cuz pretty
        timestamps()
    }

    environment {
        // Set environment variables here
        GIT_TAG = sh(returnStdout: true, script: "git rev-parse --short HEAD").trim()
    }

    stages {
        stage('Build Package') {
            steps {
                container('cray-ims-python-helper-test-cont') {
                    sh """
                        apk add --no-cache --virtual .build-deps py3-pip curl bash
                        apk add --no-cache --update python3
                        pip3 install --upgrade pip setuptools
                        pip3 install wheel
                        python3 setup.py sdist bdist_wheel
                    """             
                }
            }
        }

        stage('Unit Tests') {
            steps {
                container('cray-ims-python-helper-test-cont') {
                    sh """
                       pip3 install -r requirements.txt
                       pip3 install -r requirements-test.txt
                       python3 tests/test_images.py
                       pycodestyle --config=.pycodestyle ./ims_python_helper || true
                       pylint ./ims_python_helper || true
                    """
                }
            }
        }

        stage('PUBLISH') {
            when { branch 'master'}
            steps {
                container('cray-ims-python-helper-test-cont') {
                    // Need to install ssh and rsync commands and get private key in place for transferPkgs
                    // sshpass is for the transferPkgs function
                    sh """
                        apk add --no-cache openssh-client rsync sshpass bash curl
                        mkdir -p /root/.ssh
                        cp id_rsa-casmcms-tmp /root/.ssh/id_rsa
                        chmod 600 /root/.ssh/id_rsa
                    """
                    transferPkgs(directory: "ims-python-helper", artifactName: "dist/*.tar.gz")
                    transferPkgs(directory: "ims-python-helper", artifactName: "dist/*.whl")
                }
            }
        }
    }

    post('Post-build steps') {
        failure {
            emailext (
                subject: "FAILED: Job '${env.JOB_NAME} [${env.BUILD_NUMBER}]'",
                body: """<p>FAILED: Job '${env.JOB_NAME} [${env.BUILD_NUMBER}]':</p>
                <p>Check console output at &QUOT;<a href='${env.BUILD_URL}'>${env.JOB_NAME} [${env.BUILD_NUMBER}]</a>&QUOT;</p>""",
                recipientProviders: [[$class: 'CulpritsRecipientProvider'], [$class: 'RequesterRecipientProvider']]
            )
        }

        success {
            archiveArtifacts artifacts: 'dist/*', fingerprint: true
        }
    }
}
