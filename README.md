# Production Test Framework

The Production Test Framework provides automated infrastructure for deploying, validating, and testing production platform components. This framework automates cluster setup, service deployment, and execution of integration tests.

## Overview

The framework enables end-to-end testing of the following areas:

- **K3s Cluster Management**: Automated bootstrap and validation of k3s clusters
- **LGTM Stack Deployment**: Automated deployment of Loki, Grafana, Tempo, and Mimir
- **Integration Testing**: Automated test execution with proper setup and teardown
- **Infrastructure Automation**: SSH tunnels, kubeconfig management, and dependency synchronization

## Quick Start

To get tests running with a single command: clone the repo, copy and edit `.env` (from `env.example`) and `ansible/inventory.ini` (from `ansible/inventory.example.ini`) with your host and credentials, then run:

```bash
git clone <repo-url> production-test-framework
cd production-test-framework
cp env.example .env
cp ansible/inventory.example.ini ansible/inventory.ini
# Edit .env and ansible/inventory.ini with your hostnames and credentials
uv sync
make test
```

For more detail (prerequisites, cluster setup, other test targets), see the full **Quick Start** guide below.

## Prerequisites

Before using the framework, ensure you have the following installed:

- `kubectl` - Kubernetes command-line tool
- `helm` - Kubernetes package manager
- `uv` - Python package manager
- SSH access to the target cluster host

### Required Environment Variables

The framework requires the following environment variables to be set:

```bash
export ANSIBLE_REMOTE_USER="your-ssh-username"
export REMOTE_HOST="target-cluster-hostname-or-ip"
export CLUSTER="cluster-name"
export ANSIBLE_INVENTORY_FILE="/path/to/ansible/inventory.ini"
```

SSH uses key forwarding (agent); ensure your SSH agent has the key loaded (`ssh-add`) or that you use an environment where keys are forwarded (e.g. `ForwardAgent yes` in SSH config).

For Qase test reporting, set **`QASE_TESTOPS_API_TOKEN`** (optional). If unset, `make prereqs` will report it as missing but tests can still run.

You can also create a `.env` file in the project root with the variables above specified. Copy `env.example` to `.env` and edit the values. The `.env` file will be loaded when make is run.

**Optional / advanced:** `MOSAIC_ROOT` is used by `deploy-helm-charts` and `undeploy-helm-charts` to locate Helm charts (e.g. `$(MOSAIC_ROOT)/sw/epsw/charts/mosaic`). Set it if you use those targets with a compatible chart layout. `TESTS_DIR` defaults to `../tests` (sibling of the framework directory); set it if your tests live elsewhere.

## Quick Start

### 1. Clone and set up

Clone this repository, then create your local configuration:

```bash
git clone <repo-url> production-test-framework
cd production-test-framework
cp env.example .env
cp ansible/inventory.example.ini ansible/inventory.ini
# Edit .env and ansible/inventory.ini with your hostnames and credentials
uv sync
```

### 2. Check Prerequisites

Verify all prerequisites are installed and environment variables are set:

```bash
make prereqs
```

### 3. Set Up a Cluster

The framework can bootstrap a new k3s cluster or work with an existing one:

```bash
# Bootstrap k3s on the target host (if needed)
make bootstrap-k3s

# Set up SSH tunnel for kubectl access
make start-ssh-tunnel

# Copy kubeconfig from remote to local (for tunnel-based workflows)
make copy-kubeconfig-local
```

### 4. Run Tests

The framework provides use-case targets (default: SSH tunnel + local kubeconfig):

```bash
# Full plan: setup k3s -> deploy -> run all tests -> undeploy -> teardown k3s
make test

# Deploy only: tunnel -> deploy -> run all tests -> undeploy
make test-deploy-only

# Run tests only: tunnel -> copy kubeconfig -> run tests
make test-run-only
```

When running from the cluster control plane (repo cloned there, same layout), use the **-lc** (local cluster) targets; they use **setup-kubeconfig** with **LOCAL_CLUSTER=true** (via **setup-kubeconfig-lc**) instead of a tunnel and **copy-kubeconfig-local**:

```bash
make test-lc
make test-deploy-only-lc
make test-run-only-lc
```

## Makefile Targets

### Infrastructure management

