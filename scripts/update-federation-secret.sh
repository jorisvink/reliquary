#!/bin/sh

set -e

if [ "$#" -lt 1 ]; then
	echo "Usage: update-federation-secret.sh [config]"
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
	--ask-vault-password \
	ansible/cathedral-federation.yaml \
	-u priest -K \
	-e config=$CONFIG \
	-e @$CONFIG/keys.vault \
	-e @$CONFIG/settings.yaml \
	$@
