# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2026 Delos Data, Inc.

"""
SSH remote execution utilities using Paramiko.

Provides helpers for executing commands on remote hosts via SSH.
"""

import socket
from dataclasses import dataclass
from typing import Optional

import paramiko

from .config import LGTMConfig


@dataclass
class CommandResult:
    """Result of a command execution."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0

    def __bool__(self) -> bool:
        return self.success


class SSHExecutor:
    """Execute commands on remote hosts via Paramiko SSH."""

    def __init__(self, config: LGTMConfig):
        self.config = config
        self._client: Optional[paramiko.SSHClient] = None
        self._current_host: Optional[str] = None

    def _get_client(self, host: Optional[str] = None) -> paramiko.SSHClient:
        """
        Get or create SSH client connection.

        Args:
            host: Target host (defaults to config.host)

        Returns:
            Connected paramiko.SSHClient
        """
        host = host or self.config.host

        # Reuse existing connection if to the same host
        if self._client is not None and self._current_host == host:
            transport = self._client.get_transport()
            if transport and transport.is_active():
                return self._client
            # Connection is stale, close it
            self._client.close()
            self._client = None
            self._current_host = None

        # Close existing connection if switching hosts
        if self._client is not None:
            self._client.close()
            self._client = None

        # Create new connection
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            client.connect(
                hostname=host,
                username=self.config.ansible_remote_user,
                allow_agent=True,
                look_for_keys=True,
                timeout=30,
            )
            self._client = client
            self._current_host = host
            return client
        except Exception as e:
            raise ConnectionError(f"Failed to connect to {host}: {e}") from e

    def get_transport(self, host: Optional[str] = None) -> Optional[paramiko.Transport]:
        """
        Get the SSH transport for the connection.

        Useful for port forwarding operations.

        Args:
            host: Target host (defaults to config.host)

        Returns:
            paramiko.Transport or None if not connected
        """
        try:
            client = self._get_client(host)
            return client.get_transport()
        except ConnectionError:
            return None

    def run(
        self,
        command: str,
        host: Optional[str] = None,
        timeout: int = 60,
        stdin_data: Optional[str] = None,
    ) -> CommandResult:
        """
        Execute a command on the remote host.

        Args:
            command: The command to execute
            host: Target host (defaults to config.host)
            timeout: Command timeout in seconds
            stdin_data: Data to write to stdin as a string

        Returns:
            CommandResult with returncode, stdout, stderr
        """
        try:
            client = self._get_client(host)
        except ConnectionError as e:
            return CommandResult(
                returncode=-1,
                stdout="",
                stderr=str(e),
            )

        try:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)

            # Write stdin data if provided
            if stdin_data is not None:
                stdin.write(stdin_data)
                stdin.flush()
                # Close the stdin channel to signal EOF
                # This is necessary to prevent the command from hanging indefinitely
                stdin.channel.shutdown_write()

            # Read output
            stdout_str = stdout.read().decode("utf-8", errors="replace").strip()
            stderr_str = stderr.read().decode("utf-8", errors="replace").strip()
            exit_status = stdout.channel.recv_exit_status()

            return CommandResult(
                returncode=exit_status,
                stdout=stdout_str,
                stderr=stderr_str,
            )
        except socket.timeout:
            return CommandResult(
                returncode=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
            )
        except Exception as e:
            return CommandResult(
                returncode=-1,
                stdout="",
                stderr=str(e),
            )

    def run_kubectl(
        self,
        kubectl_args: str,
        host: Optional[str] = None,
        timeout: int = 60,
        kubeconfig: str = "~/.kube/config",
        stdin_data: Optional[str] = None,
    ) -> CommandResult:
        """
        Execute a kubectl command on the remote k3s host.

        Args:
            kubectl_args: Arguments to pass to kubectl (e.g., "get pods -A")
            host: Target host
            timeout: Command timeout
            kubeconfig: Path to kubeconfig file (default: ~/.kube/config)
            stdin_data: Data to write to stdin as a string
        Returns:
            CommandResult
        """
        cmd = f"kubectl --kubeconfig {kubeconfig} {kubectl_args}"
        return self.run(cmd, host=host, timeout=timeout, stdin_data=stdin_data)

    def check_service_active(self, service: str, host: Optional[str] = None) -> bool:
        """Check if a systemd service is active on the remote host."""
        result = self.run(f"systemctl is-active {service}", host=host)
        return result.success and result.stdout.strip() == "active"

    def file_exists(self, path: str, host: Optional[str] = None) -> bool:
        """Check if a file exists on the remote host."""
        result = self.run(f"test -f '{path}'", host=host)
        return result.success

    def read_file(self, path: str, host: Optional[str] = None) -> Optional[str]:
        """Read a file from the remote host."""
        result = self.run(f"cat '{path}'", host=host)
        return result.stdout if result.success else None

    def close(self):
        """Close the SSH connection."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
            self._current_host = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
