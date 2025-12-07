TARGETS=$(CLI)/reliquary-ambry-upload \
	$(CLI)/reliquary-cathedral-list \
	$(CLI)/reliquary-device-approve \
	$(CLI)/reliquary-device-delete \
	$(CLI)/reliquary-device-list \
	$(CLI)/reliquary-flock-join \
	$(CLI)/reliquary-flock-create \
	$(CLI)/reliquary-flock-delete \
	$(CLI)/reliquary-flock-list \
	$(CLI)/reliquary-flock-liturgy \
	$(CLI)/reliquary-kek-send \
	$(CLI)/reliquary-kek-recv \
	$(CLI)/reliquary-kek-install \
	$(CLI)/reliquary-init \
	$(CLI)/reliquary-login \
	$(CLI)/reliquary-status \
	$(CLI)/reliquary-register \
	$(CLI)/reliquary-voice-call \
	$(CLI)/reliquary-voice-liturgy \
	$(CLI)/reliquary-tunnel-config

all: $(CLI) $(TARGETS)

$(CLI)/%: %
	cp $< $@

$(CLI):
	mkdir -p $(CLI)

clean:
	rm -rf $(CLI)
