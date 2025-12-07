#!/bin/sh

set -e

if [ "$#" -lt 1 ]; then
	echo "Usage: update-ubuntu.sh [config]"
	exit 1
fi

if [ ! -z "$ROOT" ]; then
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

ansible-playbook -i $CONFIG/api.yaml \
	--ask-vault-password \
	ansible/ubuntu-update.yaml \
	$user $@
