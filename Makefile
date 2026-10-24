# Thin wrapper: every target delegates to tasks.py so Windows users without GNU make
# can run the identical command with `python tasks.py <target>` (ADR-014).
PY ?= python
TARGETS := setup test test-network lint typecheck honest-check audit-deps data data-audit graph \
           graph-apply-review load experiments report api frontend-build e2e demo ci

.PHONY: $(TARGETS)
$(TARGETS):
	$(PY) tasks.py $@
