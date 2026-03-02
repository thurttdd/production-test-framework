#!/bin/sh
# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2026 Delos Data, Inc.
set -e

GREEN='\033[0;32m'
EC='\033[0m'

# Set the SSH_AUTH_SOCK environment variable to the forwarded ssh socket
export SSH_AUTH_SOCK=/tmp/ssh-agent/socket

# RUN_MAKE_TARGET: when set, run that make target and exit (no banner/help, no shell)
if [ -n "${RUN_MAKE_TARGET}" ]; then
	echo "Running make ${RUN_MAKE_TARGET}..."
	exec make "${RUN_MAKE_TARGET}"
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
echo""
echo "Example: make test"
echo ""

# Launch an interactive shell
exec /bin/sh -i
