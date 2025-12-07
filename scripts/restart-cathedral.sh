#!/bin/sh

set -e

if [ "$#" -lt 1 ]; then
	echo "Usage: restart-cathedral.sh [config]"
	exit 1
fi

if [ ! -z "$API_INIT" ]; then
	user="-u root"
else
	user="-u priest -K"
fi

CONFIG=`realpath $1 `

shift

if [ ! -d $CONFIG ]; then
	echo "given configuration is not a directory"
	exit 1
fi

echo "Using configuration $CONFIG"

ansible-playbook -i $CONFIG/cathedrals.yaml \
	ansible/cathedral-services.yaml \
	$user \
	$@
