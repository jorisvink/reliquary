ARCH?=`uname -m`
BUILD?=`pwd`/build
OUTPUT?=`pwd`/release-$(ARCH)
TOP=`pwd`

all: api cli binaries

api: $(OUTPUT)
	$(MAKE) -C src/api API=$(OUTPUT)/api-files

cli: $(OUTPUT)
	$(MAKE) -C src/cli CLI=$(OUTPUT)/cli-files

binaries: $(OUTPUT) $(BUILD)
	$(MAKE) -C src/binaries TOP=$(TOP) OUTPUT=$(OUTPUT) BUILD=$(BUILD)

ansible-deps:
	ansible-galaxy collection install community.postgresql

$(OUTPUT):
	mkdir -p $(OUTPUT)

$(BUILD):
	mkdir -p $(BUILD)

clean:
	rm -rf $(OUTPUT) $(BUILD)

ubuntu-24.04:
	podman build -t build-ubuntu-24.04 containers/ubuntu-24.04
	podman run -ti -v `pwd`:/home/builder build-ubuntu-24.04 make
	podman rm -a

podman-clean:
	podman rm -a
	podman rmi -a

cli-release: cli
	cd $(OUTPUT)/cli-files && tar cvf ../reliquary-cli.tar .
