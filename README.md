# Production Test Framework

The Production Test Framework provides automated infrastructure for deploying, validating, and testing production platform components. This framework automates cluster setup, service deployment, and execution of integration tests.

## Overview

The framework enables end-to-end testing of the following areas:

- **K3s Cluster Management**: Automated bootstrap and validation of k3s clusters
- **LGTM Stack Deployment**: Automated deployment of Loki, Grafana, Tempo, and Mimir
- **Integration Testing**: Automated test execution with proper setup and teardown
- **Infrastructure Automation**: SSH tunnels, kubeconfig management, and dependency synchronization

## Quick Start

To get tests running with a single command: clone the repo, copy and edit `.env` to set the required and optional environment variables:

```bash
git clone <repo-url> production-test-framework
cd production-test-framework
cp env.example .env
# Edit .env: CLUSTER, and the other fields checked by `make prereqs`
uv sync
make test
```

The sections below cover prerequisites, cluster access, the other [Makefile targets](#makefile-targets), and [running in Docker](#running-with-docker).

## Prerequisites

Before using the framework, ensure you have the following installed:

- `kubectl` - Kubernetes command-line tool
- `helm` - Kubernetes package manager
- `uv` - Python package manager
- **k3d** and **sudo** (only for `test-production`, `create-test-cluster`, and `destroy-test-cluster`, which create/deletes a local k3d cluster)

### Required Environment Variables

The framework requires the following environment variables to be set:

```bash
export ANSIBLE_REMOTE_USER="your-ssh-username"
export REMOTE_HOST="target-cluster-hostname-or-ip"
export CLUSTER="cluster-name"
export ANSIBLE_INVENTORY_FILE="/path/to/ansible/inventory.ini"
```

For Qase test reporting, set **`QASE_TESTOPS_API_TOKEN`** (optional). If unset, `make prereqs` will report it as missing but tests can still run.

You can also create a `.env` file in the project root with the variables above specified. Copy `env.example` to `.env` and edit the values. The `.env` file will be loaded when make is run.

## Quick Start

### 1. Clone and set up

Clone this repository, then create your local configuration:

```bash
git clone <repo-url> production-test-framework
cd production-test-framework
cp env.example .env
# Edit .env (and add ansible/inventory.ini if you use Ansible outside this Makefile)
uv sync
```

### 2. Check Prerequisites

Verify all prerequisites are installed and environment variables are set:

```bash
make prereqs
```

### 3. Run tests

```bash
# Full flow: deploy Helm charts -> run tests -> undeploy
make test

# No deploy/undeploy: run the main suite (marker "not teardown")
make test-run-only

# k3d lifecycle: create cluster -> deploy -> run-tests -> destroy cluster
make test-production

# Same as `make run-tests` with Open Mosaic specific setup and test markers
make test-openmosaic
```

Run `make help` for the full list, or `make help-container-targets` in the [Docker image](#running-with-docker).

## Makefile Targets

### Infrastructure management

- **`prereqs`** - Check for missing prerequisites and environment variables
- **`deploy-helm-charts`** - Deploy charts (expects `kubectl` context configured; uses `CLUSTER` in messages)
- **`undeploy-helm-charts`** - Remove the `mosaic` namespace / release

### Setting up a test cluster using k3d and k3s

- **`create-test-cluster`** - Create a k3d cluster named `${CI_JOB_ID}-k3s` and a `mosaic` namespace
- **`destroy-test-cluster`** - Delete that k3d cluster

### Building blocks

- **`run-tests`** - Run pytest once with `TEST_MARKER` (no Helm undeploy, no separate teardown pass)
- **`run-all-tests`** - `run-tests`, then `undeploy-helm-charts`, then pytest with the `teardown` marker
- **`help`** / **`help-container-targets`** - Print help (the latter is a short list for container/CI use)

### Top-level tests

- **`test`** - `prereqs` → `deploy-helm-charts` → `run-all-tests` (main tests, undeploy, teardown tests)
- **`test-run-only`** - `prereqs` and a `run-tests` with marker `not teardown` (no deploy/undeploy)
- **`test-production`** - `create-test-cluster` → `deploy-helm-charts` → `run-tests` → `destroy-test-cluster`
- **`test-openmosaic`** - Same as `run-tests` (convenience target for an already-running stack)

### Test options

- **`TEST_MARKER`** - Pytest marker (default: `k3s or lgtm or metrics`). `test-run-only` forces `not teardown` in the Makefile; set `TEST_MARKER` for other targets as needed.
- **`PYTEST_ADDOPTS`** - Extra pytest options (pytest reads this environment variable).
- **`QASE_TESTOPS_RUN_TITLE`** - Qase automated test run title. Default: "Production test run <commit-hash> [dirty]". Override for CI or custom runs.
- **`CI_JOB_ID`** - Used in the k3d cluster name (default `local`); set in CI to avoid collisions.

```bash
make test-run-only PYTEST_ADDOPTS='-x'
make test QASE_TESTOPS_RUN_TITLE="CI run 123"
```

## Test Structure

By default, tests are expected in `./tests/lgtm/` (a child directory). Set `TESTS_DIR` if your tests live elsewhere. Tests are organized by validation area:

- **`test_k3s_cluster.py`** - K3s cluster health and node validation
- **`test_namespaces.py`** - Namespace and pod validation
- **`test_services.py`** - Service and storage validation
- **`test_teardown.py`** - Post-teardown validation

Tests use pytest markers for organization:
- `k3s` - K3s cluster validation tests
- `lgtm` - LGTM stack integration tests
- `metrics` - Metrics-related tests (when present)
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

The sections below describe how to set environment variables, optionally forward SSH, and mount your tests and Helm charts so you can run `make` inside the container.

### 2. Environment variables for the container

The required environment variables for cluster validation are: **`ANSIBLE_REMOTE_USER`**, **`REMOTE_HOST`**, **`CLUSTER`**, and **`ANSIBLE_INVENTORY_FILE`**. Optional variables include **`TESTS_DIR`**, and **`QASE_TESTOPS_API_TOKEN`** (see [Required Environment Variables](#required-environment-variables) above).

You can provide them by:

- **Mounting a `.env` file** into the container (e.g. `-v $(pwd)/.env:/app/framework/.env:ro`). The Makefile loads `.env` from the framework directory when you run `make`.
- **Passing variables** with `-e VAR=value` or `--env-file` for each run.

If you do not mount a `.env` file, the image uses built-in defaults (see the Dockerfile). Copy [env.example](env.example) to `.env` and edit it for your environment.

### 3. SSH agent forwarding (optional)

If you run Ansible or other tools that SSH from the container, forward your agent so keys are available:

1. On the host, ensure your SSH agent has the key loaded: `ssh-add -l` (use `ssh-add` to add it).
2. When running the container, pass the agent socket in:
   - `-e SSH_AUTH_SOCK=/tmp/ssh-agent/socket`
   - `-v $SSH_AUTH_SOCK:/tmp/ssh-agent/socket`

If SSH connections fail, see [SSH Connection Issues](#ssh-connection-issues) in Troubleshooting.

### 4. Mounting test files and mosaic Helm charts

- **Tests:** The Makefile uses **`/app/framework/tests`** (see `TESTS_DIR`). The [docker entrypoint](scripts/docker-entrypoint.sh) copies **`/app/tests/*`** into `/app/framework/tests/`, so a typical mount is `-v /path/to/your/tests:/app/tests:ro`. You can also mount straight to `/app/framework/tests` if you do not rely on that copy. Tests are Python and run with pytest.
- **Helm charts:** The Makefile runs Helm from `/app/framework/charts/mosaic` (see `deploy-helm-charts`). You can mount that path directly, e.g. `-v /path/to/mosaic/charts/mosaic:/app/framework/charts/mosaic:ro`. Alternatively, mount your charts under **`/app/charts`**; [scripts/docker-entrypoint.sh](scripts/docker-entrypoint.sh) copies `/app/charts/*` into `/app/framework/charts/` at container start.

A full example that combines `.env`, tests, mosaic, and SSH agent forwarding is shown in the code block in the next section; see also [scripts/launch_framework.sh](scripts/launch_framework.sh).

### 5. Executing tests from the container shell

By default, the container starts an interactive shell in `/app/framework`. The entrypoint prints a banner and runs `make help-container-targets` so you can see available targets. Run tests with `make`:

```bash
make test
make test-run-only
make test-production
make test-openmosaic
```

The Makefile loads `.env` from the framework directory, so a mounted `.env` is used automatically. For a full `docker run` example with env, tests, Helm charts, and optional SSH forwarding:

```bash
docker run -it --rm \
  -v $(pwd)/.env:/app/framework/.env:ro \
  -v /path/to/your/tests:/app/tests:ro \
  -v /path/to/helm/charts/mosaic:/app/framework/charts/mosaic:ro \
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
  -v /path/to/helm/charts/mosaic:/app/framework/charts/mosaic:ro \
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

Ansible is provided by the project's Python dependencies; run `uv sync` from the project root so that `ansible` is available on your PATH via `uv run` when you need it.

### SSH Connection Issues

If SSH connections fail:

1. Ensure your SSH agent has the key loaded: `ssh-add -l` (use `ssh-add` to add it).
2. Test SSH connection manually: `ssh $ANSIBLE_REMOTE_USER@$REMOTE_HOST`
3. Check that `ANSIBLE_REMOTE_USER` and `REMOTE_HOST` are set correctly

### Test Failures

If tests fail:

1. Check cluster status: `kubectl get nodes`
2. Verify pods are running: `kubectl get pods -A`
3. Check Helm chart deployment: `helm list -n mosaic`
4. Review test output for specific error messages


## Versioning and releases

The Python package version is derived from **git tags**, not a static value in `pyproject.toml`. Push an annotated or lightweight tag with a `v` prefix and a [PEP 440](https://peps.python.org/pep-0440/) version:

```bash
git tag v0.2.0
git push origin v0.2.0
```

- **Released builds** (on tag `v*`) use that version (for example `0.2.0` from tag `v0.2.0`).
- **Development builds** (commits after the latest tag) get a dev suffix such as `0.2.0.dev3+gabc1234`.
- **Docker images** on tag push are tagged with the same `v*` name; the image build sets the package version from the tag.

To build or install locally without a tag, either create a tag or set a pretend version:

```bash
export SETUPTOOLS_SCM_PRETEND_VERSION=0.2.0.dev
uv sync
```

## Getting Help

For more information:

- Run `make help` from the project root to see all available targets
- Review test documentation in `../tests/lgtm/README.md` if you use the default tests layout
