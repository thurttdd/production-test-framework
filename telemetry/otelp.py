# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2025 Delos Data, Inc.

"""
This module provides OTLP (OpenTelemetry Protocol) integration for sending
metrics and logs to an OpenTelemetry collector.

This is the base class for generic OTLP telemetry. For XPT-specific telemetry,
use the XptOtelp class from xpt_otelp.py.

Usage:
    from framework.telemetry import Otelp

    # Create and initialize
    otelp = Otelp("otel_hostname:4317")
    otelp.initialize(
        service_name="my-service",
        service_version="1.0.0",
        friendly_name="user-123",
    )

    # Create metric instruments
    request_counter = otelp.create_counter("bytes_sent", "Total bytes sent")
    latency_histogram = otelp.create_histogram("request_duration", "Request duration in ms")
    active_connections = otelp.create_up_down_counter("active_connections", "Active connections")

    # Record metrics with attributes
    request_counter.add(1024)
    latency_histogram.record(125.5)
    active_connections.add(1)
    active_connections.add(-1)  # connection closed

    # Cleanup when done
    otelp.cleanup()

    # Or use context manager
    with create_otelp("otel_hostname:4317", "my-service", "1.0.0", "user-123") as otelp:
        counter = otelp.create_counter("bytes_sent", "Total bytes sent")
        counter.add(1024)
"""

import logging
import random
import socket
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION


OTLP_GRPC_PORT = 4317
OTLP_CONNECTION_TIMEOUT = 5  # 5 seconds
OTLP_FORCE_FLUSH_TIMEOUT_MS = 10000  # 10 seconds
OTLP_JITTER_FACTOR = 0.3  # 30% jitter
OTLP_FLUSH_WAIT_TIME = 0.1  # 100 milliseconds
OTLP_METRIC_FLUSH_INTERVAL_MS = 5000  # 5 seconds
OTLP_METRIC_FLUSH_TIMEOUT_MS = 20000  # 20 seconds

logger = logging.getLogger(__name__)


@dataclass
class OtelpConfig:
    """Configuration for OTLP service."""

    service_name: str = ""
    service_version: str = "1.0.0"
    friendly_name: str = ""


