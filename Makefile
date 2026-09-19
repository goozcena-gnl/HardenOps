PYTHON ?= python3
DISTRO ?=
PROVIDER ?=
LEVEL ?= minimal
IMAGE ?= ubuntu:24.04
export ANSIBLE_CONFIG := $(CURDIR)/ansible.cfg
export ANSIBLE_COLLECTIONS_PATH := $(CURDIR)/.collections
export MOLECULE_GLOB := tests/molecule/*/molecule.yml
export HARDENOPS_TEST_IMAGE := $(IMAGE)

.PHONY: help install deploy status inventory plan harden verify destroy lint syntax validate test molecule hygiene

help:
	@echo "HardenOps 0.1.0 — disposable Linux hardening lab"
	@echo "make install                         Install controller dependencies in the active venv"
	@echo "make deploy DISTRO=ubuntu2404        Boot Ubuntu 24.04 (default PROVIDER=libvirt)"
	@echo "make deploy DISTRO=rocky9            Boot Rocky Linux 9"
	@echo "make status                          Show remembered VM state"
	@echo "make plan LEVEL=minimal              Inspect and plan without changing the target"
	@echo "make harden LEVEL=intermediary       Apply the cumulative baseline"
	@echo "make verify LEVEL=intermediary       Inspect state and write reports"
	@echo "make destroy                         Destroy this lab VM and local connection state"
	@echo "make lint validate test              Static validation and unit tests"
	@echo "make molecule IMAGE=ubuntu:24.04      Filesystem role container test (Docker required)"
	@echo "make molecule IMAGE=rockylinux:9      Repeat filesystem test on Rocky Linux"

install:
	$(PYTHON) -m pip install -r requirements-dev.txt
	ansible-galaxy collection install -r requirements.yml

deploy:
	$(PYTHON) tools/lab.py deploy $(if $(DISTRO),--distro $(DISTRO)) $(if $(PROVIDER),--provider $(PROVIDER))
	ansible-playbook -i .lab/inventory.yml ansible/playbooks/baseline.yml

status:
	$(PYTHON) tools/lab.py status

inventory:
	$(PYTHON) tools/lab.py inventory

plan harden verify: inventory
	ansible-playbook -i .lab/inventory.yml ansible/playbooks/$@.yml -e hardenops_level=$(LEVEL)

destroy:
	$(PYTHON) tools/lab.py destroy

lint:
	yamllint .
	ansible-lint
	$(MAKE) syntax

syntax:
	ansible-playbook -i ansible/inventories/lab/hosts.yml --syntax-check ansible/playbooks/baseline.yml
	ansible-playbook -i ansible/inventories/lab/hosts.yml --syntax-check ansible/playbooks/plan.yml
	ansible-playbook -i ansible/inventories/lab/hosts.yml --syntax-check ansible/playbooks/harden.yml
	ansible-playbook -i ansible/inventories/lab/hosts.yml --syntax-check ansible/playbooks/verify.yml

validate:
	$(PYTHON) tools/validate_catalog.py

test:
	$(PYTHON) -m pytest

molecule:
	molecule test -s filesystem

hygiene:
	git ls-files -z | xargs -0 detect-secrets-hook
	$(PYTHON) -m pip_audit -r requirements-dev.txt
