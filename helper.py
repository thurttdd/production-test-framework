# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2026 Delos Data, Inc.

"""
Helper functions for testing.

Provides reusable utilities for testing.
"""

import socket
import time
import requests


def check_tcp_connectivity(host: str, port: int, timeout: float = 5.0) -> bool:
    """
    Test TCP connectivity to a host:port.

    Args:
        host: Target hostname or IP
        port: Target port
        timeout: Connection timeout in seconds

    Returns:
        True if connection successful, False otherwise
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except socket.error:
        return False


def wait_for_tcp_connectivity(host: str, port: int, timeout: float = 30) -> bool:
    """Wait for TCP connectivity to a host:port."""
    poll_interval = 0.5
    for i in range(int(timeout / poll_interval)):
        if i % 10 == 0:
            print(f"Waiting for TCP connectivity to {host}:{port}... {i}s")
        if check_tcp_connectivity(host, port):
            return True
        time.sleep(poll_interval)
    return False


def get_mimir_base_url(mimir_port: int) -> str:
    """Get the base URL for Mimir Prometheus API."""
    return f"http://localhost:{mimir_port}/prometheus"


def query_mimir(mimir_port: int, endpoint: str, params: dict = None, timeout: int = 10) -> requests.Response:
    """
    Query Mimir Prometheus API.

    Args:
        mimir_port: Local port where Mimir is accessible
        endpoint: API endpoint (e.g., "/api/v1/query")
        params: Optional query parameters
        timeout: Request timeout in seconds

    Returns:
        requests.Response object
    """
    base_url = get_mimir_base_url(mimir_port)
    url = f"{base_url}{endpoint}"
    return requests.get(url, params=params, timeout=timeout)
