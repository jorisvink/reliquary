# Reliquary makefile

TOP=$(shell pwd)
BUILD?=$(TOP)/build
OUTPUT?=$(TOP)/release-$(ARCH)
ARCH?=$(shell uname -m)

KORE_GIT?=https://github.com/jorisvink/kore
SANCTUM_GIT?=https://github.com/jorisvink/sanctum
SYNCRETISM_GIT?=https://github.com/jorisvink/syncretism

export KORE_GIT
export SANCTUM_GIT
export SYNCRETISM_GIT

export TOP
export ARCH
export BUILD
export OUTPUT

all: api cli binaries

api: $(OUTPUT)
	$(MAKE) -C src/api API=$(OUTPUT)/api-files

cli: $(OUTPUT)
	$(MAKE) -C src/cli CLI=$(OUTPUT)/cli-files

binaries: $(OUTPUT) $(BUILD)
	$(MAKE) -C src/binaries

ansible-deps:
	ansible-galaxy collection install community.postgresql

$(OUTPUT):
	mkdir -p $(OUTPUT)

$(BUILD):
	mkdir -p $(BUILD)

clean:
	rm -rf $(OUTPUT) $(BUILD)

ubuntu-24.04:
	rm -f .reliquary-env
	echo "KORE_GIT=$(KORE_GIT)" >> .reliquary-env
	echo "SANCTUM_GIT=$(SANCTUM_GIT)" >> .reliquary-env
	echo "SYNCRETISM_GIT=$(SYNCRETISM_GIT)" >> .reliquary-env
	podman build -t build-ubuntu-24.04 containers/ubuntu-24.04
	podman run --env-file .reliquary-env -ti -v $(TOP):/home/builder \
	    build-ubuntu-24.04 make
	podman rm -a
	rm -f .reliquary-env

podman-clean:
	podman rm -a
	podman rmi -a

cli-release: cli
	cd $(OUTPUT)/cli-files && tar cvf ../reliquary-cli.tar .
