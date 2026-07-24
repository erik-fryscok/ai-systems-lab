LAB := ./scripts/lab
MODEL ?= coder
USE_CASE ?= coder

.PHONY: doctor presets pull pull-all start stop restart status logs models load switch unload unload-active auto-idle-on auto-idle-off auto-idle-toggle service-install service-start service-stop service-restart service-status service-uninstall chat bench-llama bench-server bench-quality

doctor:
	$(LAB) doctor

presets:
	$(LAB) presets

pull:
	$(LAB) pull $(MODEL)

pull-all:
	$(LAB) pull all

start:
	$(LAB) start

stop:
	$(LAB) stop

restart: stop start

status:
	$(LAB) status

logs:
	$(LAB) logs

models:
	$(LAB) list

load:
	$(LAB) load $(MODEL)

switch:
	$(LAB) switch $(MODEL)

unload:
	$(LAB) unload $(MODEL)

unload-active:
	$(LAB) unload-active

auto-idle-on:
	$(LAB) auto-idle on

auto-idle-off:
	$(LAB) auto-idle off

auto-idle-toggle:
	$(LAB) auto-idle toggle

service-install:
	$(LAB) service-install

service-start:
	$(LAB) service-start

service-stop:
	$(LAB) service-stop

service-restart:
	$(LAB) service-restart

service-status:
	$(LAB) service-status

service-uninstall:
	$(LAB) service-uninstall

chat:
	$(LAB) chat $(MODEL) "$(PROMPT)"

bench-llama:
	$(LAB) bench-llama $(MODEL)

bench-server:
	$(LAB) bench-server $(USE_CASE)

bench-quality:
	$(LAB) bench-quality $(USE_CASE)
