# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2025 Delos Data, Inc.
# =============================================================================
# Configuration
# =============================================================================

# Load environment variables from .env file
ifneq (,$(wildcard ./.env))
    include .env
    export
endif

# List of required prerequisites to check
PREREQS = uv kubectl helm
ENV_VARS = ANSIBLE_REMOTE_USER REMOTE_HOST CLUSTER ANSIBLE_INVENTORY_FILE
FRAMEWORK_DIR := $(CURDIR)
TESTS_DIR := $(shell cd $(FRAMEWORK_DIR)/tests && pwd)

# Git and Qase (Qase uses QASE_TESTOPS_RUN_TITLE env var for run title; default overridable by CI/user)
GIT_COMMIT_HASH ?= (unknown commit hash)
IS_GIT_REPO := $(shell git rev-parse --is-inside-work-tree 2>/dev/null)
ifeq ($(IS_GIT_REPO),true)
GIT_COMMIT_HASH := $(shell git describe --dirty --always | sed 's/.*-g//; s/-dirty$$/ (dirty)/')
endif

QASE_TESTOPS_RUN_TITLE ?= Production test run $(GIT_COMMIT_HASH)
KUBECONFIG ?= $(HOME)/.kube/config
PATH := $(PATH):$(shell uv run dirname `uv python find` 2>/dev/null || true)

# Path to the API tunnel socket
SOCKET_PATH = /tmp/api-tunnel.sock

# Command to copy k3s kubeconfig to ~/.kube/config and set permissions (run locally or via ssh)
KUBECONFIG_SETUP = mkdir -p ~/.kube && sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config && sudo chown $$(id -u):$$(id -g) ~/.kube/config && chmod 600 ~/.kube/config

export QASE_TESTOPS_RUN_TITLE

# Emojis
OK := ✅
ERR := ❌
CONNECT := 🔌
TASK := ⏹

# Default test arguments
PYTEST_ARGS ?=
TEST_MARKER ?= "k3s or lgtm or metrics"

help:
	@echo ""
	@echo ""
	@echo "Production Test Framework"
	@echo "-------------------------"
	@echo ""
	@echo "Infrastructure management targets:"
	@echo "  prereqs                   - Check for any missing pre-requisites"
	@echo "  bootstrap-k3s             - Bootstrap k3s on target host"
	@echo "  start-ssh-tunnel          - Set up API tunnel (localhost:6443 -> REMOTE_HOST:6443)"
	@echo "  stop-ssh-tunnel           - Shutdown the API tunnel"
	@echo "  setup-kubeconfig          - Copy k3s kubeconfig to user home on remote"
	@echo "  copy-kubeconfig-local     - Copy kubeconfig from remote to ~/.kube/config (tunnel targets)"
	@echo "  setup-kubeconfig-lc       - setup-kubeconfig with LOCAL_CLUSTER=true (lc targets only)"
	@echo "  deploy-helm-charts        - Deploy Helm charts (tunnel + local kubeconfig)"
	@echo "  undeploy-helm-charts      - Remove Helm charts"
	@echo ""
	@echo "NCCL Profiler OTEL targets:"
	@echo "  profiler-otel-start       - Start OTEL stack and vLLM with NCCL profiler"
	@echo "  profiler-otel-stop        - Stop vLLM and OTEL stack containers"
	@echo "  profiler-otel-logs        - Tail vLLM container logs"
	@echo "  profiler-otel-status      - Show container and health status"
	@echo "  profiler-otel-test        - Run NCCL profiler OTEL tests (requires running stack)"
	@echo "  profiler-otel-test-only   - Run NCCL profiler OTEL tests only (stack must already be running; no start/stop)"
	@echo ""
	@echo "Testing targets (default = tunnel + local kubeconfig):"
	@echo "  test                      - Full plan: setup k3s -> tunnel -> copy kubeconfig -> deploy -> run all tests"
	@echo "                                         -> undeploy -> teardown k3s -> stop tunnel"
	@echo "  test-deploy-only          - Tunnel -> copy kubeconfig -> deploy -> run all tests -> undeploy -> stop tunnel"
	@echo "  test-run-only             - Tunnel -> copy kubeconfig -> run tests -> stop tunnel"
	@echo ""
	@echo "Testing targets (lc = run on local cluster; no tunnel):"
	@echo "  test-lc                   - Same as test; run from cluster control plane (uses setup-kubeconfig LOCAL_CLUSTER=true)"
	@echo "  test-deploy-only-lc       - Same as test-deploy-only; run from cluster host"
	@echo "  test-run-only-lc          - Run tests only; run from cluster host"
	@echo ""
	@echo "Test options:"
	@echo "  TEST_MARKER='...'         - Pytest marker (default: k3s or lgtm). Use 'not teardown' for main suite."
	@echo "  PYTEST_ARGS='...'         - Extra pytest arguments"
	@echo "  QASE_TESTOPS_RUN_TITLE    - Qase run title (default: Production test run <commit-hash> [dirty])"
	@echo ""

