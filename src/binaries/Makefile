BUILD?=build
OUTPUT?=binaries

LIBSODIUM_VERSION=1.0.20
LIBSODIUM?=$(TOP)/src/binaries/libsodium-$(LIBSODIUM_VERSION).tar.gz

KORE_GIT?=https://github.com/jorisvink/kore
SANCTUM_GIT?=https://github.com/jorisvink/sanctum
SYNCRETISM_GIT?=https://github.com/jorisvink/syncretism

TARGETS=	$(OUTPUT)/kore \
		$(OUTPUT)/sanctum \
		$(OUTPUT)/syncretism \
		$(BUILD)/fakeroot/lib/libsodium.a

targets: $(TARGETS)

$(OUTPUT)/kore: $(BUILD)/kore/kore
	cp $(BUILD)/kore/kore $(OUTPUT)/kore

$(OUTPUT)/sanctum: $(BUILD)/sanctum/sanctum
	cp $(BUILD)/sanctum/sanctum $(OUTPUT)/sanctum

$(OUTPUT)/syncretism: $(BUILD)/syncretism/syncretism
	cp $(BUILD)/syncretism/syncretism $(OUTPUT)/syncretism

$(BUILD)/fakeroot/lib/libsodium.a: $(BUILD)
	mkdir -p $(BUILD)/fakeroot
	cd $(BUILD) && tar zfvx $(LIBSODIUM)
	cd $(BUILD)/libsodium-$(LIBSODIUM_VERSION) && \
	    env CC=clang ./configure --prefix=$(BUILD)/fakeroot \
	    --enable-shared=no && make -j && make install

$(BUILD)/sanctum/sanctum: $(BUILD)/fakeroot/lib/libsodium.a
	git clone $(SANCTUM_GIT) $(BUILD)/sanctum
	env PKG_CONFIG_PATH=$(BUILD)/fakeroot/lib/pkgconfig \
	    $(MAKE) -C $(BUILD)/sanctum

$(BUILD)/kore/kore:
	git clone $(KORE_GIT) $(BUILD)/kore
	$(MAKE) -C $(BUILD)/kore PREFIX=$(OUTPUT)/fakeroot \
	    PYTHON=1 ACME=1 PGSQL=1
	$(MAKE) -C $(BUILD)/kore PREFIX=$(OUTPUT)/fakeroot \
	    PYTHON=1 ACME=1 PGSQL=1 install

$(BUILD)/syncretism/syncretism:
	git clone $(SYNCRETISM_GIT) $(BUILD)/syncretism
	$(MAKE) -C $(BUILD)/syncretism

$(BUILD):
	mkdir -p $(BUILD)

clean:
	rm -rf $(BUILD) $(BINARIES)
