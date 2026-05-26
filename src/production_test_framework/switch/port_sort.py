# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2025 Delos Data, Inc.

import re

from production_test_framework.switch.models import Port

_PORT_ID_PATTERN = re.compile(r"^(\D*)(\d*)$")


def port_id_sort_key(port_id: str) -> tuple[str, int]:
    """Sort key for names like swp6 before swp59 (numeric suffix, not lexicographic)."""
    match = _PORT_ID_PATTERN.match(port_id)
    if match is None:
        return (port_id, 0)
    prefix, digits = match.groups()
    return (prefix, int(digits) if digits else 0)


def sort_ports(ports: list[Port]) -> list[Port]:
    return sorted(ports, key=lambda port: port_id_sort_key(port.id))
