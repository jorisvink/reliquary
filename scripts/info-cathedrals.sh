#!/bin/sh

set -e

if [ "$#" -lt 1 ]; then
	echo "Usage: info-cathedral.sh [config]"
	exit 1
fi

CONFIG=`realpath $1 `

shift

if [ ! -d $CONFIG ]; then
	echo "given configuration is not a directory"
	exit 1
fi

echo "Using configuration $CONFIG"

ansible-playbook -i $CONFIG/cathedrals.yaml \
	ansible/cathedral-info.yaml \
	-u priest \
	$@
