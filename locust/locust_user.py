# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2026 Delos Data, Inc.

"""
Locust User class for sending telemetry metrics to an OTEL endpoint.
"""

from dataclasses import dataclass
from typing import Type

import gevent

from locust import User, events, task, between
from locust.env import Environment
from locust.stats import stats_history, stats_printer

from ..telemetry import Otelp


# =============================================================================
# Exceptions
# =============================================================================


class OtelpConnectionError(RuntimeError):
    """Raised when connection to OTLP endpoint fails."""

    pass


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class OtelpMetricConfig:
    """Configuration for LocustMetricsUser."""

    otlp_endpoint: str
    service_name: str
    service_version: str
    metric_name: str


@dataclass
class LocustTestConfig:
    """
    Configuration for a Locust test run.

    Each test module should define a fixture that returns this config
    with its specific settings.
    """

    user_class: Type["LocustMetricsUser"]
    num_users: int
    spawn_rate: int
    duration_seconds: int


# =============================================================================
# Locust Metrics User Class
# =============================================================================


class LocustMetricsUser(User):
    """
    Locust Metrics User that sends telemetry metrics to the OTEL endpoint.

    Set the class attribute `config` with an OtelpMetricConfig instance.

    Example:
        class MyMetricsUser(LocustMetricsUser):
            config = OtelpMetricConfig(
                otlp_endpoint="espresso-1:30317",
                service_name="my-service",
                service_version="1.0.0",
                metric_name="my_counter",
            )
    """

    config: OtelpMetricConfig = None
    user_counter = 0
    wait_time = between(1, 3)

    def on_start(self):
        """Called when a user starts. Initialize the Otelp instance."""
        if self.config is None:
            raise ValueError("LocustMetricsUser.config must be set before running")

        LocustMetricsUser.user_counter += 1
        self.user_id = LocustMetricsUser.user_counter
        self.friendly_name = f"epi-{self.user_id}"

        self.otelp = Otelp(self.config.otlp_endpoint)
        self.otelp.initialize(
            service_name=self.config.service_name,
            service_version=self.config.service_version,
            friendly_name=self.friendly_name,
        )

        if not self.otelp.is_connected:
            raise OtelpConnectionError(
                f"{self.friendly_name} could not connect to OTLP endpoint {self.config.otlp_endpoint}"
            )

        # Create the metrics counter
        self.counter = self.otelp.create_counter(
            self.config.metric_name,
            description="Bytes sent",
        )

    def on_stop(self):
        """Called when a user stops. Clean up the Otelp instance."""
        if hasattr(self, "otelp") and self.otelp is not None:
            self.otelp.cleanup()
            self.otelp = None

    @task
    def record_metrics(self):
        """Record metrics for this user."""
        if self.otelp is not None and self.otelp.is_connected:
            self.counter.add(
                1,
                {
                    "name": self.friendly_name,
                },
            )


# =============================================================================
# Locust Test Runner
# =============================================================================


def run_locust_test(
    user_class: Type[User],
    num_users: int,
    spawn_rate: int,
    duration_seconds: int,
) -> None:
    """
    Run a Locust test.

    Args:
        user_class: The Locust User class to use
        num_users: Number of concurrent users to spawn
        spawn_rate: Rate at which to spawn users (users/second)
        duration_seconds: How long to run the test
    """

    env = Environment(user_classes=[user_class], events=events)
    runner = env.create_local_runner()

    env.events.init.fire(environment=env, runner=runner)

    gevent.spawn(stats_printer(env.stats))
    gevent.spawn(stats_history, env.runner)

    runner.start(num_users, spawn_rate=spawn_rate)

    gevent.spawn_later(duration_seconds, runner.quit)
    runner.greenlet.join()