- **`prereqs`** - Check for missing prerequisites and environment variables
- **`bootstrap-k3s`** - Bootstrap k3s on target host (uses Ansible from project Python deps)
- **`start-ssh-tunnel`** / **`stop-ssh-tunnel`** - Set up or shut down API tunnel (localhost:6443 → REMOTE_HOST:6443)
- **`setup-kubeconfig`** - Copy k3s kubeconfig and set permissions. With **LOCAL_CLUSTER=true** runs locally; otherwise SSHs to remote and runs there.
- **`copy-kubeconfig-local`** - Copy kubeconfig from remote to ~/.kube/config (for tunnel-based targets; depends on setup-kubeconfig)
- **`setup-kubeconfig-lc`** - Invoke setup-kubeconfig with LOCAL_CLUSTER=true (for -lc targets)
- **`deploy-helm-charts`** / **`undeploy-helm-charts`** - Deploy or remove Helm charts (tunnel + local kubeconfig)

### NCCL Profiler OTEL targets

- **`profiler-otel-start`** - Start OTEL stack and vLLM with NCCL profiler
- **`profiler-otel-stop`** - Stop vLLM and OTEL stack containers
- **`profiler-otel-logs`** - Tail vLLM container logs
- **`profiler-otel-status`** - Show container and health status
- **`profiler-otel-test`** - Run NCCL profiler OTEL tests (requires running stack)

### Test targets (default: tunnel + local kubeconfig)

- **`test`** - Full plan: bootstrap k3s → start tunnel → copy kubeconfig → deploy → run all tests → stop tunnel
- **`test-deploy-only`** - Start tunnel → copy kubeconfig → deploy → run all tests → undeploy → stop tunnel
- **`test-run-only`** - Start tunnel → copy kubeconfig → run tests → stop tunnel

### Test targets (-lc: run on local cluster; no tunnel)

- **`test-lc`** - Same as test; run from cluster control plane (uses setup-kubeconfig LOCAL_CLUSTER=true)
- **`test-deploy-only-lc`** - Same as test-deploy-only; run from cluster host
- **`test-run-only-lc`** - Run tests only; run from cluster host

### Test options

- **`TEST_MARKER`** - Pytest marker (default: `k3s or lgtm`). Use `not teardown` for the main test suite.
- **`PYTEST_ARGS`** - Extra arguments passed to pytest.
- **`QASE_TESTOPS_RUN_TITLE`** - Qase automated test run title. Default: "Production test run <commit-hash> [dirty]". Override for CI or custom runs.

```bash
make test-run-only TEST_MARKER='not teardown' PYTEST_ARGS='-x'
make test QASE_TESTOPS_RUN_TITLE="CI run 123"
```

## Test Structure

By default, tests are expected in `../tests/lgtm/` (a sibling directory). Set `TESTS_DIR` if your tests live elsewhere. Tests are organized by validation area:

- **`test_k3s_cluster.py`** - K3s cluster health and node validation
- **`test_namespaces.py`** - Namespace and pod validation
- **`test_services.py`** - Service and storage validation
- **`test_teardown.py`** - Post-teardown validation

Tests use pytest markers for organization:
- `k3s` - K3s cluster validation tests
- `lgtm` - LGTM stack integration tests
- `teardown` - Teardown validation tests


## Building the test framework Docker image

From the project root:

```bash
docker build -t production-test-framework .
```

Optionally pass the git hash as a build arg: `docker build --build-arg GIT_HASH=$(git rev-parse --short HEAD) -t production-test-framework .`

## Running with Docker

### 1. Build and run

Build the image as shown above. To run the container with a minimal setup:

```bash
docker run -it --rm production-test-framework
```

The sections below describe how to set environment variables, enable SSH agent forwarding, and mount your test files and mosaic root so you can run tests inside the container.

### 2. Environment variables for the container

