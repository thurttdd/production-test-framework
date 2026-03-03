# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2025 Delos Data, Inc.

"""
vLLM inference client for testing.

Provides a reusable client for vLLM inference.
"""

import time
from dataclasses import dataclass, field
from typing import Optional, Dict

import requests


DEFAULT_MODEL = "Qwen/Qwen3-8B"


@dataclass
class VllmConfig:
    """Configuration for vLLM client."""

    host: str = "localhost"
    port: int = 8080
    timeout: int = 600  # Longer timeout for inference
    health_timeout: int = 10

    @property
    def base_url(self) -> str:
        """Get the base URL for vLLM API."""
        return f"http://{self.host}:{self.port}"

    @classmethod
    def from_env(cls, host: str = "localhost", port: int = 8080) -> "VllmConfig":
        """Create configuration with specified host and port."""
        return cls(host=host, port=port)


@dataclass
class InferenceResult:
    """Result of an inference request."""

    success: bool
    text: str = ""
    model: str = ""
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: str = ""
    error: Optional[str] = None
    response_time: float = 0.0


class VllmClient:
    """
    Client for vLLM inference.

    Provides methods for health check and inference.
    """

    def __init__(self, config: Optional[VllmConfig] = None):
        """
        Initialize vLLM client.

        Args:
            config: VllmConfig instance. If None, uses defaults.
        """
        self.config = config or VllmConfig()

    @property
    def base_url(self) -> str:
        """Get the base URL for vLLM API."""
        return self.config.base_url

    def health_check(self) -> bool:
        """
        Check if vLLM server is healthy.

        Returns:
            True if server is healthy, False otherwise.
        """
        try:
            response = requests.get(f"{self.base_url}/health", timeout=self.config.health_timeout)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def wait_for_ready(self, timeout: float, poll_interval: float = 5) -> bool:
        """
        Wait for vLLM server to be ready.

        Args:
            timeout: Maximum time to wait in seconds
            poll_interval: Time between health checks in seconds

        Returns:
            True if server becomes ready, False if timeout exceeded.
        """
        start_time = time.time()
        attempt = 0

        while time.time() - start_time < timeout:
            attempt += 1
            if self.health_check():
                elapsed = time.time() - start_time
                print(f"\n  vLLM server ready after {elapsed:.1f}s")
                return True

            if attempt % 3 == 0:  # Log every ~15 seconds
                elapsed = time.time() - start_time
                print(f"  Waiting for vLLM server to be ready... {elapsed:.0f}s elapsed")

            time.sleep(poll_interval)

        return False

    def complete(
        self,
        prompt: str,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 100,
        temperature: float = 0.9,
    ) -> InferenceResult:
        """
        Generate text completion.

        Args:
            prompt: Input prompt text
            model: Model name (default: DEFAULT_MODEL)
            max_tokens: Maximum tokens to generate (default: 100)
            temperature: Sampling temperature (default: 0.9)

        Returns:
            InferenceResult with generated text and metadata.
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        start_time = time.time()

        try:
            response = requests.post(f"{self.base_url}/v1/completions", json=payload, timeout=self.config.timeout)
            response_time = time.time() - start_time

            if response.status_code != 200:
                return InferenceResult(
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text}",
                    response_time=response_time,
                )

            data = response.json()
            choice = data.get("choices", [{}])[0]

            return InferenceResult(
                success=True,
                text=choice.get("text", ""),
                model=model,
                usage=data.get("usage", {}),
                finish_reason=choice.get("finish_reason", ""),
                response_time=response_time,
            )

        except requests.exceptions.Timeout:
            response_time = time.time() - start_time
            return InferenceResult(success=False, error="Request timeout", response_time=response_time)
        except requests.exceptions.RequestException as e:
            response_time = time.time() - start_time
            return InferenceResult(success=False, error=str(e), response_time=response_time)
