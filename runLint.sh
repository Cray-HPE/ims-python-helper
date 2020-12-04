#!/bin/bash

#
# Copyright 2019, Cray Inc.  All Rights Reserved.
#

# Very simple scanner for files missing copyrights

# Extensions to check
CODE_EXTENSIONS="py sh c"

# Additional files to check, uses exact match
EXTRA_FILES=""

FAIL=0

function scan_file {
    echo -n "Scanning $1... "
    # skip empty files
    if [ -s $1 ]; then
        grep -q "Copyright" $1
        if [ $? -ne 0 ]; then
            echo "missing copyright headers"
            return 1
        fi
    fi
    echo "OK"
    return 0
}

# Scan extentions
for CE in ${CODE_EXTENSIONS}
do
    for F in `git ls-files "*.${CE}"`
    do
        scan_file ${F}
        if [ $? -ne 0 ]; then
            FAIL=1
        fi
    done
done

# Do the listed extra files
for F in ${EXTRA_FILES}
do
    scan_file ${F}
done

if [ ${FAIL} -eq 0 ]; then
    echo "All scanned code passed"
else
    echo "Some code is missing copyright, see list above"
fi

exit ${FAIL}