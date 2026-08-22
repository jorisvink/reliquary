TARGETS=$(CLI)/rlq

all: $(CLI) $(TARGETS)

$(CLI)/%: %
	cp $< $@

$(CLI):
	mkdir -p $(CLI)

clean:
	rm -rf $(CLI)
