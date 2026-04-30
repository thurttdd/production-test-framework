# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2025 Delos Data, Inc.

"""Shared pytest fixtures for unit tests."""

import sys
import types
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _add_production_test_framework_to_sys_path():
    pkg = types.ModuleType("production_test_framework")
    pkg.__path__ = [str(_REPO_ROOT)]
    pkg.__package__ = "production_test_framework"
    sys.modules["production_test_framework"] = pkg


_add_production_test_framework_to_sys_path()


from config import LGTMConfig


@pytest.fixture
def lgtm_config():
    """LGTMConfig with test values (no real SSH)."""
    return LGTMConfig(
        host="test-host.example.com",
        ansible_remote_user="testuser",
    )
