LAB := ./scripts/lab
MODEL ?= coder
USE_CASE ?= coder

.PHONY: doctor test catalog presets pull start stop restart status logs models load switch unload unload-active auto-idle-on auto-idle-off auto-idle-toggle service-install service-start service-stop service-restart service-status service-uninstall chat verify bench-llama bench-server bench-quality

doctor:
	$(LAB) doctor

test:
	python3 -m unittest discover -s tests

catalog:
	$(LAB) catalog

presets:
	$(LAB) presets

pull:
	$(LAB) pull $(MODEL)

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

verify:
	$(LAB) verify $(MODEL)

bench-llama:
	$(LAB) bench-llama $(MODEL)

bench-server:
	$(LAB) bench-server $(USE_CASE)

bench-quality:
	$(LAB) bench-quality $(USE_CASE)
