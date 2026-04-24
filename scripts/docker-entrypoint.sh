#!/bin/sh
# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2025 Delos Data, Inc.
set -e

GREEN='\033[0;32m'
EC='\033[0m'


# Set the PYTHONPATH environment variable to the overlay
export PYTHONPATH=/app/framework/tests

# Set the SSH_AUTH_SOCK environment variable to the forwarded ssh socket
export SSH_AUTH_SOCK=/tmp/ssh-agent/socket

# if there's an ssh socket mounted, use the host group id for the appuser
if [ -S /tmp/ssh-agent/socket ]; then
	sudo groupadd -g `stat -c '%g' /tmp/ssh-agent/socket` ssh-agent-host
	sudo usermod -aG ssh-agent-host appuser
fi

# if there's a docker socket mounted, use the host group id for the appuser
if [ -S /var/run/docker.sock ]; then
	sudo groupadd -g `stat -c '%g' /var/run/docker.sock` docker-host
	sudo usermod -aG docker-host appuser
fi

# copy tests to the framework tests directory
cp -r /app/tests/* /app/framework/tests/

# if helm charts are mounted, copy them to the framework charts directory
if [ -d /app/charts ]; then
	cp -r /app/charts/* /app/framework/charts/
fi

# Make sure all python dependencies are installed
uv sync --all-packages

# RUN_MAKE_TARGET: when set, run that make target and exit (no banner/help, no shell)
if [ -n "${RUN_MAKE_TARGET}" ]; then
	echo "Running make ${RUN_MAKE_TARGET}..."
	if [ -S /var/run/docker.sock ]; then
		# Switch to the new docker-host group to run the make target
		exec sg docker-host -c "make ${RUN_MAKE_TARGET}"
	else
		exec make "${RUN_MAKE_TARGET}"
	fi
fi

# Display the container banner
echo -e ""
echo -e "${GREEN}Production Test Framework"
echo -e "-------------------------${EC}"
echo -e ""

# Show the top level makefile target help
make help-container-targets

echo ""
echo "To run tests, run make using one of the targets shown above."
echo ""
echo "Example: make test"
echo ""

# Launch an interactive shell
exec /bin/sh -i
