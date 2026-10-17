# Copyright (c) 2026 AWA <https://www.akkdiy.cn>. All rights reserved.
CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra -Werror
DESTDIR ?= /tmp/DBBackup

.PHONY: all clean install assets
all: build/index.cgi build/api.cgi assets

build:
	mkdir -p build

build/index.cgi: src/cgi_launcher.c | build
	$(CC) $(CFLAGS) -DDBBACKUP_ENTRY=\"index\" $< -o $@

build/api.cgi: src/cgi_launcher.c | build
	$(CC) $(CFLAGS) -DDBBACKUP_ENTRY=\"api\" $< -o $@

assets: | build
	python3 src/generate_icons.py build/assets

install: all
	install -d -m 0755 "$(DESTDIR)/ui/images" "$(DESTDIR)/share" "$(DESTDIR)/var"
	install -m 0755 build/index.cgi "$(DESTDIR)/ui/index.cgi"
	install -m 0755 build/api.cgi "$(DESTDIR)/ui/api.cgi"
	install -m 0644 ui/config ui/DBBackup.js "$(DESTDIR)/ui/"
	install -m 0644 build/assets/icon_16.png build/assets/icon_24.png build/assets/icon_32.png build/assets/icon_48.png build/assets/icon_64.png build/assets/icon_72.png build/assets/icon_256.png "$(DESTDIR)/ui/images/"
	install -m 0644 src/cgi_app.py src/worker.py "$(DESTDIR)/share/"

clean:
	rm -rf build

