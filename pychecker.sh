#! /bin/bash

list=$(find clewn/ testsuite/ -name "*py")

for i in $list; do
    echo "--- $i"
    pychecker --quiet -F ./.pycheckrc $i
done