help-container-targets:
	@echo "Testing targets (default = tunnel + local kubeconfig):"
	@echo "  test                      - Full plan: setup k3s -> tunnel -> copy kubeconfig -> deploy -> run all tests"
	@echo "                                         -> undeploy -> teardown k3s -> stop tunnel"
	@echo "  test-deploy-only          - Tunnel -> copy kubeconfig -> deploy -> run all tests -> undeploy -> stop tunnel"
	@echo "  test-run-only             - Tunnel -> copy kubeconfig -> run tests -> stop tunnel"
	@echo ""
	@echo "NCCL Profiler OTEL targets:"
	@echo "  profiler-otel-test-only   - Run NCCL profiler OTEL tests only (stack must already be running; no start/stop)"
	@echo ""
	@echo "Test options:"
	@echo "  TEST_MARKER='...'         - Pytest marker (default: k3s or lgtm). Use 'not teardown' for main suite."
	@echo "  PYTEST_ARGS='...'         - Extra pytest arguments"
	@echo "  QASE_TESTOPS_RUN_TITLE    - Qase run title (default: Production test run <commit-hash> [dirty])"
	@echo ""

# =============================================================================
# Infrastructure Management Targets
# =============================================================================

prereqs:
	@echo "Checking pre-requisites..."
	@for exec in $(PREREQS); do \
		if command -v "$$exec" >/dev/null 2>&1; then \
			echo "    $(OK) $$exec found in PATH"; \
		else \
			echo "    $(ERR) $$exec not found in PATH"; \
		fi; \
	done
	@for env_var in $(ENV_VARS); do \
		if [ -z "$$(printenv $$env_var)" ]; then \
			echo "    $(ERR) $$env_var not set"; \
		else \
			echo "    $(OK) $$env_var is set"; \
		fi; \
	done

bootstrap-k3s: prereqs
	@echo "$(TASK) Bootstrapping k3s on cluster $(CLUSTER)..."
	ANSIBLE_REMOTE_USER=$(ANSIBLE_REMOTE_USER) \
	ansible-playbook -i $(ANSIBLE_INVENTORY_FILE) \
	./ansible/site.yml

setup-kubeconfig: prereqs
	@if [ "$(LOCAL_CLUSTER)" = "true" ]; then \
		echo "$(TASK) Copying k3s kubeconfig to ~/.kube/config (local)..."; \
		$(KUBECONFIG_SETUP) && echo "$(OK) kubeconfig copied to ~/.kube/config"; \
	else \
		echo "$(TASK) Copying k3s kubeconfig to user home on $(REMOTE_HOST)..."; \
		ssh $(ANSIBLE_REMOTE_USER)@$(REMOTE_HOST) '$(KUBECONFIG_SETUP) && echo "$(OK) kubeconfig copied to ~/.kube/config"'; \
	fi

start-ssh-tunnel: prereqs
	@echo "    $(CONNECT) Setting up a background API tunnel (localhost:6443 -> $(REMOTE_HOST):6443)..."
	@if [ -S "$(SOCKET_PATH)" ]; then \
		echo "     Socket file '$(SOCKET_PATH)' exists. The tunnel should be up, skipping tunnel creation."; \
	else \
		ssh -S $(SOCKET_PATH) -fNTM -L 6443:127.0.0.1:6443 $(ANSIBLE_REMOTE_USER)@$(REMOTE_HOST); \
	fi

stop-ssh-tunnel: prereqs
	@echo "$(TASK) Shutting down the API tunnel..."
	@ssh -S $(SOCKET_PATH) -O exit "$(ANSIBLE_REMOTE_USER)@$(REMOTE_HOST)" || true

setup-kubeconfig-lc: prereqs
	@$(MAKE) setup-kubeconfig LOCAL_CLUSTER=true

copy-kubeconfig-local: prereqs setup-kubeconfig
	@echo "$(TASK) Copying kubeconfig to locally to $(KUBECONFIG)..."
	mkdir -p ~/.kube && \
	ssh $(ANSIBLE_REMOTE_USER)@$(REMOTE_HOST) 'sudo cat /etc/rancher/k3s/k3s.yaml' > $(KUBECONFIG)
	@chmod 600 ~/.kube/config && \
	echo "$(TASK) kubeconfig copied to $(KUBECONFIG)"

