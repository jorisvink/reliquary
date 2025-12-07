#!/bin/sh

set -e

if [ "$#" -lt 1 ]; then
	echo "Usage: deploy-cathedrals.sh [config]"
	exit 1
fi

if [ ! -z "$CATHEDRAL_INIT" ]; then
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
	--ask-vault-password \
	ansible/cathedral-deploy.yaml \
	$user \
	-e config=$CONFIG \
	-e @$CONFIG/keys.vault \
	-e @$CONFIG/settings.yaml \
	-e release=`pwd`/release \
	$@