class Otelp:
    """
    Provides generic OTLP integration for sending metrics to an OpenTelemetry collector.

    This is a base class that can be used directly for non-XPT telemetry.

    Attributes:
        otel_collector_endpoint: The gRPC endpoint of the OTLP collector (e.g., "localhost:4317")
        is_connected: Whether the OTLP collector is reachable
        config: Configuration for the telemetry service
    """

    def __init__(self, otel_collector_endpoint: str):
        """
        Create a new Otelp instance.

        Args:
            otel_collector_endpoint: The gRPC endpoint of the OTLP collector.
                                    Format: "host:port" (e.g., "localhost:4317")
        """
        if not otel_collector_endpoint:
            raise ValueError("otel_collector_endpoint cannot be empty")

        self.otel_collector_endpoint = otel_collector_endpoint
        self.is_connected = False
        self.config = OtelpConfig()

        # OpenTelemetry components
        self._meter_provider: Optional[MeterProvider] = None
        self._meter: Optional[metrics.Meter] = None

        # Store created instruments for reuse
        self._instruments: Dict[str, Any] = {}

    @property
    def meter(self) -> Optional[metrics.Meter]:
        """
        Get the OpenTelemetry Meter for creating custom instruments.

        Returns:
            The Meter instance if initialized, None otherwise.
        """
        return self._meter

    def initialize(
        self,
        service_name: str,
        service_version: str,
        friendly_name: str,
    ) -> None:
        """
        Initialize the OTLP service.

        This tests connectivity to the OTLP collector and sets up the meter provider.

        Args:
            service_name: The name of the service (e.g., "my-service")
            service_version: The version of the service
            friendly_name: A human-readable name
        """
        self.config = OtelpConfig(
            service_name=service_name,
            service_version=service_version,
            friendly_name=friendly_name,
        )

        logger.info(
            "Initializing OTLP service: %s Version: %s FriendlyName: %s EndPoint: %s",
            service_name,
            service_version,
            friendly_name,
            self.otel_collector_endpoint,
        )

        # Test OTLP connectivity
        self.is_connected = self._test_otlp_connectivity()
        logger.info(f"OTLP connectivity test result: {self.is_connected}")

        if not self.is_connected:
            logger.error("OTLP service is not available, using local-only mode")
            return

        # Initialize OTLP meter provider
        try:
            self._init_meter_provider()
            logger.info("OTLP meter provider initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize OTLP meter provider: %s", e)
            self.is_connected = False
            return

    def _test_otlp_connectivity(self) -> bool:
        """
        Test if the OTLP endpoint is reachable via TCP.

        Args:
        Returns:
            True if the endpoint is reachable, False otherwise
        """
        logger.info(f"Testing OTLP connectivity to: {self.otel_collector_endpoint}")

        # Parse host and port
        try:
            if "://" in self.otel_collector_endpoint:
                # Strip protocol prefix if present
                addr = self.otel_collector_endpoint.split("://", 1)[1]
            else:
                addr = self.otel_collector_endpoint

            if ":" in addr:
                host, port_str = addr.rsplit(":", 1)
                port = int(port_str)
            else:
                host = addr
                port = OTLP_GRPC_PORT  # Default OTLP gRPC port
        except ValueError as e:
            logger.error(f"Invalid endpoint format: {e}")
            return False

        # Test TCP connectivity
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(OTLP_CONNECTION_TIMEOUT)
            result = sock.connect_ex((host, port))
            sock.close()

            if result == 0:
                logger.info(f"Successfully connected to OTLP endpoint: {self.otel_collector_endpoint}")
                return True
            else:
                logger.error(
                    f"Failed to connect to OTLP endpoint: {self.otel_collector_endpoint} (error code: {result})"
                )
                return False
        except socket.error as e:
            logger.error(f"Socket error connecting to OTLP endpoint: {self.otel_collector_endpoint} - {e}")
            return False

    def _init_meter_provider(self) -> None:
        """Initialize OpenTelemetry meter provider with OTLP exporter."""
        # Create resource with service info
        resource = Resource.create(
            {
                SERVICE_NAME: self.config.service_name,
                SERVICE_VERSION: self.config.service_version,
                "otelp.friendly_name": self.config.friendly_name,
            }
        )

        # Create OTLP metric exporter
        exporter = OTLPMetricExporter(
            endpoint=self.otel_collector_endpoint,
            insecure=True,
        )

        # Add jitter to stagger exports (±30% of interval)
        base_interval = OTLP_METRIC_FLUSH_INTERVAL_MS
        jitter = random.random() * OTLP_JITTER_FACTOR * base_interval
        actual_interval = base_interval + jitter - (jitter / 2)

        # Create periodic reader
        reader = PeriodicExportingMetricReader(
            exporter,
            export_interval_millis=int(actual_interval),
            export_timeout_millis=OTLP_METRIC_FLUSH_TIMEOUT_MS,
        )

        # Create and set meter provider
        self._meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[reader],
        )
        metrics.set_meter_provider(self._meter_provider)

        # Create meter
        self._meter = self._meter_provider.get_meter(self.config.friendly_name)

        logger.info(f"Meter provider initialized with meter: {self.config.friendly_name}")

    # =========================================================================
    # Metric Instrument Creation Methods
    # =========================================================================

    def create_counter(
        self,
        name: str,
        description: str = "",
        unit: str = "",
    ) -> metrics.Counter:
        """
        Create a Counter instrument for monotonically increasing values.

        Counters are used for values that only go up, like request counts,
        bytes sent, or tasks completed.

        Args:
            name: The metric name (e.g., "total bytes sent")
            description: Human-readable description
            unit: Unit of measurement (e.g., "bytes")

        Returns:
            A Counter instrument

        Raises:
            RuntimeError: If not connected or meter not initialized

        Example:
            counter = otelp.create_counter("total_bytes_sent", "Total bytes sent")
            counter.add(1024)
        """
        self._check_initialized()

        if name in self._instruments:
            return self._instruments[name]

        counter = self._meter.create_counter(
            name=name,
            description=description,
            unit=unit,
        )
        self._instruments[name] = counter
        logger.info(f"Created counter: {name}")
        return counter

    def create_up_down_counter(
        self,
        name: str,
        description: str = "",
        unit: str = "",
    ) -> metrics.UpDownCounter:
        """
        Create an UpDownCounter instrument for values that can increase or decrease.

        UpDownCounters are used for values like active connections, queue size,
        or any metric that can go both up and down.

        Args:
            name: The metric name (e.g., "active_connections")
            description: Human-readable description
            unit: Unit of measurement

        Returns:
            An UpDownCounter instrument

        Raises:
            RuntimeError: If not connected or meter not initialized

        Example:
            connections = otelp.create_up_down_counter("active_connections", "Active connections")
            connections.add(1)   # Connection opened
            connections.add(-1)  # Connection closed
        """
        self._check_initialized()

        if name in self._instruments:
            return self._instruments[name]

        counter = self._meter.create_up_down_counter(
            name=name,
            description=description,
            unit=unit,
        )
        self._instruments[name] = counter
        logger.info(f"Created up_down_counter: {name}")
        return counter

    def create_histogram(
        self,
        name: str,
        description: str = "",
        unit: str = "",
    ) -> metrics.Histogram:
        """
        Create a Histogram instrument for recording distributions of values.

        Histograms are used for latencies, request sizes, or any metric where
        you want to understand the distribution (percentiles, average, etc.).

        Args:
            name: The metric name (e.g., "request_duration")
            description: Human-readable description
            unit: Unit of measurement (e.g., "ms", "bytes")

        Returns:
            A Histogram instrument

        Raises:
            RuntimeError: If not connected or meter not initialized

        Example:
            latency = otelp.create_histogram("http.latency", "Request latency", "ms")
            latency.record(125.5, {"method": "GET", "path": "/api/users"})
        """
        self._check_initialized()

        if name in self._instruments:
            return self._instruments[name]

        histogram = self._meter.create_histogram(
            name=name,
            description=description,
            unit=unit,
        )
        self._instruments[name] = histogram
        logger.info(f"Created histogram: {name}")
        return histogram

    def create_observable_gauge(
        self,
        name: str,
        callbacks: Sequence[Callable],
        description: str = "",
        unit: str = "",
    ) -> metrics.ObservableGauge:
        """
        Create an ObservableGauge for values that are sampled at collection time.

        ObservableGauges are callback-based and are read when metrics are collected.
        Use for values like CPU usage, memory usage, or temperature.

        Args:
            name: The metric name (e.g., "gpu_usage")
            callbacks: Sequence of callback functions that return observations
            description: Human-readable description
            unit: Unit of measurement (e.g., "percent")

        Returns:
            An ObservableGauge instrument

        Raises:
            RuntimeError: If not connected or meter not initialized

        Example:
            def get_cpu_usage(options):
                yield metrics.Observation(75.5, {"core": "0"})
                yield metrics.Observation(82.3, {"core": "1"})

            cpu_gauge = otelp.create_observable_gauge(
                "system.cpu.usage",
                [get_cpu_usage],
                "CPU usage percentage",
                "percent"
            )
        """
        self._check_initialized()

        if name in self._instruments:
            return self._instruments[name]

        gauge = self._meter.create_observable_gauge(
            name=name,
            callbacks=callbacks,
            description=description,
            unit=unit,
        )
        self._instruments[name] = gauge
        logger.info(f"Created observable_gauge: {name}")
        return gauge

    def create_observable_counter(
        self,
        name: str,
        callbacks: Sequence[Callable],
        description: str = "",
        unit: str = "",
    ) -> metrics.ObservableCounter:
        """
        Create an ObservableCounter for monotonic values sampled at collection time.

        ObservableCounters are callback-based and report cumulative values.
        Use when you can only read the total value, not increments.

        Args:
            name: The metric name
            callbacks: Sequence of callback functions that return observations
            description: Human-readable description
            unit: Unit of measurement

        Returns:
            An ObservableCounter instrument

        Raises:
            RuntimeError: If not connected or meter not initialized
        """
        self._check_initialized()

        if name in self._instruments:
            return self._instruments[name]

        counter = self._meter.create_observable_counter(
            name=name,
            callbacks=callbacks,
            description=description,
            unit=unit,
        )
        self._instruments[name] = counter
        logger.info(f"Created observable_counter: {name}")
        return counter

    def create_observable_up_down_counter(
        self,
        name: str,
        callbacks: Sequence[Callable],
        description: str = "",
        unit: str = "",
    ) -> metrics.ObservableUpDownCounter:
        """
        Create an ObservableUpDownCounter for values sampled at collection time.

        Similar to ObservableGauge but specifically for additive values that
        can increase or decrease.

        Args:
            name: The metric name
            callbacks: Sequence of callback functions that return observations
            description: Human-readable description
            unit: Unit of measurement

        Returns:
            An ObservableUpDownCounter instrument

        Raises:
            RuntimeError: If not connected or meter not initialized
        """
        self._check_initialized()

        if name in self._instruments:
            return self._instruments[name]

        counter = self._meter.create_observable_up_down_counter(
            name=name,
            callbacks=callbacks,
            description=description,
            unit=unit,
        )
        self._instruments[name] = counter
        logger.info("Created observable_up_down_counter: %s", name)
        return counter

    def get_instrument(self, name: str) -> Optional[Any]:
        """
        Get a previously created instrument by name.

        Args:
            name: The metric name

        Returns:
            The instrument if found, None otherwise
        """
        return self._instruments.get(name)

    def _check_initialized(self) -> None:
        """Check that the meter is initialized and raise if not."""
        if not self.is_connected:
            raise RuntimeError("OTLP not connected")
        if self._meter is None:
            raise RuntimeError("Meter not initialized")

    # =========================================================================
    # Lifecycle Methods
    # =========================================================================

    def cleanup(self) -> None:
        """
        Clean up OTLP resources.

        This flushes any remaining metrics and shuts down the meter provider.
        Should be called when done with telemetry operations.
        """
        logger.info("Cleaning up OTLP module")

        # Clear instruments
        self._instruments.clear()

        # Force flush remaining metrics
        if self._meter_provider is not None:
            logger.info("Flushing metrics before shutdown")
            try:
                self._meter_provider.force_flush(timeout_millis=OTLP_FORCE_FLUSH_TIMEOUT_MS)
                logger.info("Successfully flushed all metrics")
            except Exception as e:
                logger.error("Failed to flush metrics: %s", e)

        # Small buffer for flush to complete
        time.sleep(OTLP_FLUSH_WAIT_TIME)

        # Shutdown meter provider
        if self._meter_provider is not None:
            logger.info("Shutting down OpenTelemetry providers...")
            try:
                self._meter_provider.shutdown()
                logger.info("OpenTelemetry providers shut down successfully")
            except Exception as e:
                logger.error("Failed to shutdown meter provider: %s", e)

        self.is_connected = False

    def get_connection_status(self) -> bool:
        """Return the current connection status."""
        return self.is_connected

    def __enter__(self) -> "Otelp":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - automatically cleanup."""
        self.cleanup()


@contextmanager
def create_otelp(
    endpoint: str,
    service_name: str,
    service_version: str,
    friendly_name: str,
):
    """
    Context manager for creating and initializing an Otelp instance.

    Usage:
        with create_otelp("localhost:4317", "my-service", "1.0.0", "my-service-1", "user-123") as otelp:
            counter = otelp.create_counter("ingest_counter", "Ingest test tick counter")
            counter.add(1)

    Args:
        endpoint: The OTLP collector endpoint
        service_name: The service name
        service_version: The service version
        friendly_name: Human-readable name

    Yields:
        Initialized Otelp instance
    """
    otelp = Otelp(endpoint)
    otelp.initialize(
        service_name=service_name,
        service_version=service_version,
        friendly_name=friendly_name,
    )
    try:
        yield otelp
    finally:
        otelp.cleanup()