deploy-helm-charts: prereqs start-ssh-tunnel
	@echo "$(TASK) Deploying Helm charts on cluster $(CLUSTER)..."
	@echo "KUBECONFIG: $(KUBECONFIG)"
	cd /app/charts/mosaic && \
	helm --kubeconfig=$(KUBECONFIG) dep update && \
	helm --kubeconfig=$(KUBECONFIG) --create-namespace --namespace=mosaic --wait --timeout=10m upgrade --install mosaic .

undeploy-helm-charts: prereqs start-ssh-tunnel
	@echo "$(TASK) Removing Helm charts from cluster $(CLUSTER)..."
	@echo "KUBECONFIG: $(KUBECONFIG)"
	@cd /app/charts/mosaic
	@kubectl --kubeconfig=$(KUBECONFIG) delete ns mosaic
	@echo "$(TASK) Helm charts removed from cluster $(CLUSTER)"

# =============================================================================
# NCCL Profiler OTEL Targets
# =============================================================================

.PHONY: profiler-otel-start profiler-otel-stop profiler-otel-logs profiler-otel-status

PROFILER_COMPOSE_FILE := $(FRAMEWORK_DIR)/profiler/docker-compose.yml

profiler-otel-start:
	@echo "$(OK) Starting OTEL stack and vLLM with NCCL Profiler..."
	@sudo docker compose -f $(PROFILER_COMPOSE_FILE) up -d
	@echo "$(OK) Containers started. Use 'make profiler-otel-logs' to watch vLLM logs."
	@echo "$(OK) vLLM will be available at http://localhost:8080 once model is loaded."
	@echo "$(OK) Grafana dashboard available at http://localhost:3000"

profiler-otel-stop:
	@echo "$(OK) Stopping all containers..."
	@sudo docker compose -f $(PROFILER_COMPOSE_FILE) down || true
	@echo "$(OK) All containers stopped."

profiler-otel-logs:
	@echo "$(OK) Tailing vLLM logs (Ctrl+C to exit)..."
	@sudo docker compose -f $(PROFILER_COMPOSE_FILE) logs -f mosaic-vllm

profiler-otel-status:
	@echo "$(OK) Checking container status..."
	@sudo docker compose -f $(PROFILER_COMPOSE_FILE) ps
	@echo ""
	@echo "vLLM Health:"
	@sudo docker inspect mosaic-vllm --format='{{.State.Health.Status}}' 2>/dev/null || echo "Container not running"

run-otel-test:
	@echo "$(OK) Running NCCL profiler OTEL tests..."
	uv run pytest -m profiler_otel -v $(PYTEST_ARGS) $(TESTS_DIR)/profiler_otel -s;

profiler-otel-test: profiler-otel-start run-otel-test profiler-otel-stop

profiler-otel-test-only: run-otel-test

# =============================================================================
# Base Test Targets (used by all test targets)
# =============================================================================

.PHONY: run-all-tests run-tests
.PHONY: test test-deploy-only test-run-only
.PHONY: test-lc test-deploy-only-lc test-run-only-lc

# Single test run (one marker). QASE_TESTOPS_RUN_TITLE is exported above.
run-tests: prereqs
	@echo "$(TASK) Running tests with marker: $(TEST_MARKER)..."
	@cd $(TESTS_DIR) && uv run pytest -m $(TEST_MARKER) -v $(PYTEST_ARGS) .; \
	exit $$?;


# Full test plan: main tests -> undeploy -> teardown tests (for use cases that deploy)
run-all-tests: run-tests undeploy-helm-charts
	@echo "$(TASK) Running teardown tests..."; \
	cd $(TESTS_DIR) && uv run pytest -m teardown -v $(PYTEST_ARGS) .; \
	exit $$?;

# -----------------------------------------------------------------------------
# Top-level test targets
# -----------------------------------------------------------------------------

test: prereqs bootstrap-k3s start-ssh-tunnel copy-kubeconfig-local deploy-helm-charts run-all-tests stop-ssh-tunnel

test-deploy-only: prereqs start-ssh-tunnel copy-kubeconfig-local deploy-helm-charts run-all-tests stop-ssh-tunnel

test-run-only: prereqs start-ssh-tunnel copy-kubeconfig-local
	@$(MAKE) run-tests TEST_MARKER='not teardown'; EXIT_CODE=$$?; $(MAKE) stop-ssh-tunnel; exit $$EXIT_CODE

test-lc: prereqs bootstrap-k3s setup-kubeconfig-lc deploy-helm-charts run-all-tests

test-deploy-only-lc: prereqs setup-kubeconfig-lc deploy-helm-charts run-all-tests

test-run-only-lc: prereqs
	@$(MAKE) run-tests TEST_MARKER='not teardown'; EXIT_CODE=$$?; exit $$EXIT_CODE
