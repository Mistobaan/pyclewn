#! /bin/bash

if [ -z "$*" ]; then
    set $* $(find clewn/ testsuite/ -name "*py")
fi

for i in $*; do
    echo "--- $i"
    pychecker --quiet -F ./.pycheckrc $i
done

