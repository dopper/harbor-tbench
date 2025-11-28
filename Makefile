# Simple helpers for Harbor + custom agents

.DEFAULT_GOAL := help

# Prefer a py3.12 interpreter (daytona/obstore wheels not available yet for 3.14)
PYTHON ?= $(shell command -v python3.12 || command -v python3.11 || command -v python3)
VENV := .venv
PIP := $(VENV)/bin/pip
HARBOR := $(VENV)/bin/harbor

.PHONY: help venv install clean

help: ## Show available targets
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

venv: ## Create local virtualenv at .venv (defaults to python3.12 if available)
	@test -n "$(PYTHON)" || { echo "No suitable python found (looked for python3.12, python3.11, python3)"; exit 1; }
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)

install: venv ## Install/upgrade pip and install Harbor into .venv
	$(PIP) install --upgrade pip
	$(PIP) install harbor

clean: ## Remove the virtualenv
	rm -rf $(VENV)
