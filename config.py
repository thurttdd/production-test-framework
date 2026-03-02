# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2026 Delos Data, Inc.

"""
Configuration management for LGTM stack tests.

Loads configuration from environment variables with defaults.
"""

import os
from dataclasses import dataclass, field


@dataclass
class LGTMConfig:
    """Configuration for LGTM stack deployment and testing."""

    # Target host configuration
    host: str = field(default_factory=lambda: os.getenv("REMOTE_HOST", "espresso-1"))

    # SSH/Ansible configuration
    ansible_remote_user: str = field(default_factory=lambda: os.getenv("ANSIBLE_REMOTE_USER", ""))

    grafana_port: int = 3000
    mimir_port: int = 9009
    otlp_grpc_port: int = 4317
    otlp_http_port: int = 4318

    def validate_ssh_config(self) -> bool:
        """Check if SSH configuration is complete."""
        return bool(self.ansible_remote_user)

    @classmethod
    def from_env(cls) -> "LGTMConfig":
        """Create configuration from environment variables."""
        return cls()
