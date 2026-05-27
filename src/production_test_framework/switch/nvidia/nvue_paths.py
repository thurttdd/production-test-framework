# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2025 Delos Data, Inc.

"""Composable NVUE URL path segments (Cumulus Linux 5.12 OpenAPI)."""

BRIDGE_DOMAIN = "br_default"

SYSTEM_PATH = "/system"
PLATFORM_PATH = "/platform"
FIRMWARE_PATH = "/platform/firmware"
INTERFACES_PATH = "/interface"

BRIDGE_DOMAIN_PATH = f"/bridge/domain/{BRIDGE_DOMAIN}"
BRIDGE_DOMAIN_VLANS_PATH = f"{BRIDGE_DOMAIN_PATH}/vlan"


def interface_path(interface_id: str) -> str:
    return f"{INTERFACES_PATH}/{interface_id}"


def bridge_domain_vlan_path(vlan_id: str) -> str:
    return f"{BRIDGE_DOMAIN_VLANS_PATH}/{vlan_id}"
