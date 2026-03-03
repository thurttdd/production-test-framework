#!/bin/sh
# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2025 Delos Data, Inc.

# The docker image to use
IMAGE=production-test-framework:latest

# The directory where the pytest tests are located
TESTS_DIR=../tests

# The directory where the mosaic root is located
HELM_CHARTS_DIR=$HOME/projects/mosaic/sw/epsw/charts

# The directory where the nccl profiler plugin is located
NCCL_PROFILER_PLUGIN_DIR=$HOME/projects/mosaic/sw/epsw/nccl_profiler_plugin

# The environment file to use. This is used to set the environment variables for the framework.
ENV_FILE=.env.docker

# The DNS search domain. This command will parseout the local tailscale domain from the resolv.conf file,
# but this can be replaced with a static search domain if needed.
DNS_SEARCH=`sed -n '/^search/s/^search[[:space:]]*//p' /etc/resolv.conf | grep -owiE '[a-z0-9.]*ts.net'`

# The name of the container to create
CONTAINER_NAME=production-test-framework

docker run -v $TESTS_DIR:/app/tests \
-v $SSH_AUTH_SOCK:/tmp/ssh-agent/socket \
-v $HELM_CHARTS_DIR:/app/mosaic/sw/epsw/charts  \
-v $NCCL_PROFILER_PLUGIN_DIR:/app/mosaic/profiler_plugin  \
-v /var/run/docker.sock:/var/run/docker.sock \
--network host \
--dns-search $DNS_SEARCH \
--env-file $ENV_FILE \
-it \
--rm \
--name $CONTAINER_NAME \
$IMAGE
