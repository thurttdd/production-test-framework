# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2025 Delos Data, Inc.

"""Production test framework for k3s, LGTM stack, and integration testing."""

from importlib.metadata import PackageNotFoundError, version

try:
    from ._version import __version__
except ImportError:
    try:
        __version__ = version("production-test-framework")
    except PackageNotFoundError:
        __version__ = "0.0.0"
