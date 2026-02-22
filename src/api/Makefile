API?=release

CODE=		$(API)/api.py \
		$(API)/queries.py \
		$(API)/ratelimit.py \
		$(API)/schema.sql \
		$(API)/sync.py

TEMPLATES=	$(API)/templates/login.html \
		$(API)/templates/account.html \
		$(API)/templates/flock.html

all: $(API) $(CODE) $(TEMPLATES)

$(API)/%.py: %.py
	cp $< $@

$(API)/%.sql: %.sql
	cp $< $@

$(API)/templates/%.html: templates/%.html
	cp $< $@

$(API):
	mkdir -p $(API)/templates

clean:
	rm -rf $(API)
