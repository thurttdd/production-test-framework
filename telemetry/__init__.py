# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2026 Delos Data, Inc.
# Telemetry module for initializing and sending metrics to an OpenTelemetry collector
#
# Usage:
#     # Generic OTLP client
#     from framework.telemetry import Otelp, create_otelp
#
#     with create_otelp("my-endpoint", "my-service", "1.0.0", "user-123") as otelp:
#         counter = otelp.create_counter("bytes_sent", "Total bytes sent")
#         counter.add(1024)
#
from .otelp import Otelp, OtelpConfig, create_otelp

__all__ = [
    # Generic OTLP client
    "Otelp",
    "OtelpConfig",
    "create_otelp",
]
