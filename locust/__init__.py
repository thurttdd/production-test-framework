# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2025 Delos Data, Inc.

"""
Locust load testing utilities.

Locust is a load testing tool that allows testing the performance
of an application under load.
"""

from .locust_user import (
    LocustMetricsUser,
    OtelpMetricConfig,
    LocustTestConfig,
    OtelpConnectionError,
    run_locust_test,
)

__all__ = [
    "LocustMetricsUser",
    "OtelpMetricConfig",
    "LocustTestConfig",
    "OtelpConnectionError",
    "run_locust_test",
]
