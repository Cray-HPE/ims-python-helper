# Copyright 2019,2021 Hewlett Packard Enterprise Development LP
Name: cray-ims-python-helper-crayctldeploy
License: Cray Software License Agreement
Summary: Rich Client Support for Cray Image Management Service
Group: System/Management
Version: %(cat .rpm_version)
Release: %(echo ${BUILD_METADATA})
Source: %{name}-%{version}.tar.bz2
Vendor: Cray Inc.
BuildRequires: python3 >= 3.6.8
BuildRequires: wget >= 1.14
Requires: python3 >= 3.6.8
Requires: python3-requests >= 2.18
Requires: python-idna
Requires: python3-certifi >= 2018.1.18
Requires: python3-boto3
Requires: cray-python-helper-requires-crayctldeploy

%description
Client library to use in conjunction with IMS from a non-compute node.

%prep
%setup -q

%build
python3 setup.py build
curl https://bootstrap.pypa.io/pip/2.7/get-pip.py --output get-pip.py
python3 get-pip.py

%install
python3 setup.py install --root %{buildroot} --record=PY3_INSTALLED_FILES

cat PY3_INSTALLED_FILES | grep __pycache__ | xargs dirname | xargs dirname | uniq >> PY3_INSTALLED_FILES
cat PY*_INSTALLED_FILES > INSTALLED_FILES
cat INSTALLED_FILES

%clean
rm -rf  %{buildroot}/usr/lib/python3.6/site-packages/ims_python_helper*

%files -f INSTALLED_FILES
%defattr(-,root,root)

%changelog

