# Copyright 2019 Cray Inc. All Rights Reserved.
Name: cray-ims-python-helper-crayctldeploy
License: Cray Software License Agreement
Summary: Rich Client Support for Cray Image Management Service
Group: System/Management
Version: %(cat .rpm_version)
Release: %(echo ${BUILD_METADATA})
Source: %{name}-%{version}.tar.bz2
Vendor: Cray Inc.
BuildRequires: python == 2.7
BuildRequires: python3 >= 3.6.8
BuildRequires: wget >= 1.14
Requires: python3 >= 3.6.8
Requires: python3-requests >= 2.18
Requires: python-idna
Requires: python2-certifi >= 2018.1.18
Requires: python3-certifi >= 2018.1.18
Requires: python2-boto3
Requires: python3-boto3
Requires: cray-python-helper-requires-crayctldeploy

%description
Client library to use in conjunction with IMS from a non-compute node.
Python 2 and 3 versions are installed.

%prep
%setup -q

%build
python setup.py build
python3 setup.py build
wget https://bootstrap.pypa.io/get-pip.py
python get-pip.py
python3 get-pip.py

%install
python2.7 setup.py install --root %{buildroot} --record=PY2_INSTALLED_FILES
python3 setup.py install --root %{buildroot} --record=PY3_INSTALLED_FILES

cat PY2_INSTALLED_FILES | grep __init__.pyc | xargs dirname | uniq >> PY2_INSTALLED_FILES
cat PY3_INSTALLED_FILES | grep __pycache__ | xargs dirname | xargs dirname | uniq >> PY3_INSTALLED_FILES
cat PY*_INSTALLED_FILES > INSTALLED_FILES
cat INSTALLED_FILES

%clean
rm -rf  %{buildroot}/usr/lib/python2.7/site-packages/ims_python_helper*
rm -rf  %{buildroot}/usr/lib/python3.6/site-packages/ims_python_helper*

%files -f INSTALLED_FILES
%defattr(-,root,root)

%changelog

