#!/bin/sh

set -e

if [ "$#" -lt 1 ]; then
	echo "Usage: update-ubuntu.sh [config]"
	exit 1
fi

if [ -z "$CATHEDRAL_USER" ]; then
	user="-u priest -K"
else
	user="-u $CATHEDRAL_USER"
fi

CONFIG=`realpath $1 `
shift

if [ ! -d $CONFIG ]; then
	echo "given configuration is not a directory"
	exit 1
fi

echo "Using configuration $CONFIG"

ansible-playbook -i $CONFIG/api.yaml -i $CONFIG/cathedrals.yaml \
	ansible/ubuntu-update.yaml \
	$user $@