The container uses the same environment variables as the non-Docker setup: **`ANSIBLE_REMOTE_USER`**, **`REMOTE_HOST`**, **`CLUSTER`**, and **`ANSIBLE_INVENTORY_FILE`** are required. Optional variables include **`MOSAIC_ROOT`**, **`TESTS_DIR`**, and **`QASE_TESTOPS_API_TOKEN`** (see [Required Environment Variables](#required-environment-variables) above).

You can provide them by:

- **Mounting a `.env` file** into the container (e.g. `-v $(pwd)/.env:/app/framework/.env:ro`). The Makefile loads `.env` from the framework directory when you run `make`.
- **Passing variables** with `-e VAR=value` or `--env-file` for each run.

If you do not mount a `.env` file, the image uses built-in defaults (see the Dockerfile). Copy [env.example](env.example) to `.env` and edit it for your environment.

### 3. SSH agent forwarding

Ansible inside the container needs to reach your target hosts via SSH. Use SSH agent forwarding so the container can use your host’s keys:

1. On the host, ensure your SSH agent has the key loaded: `ssh-add -l` (use `ssh-add` to add it).
2. When running the container, pass the agent socket in:
   - `-e SSH_AUTH_SOCK=/tmp/ssh-agent/socket`
   - `-v $SSH_AUTH_SOCK:/tmp/ssh-agent/socket`

If SSH connections fail, see [SSH Connection Issues](#ssh-connection-issues) in Troubleshooting.

### 4. Mounting test files and mosaic root

- **Tests:** The framework expects tests at **`TESTS_DIR`**. Inside the container the default is `../tests` (i.e. **`/app/tests`** when the working directory is `/app/framework`). Mount your host tests directory there, e.g. `-v /path/to/your/tests:/app/tests:ro`. Tests are implemented in Python and run with pytest.
- **Mosaic root:** For **`deploy-helm-charts`** and **`undeploy-helm-charts`**, set **`MOSAIC_ROOT`** and mount the mosaic tree so the expected path exists (e.g. `$(MOSAIC_ROOT)/sw/epsw/charts/mosaic`). For example, mount the host mosaic root at `/app/mosaic` and set `MOSAIC_ROOT=/app/mosaic`: `-v /path/to/mosaic:/app/mosaic:ro`.

A full example that combines `.env`, tests, mosaic, and SSH agent forwarding is shown in the code block in the next section; see also [scripts/launch_framework.sh](scripts/launch_framework.sh).

### 5. Executing tests from the container shell

By default, the container starts an interactive shell in `/app/framework`. The entrypoint prints a banner and runs `make help-container-targets` so you can see available targets. Run tests with `make`:

```bash
make test
make test-run-only
make test-deploy-only
```

The Makefile loads `.env` from the framework directory, so a mounted `.env` is used automatically. For a full `docker run` example with env, tests, kubeconfig, and SSH forwarding:

```bash
docker run -it --rm \
  -v $(pwd)/.env:/app/framework/.env:ro \
  -v /path/to/your/tests:/app/tests:ro \
  -e SSH_AUTH_SOCK=/tmp/ssh-agent/socket \
  -v $SSH_AUTH_SOCK:/tmp/ssh-agent/socket \
  production-test-framework
```

Then run `make test` (or another target) inside the container. See [Makefile Targets](#makefile-targets) for all test targets.

### 6. Running a single make target (RUN_MAKE_TARGET)

If you set **`RUN_MAKE_TARGET`**, the entrypoint runs that make target and exits; no interactive shell or banner is shown. Use this for CI or one-off non-interactive runs:

```bash
docker run -it --rm \
  -e RUN_MAKE_TARGET=test-run-only \
  -v $(pwd)/.env:/app/framework/.env:ro \
  -v /path/to/your/tests:/app/tests:ro \
  -e SSH_AUTH_SOCK=/tmp/ssh-agent/socket \
  -v $SSH_AUTH_SOCK:/tmp/ssh-agent/socket \
  production-test-framework
```

Pre-built images are published to Docker Hub via GitHub Actions (see `.github/workflows/` for CI; configure `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` secrets for pushes).

## Troubleshooting

### Prerequisites Not Found

If `make prereqs` shows missing tools:

```bash
# Install missing prerequisites
# For macOS:
brew install kubectl helm

# For Python/uv:
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Ansible is provided by the project's Python dependencies; run `uv sync` from the project root (or use a test target, which syncs dependencies) so that `ansible` is available on your PATH via `uv run`.

### SSH Connection Issues

If SSH connections fail:

1. Ensure your SSH agent has the key loaded: `ssh-add -l` (use `ssh-add` to add it).
2. Test SSH connection manually: `ssh $ANSIBLE_REMOTE_USER@$REMOTE_HOST`
3. Check that `ANSIBLE_REMOTE_USER` and `REMOTE_HOST` are set correctly

### API Tunnel Issues

If the API tunnel fails:

```bash
# Check if tunnel socket exists
ls -la /tmp/api-tunnel.sock

# Manually shutdown tunnel
make stop-ssh-tunnel

# Recreate tunnel
make start-ssh-tunnel
```

### Test Failures

If tests fail:

1. Check cluster status: `kubectl get nodes`
2. Verify pods are running: `kubectl get pods -A`
3. Check Helm chart deployment: `helm list -n mosaic`
4. Review test output for specific error messages

## NCCL Profiler / vLLM (optional)

The `profiler-otel-*` targets and `profiler/docker-compose.yml` are for running the OTEL stack and vLLM with an NCCL profiler. They require an external repository (or compatible layout) and the `MOSAIC_PATH` environment variable for includes and build context. See `profiler/docker-compose.yml` for details.

## Getting Help

For more information:

- Run `make help` from the project root to see all available targets
- Review test documentation in `../tests/lgtm/README.md` if you use the default tests layout
