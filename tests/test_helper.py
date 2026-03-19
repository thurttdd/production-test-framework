# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2025 Delos Data, Inc.

"""Unit tests for helper module."""

import socket
from unittest.mock import patch, MagicMock

from production_test_framework.helper import (
    check_tcp_connectivity,
    wait_for_tcp_connectivity,
    get_mimir_base_url,
    query_mimir,
)


class TestCheckTcpConnectivity:
    """Tests for check_tcp_connectivity."""

    def test_connectivity_success(self):
        with patch("production_test_framework.helper.socket.socket") as mock_socket_cls:
            mock_sock = MagicMock()
            mock_socket_cls.return_value = mock_sock
            mock_sock.connect_ex.return_value = 0

            result = check_tcp_connectivity("localhost", 8080)

            assert result is True
            mock_sock.connect_ex.assert_called_once_with(("localhost", 8080))
            mock_sock.close.assert_called_once()

    def test_connectivity_failure(self):
        with patch("production_test_framework.helper.socket.socket") as mock_socket_cls:
            mock_sock = MagicMock()
            mock_socket_cls.return_value = mock_sock
            mock_sock.connect_ex.return_value = 1

            result = check_tcp_connectivity("example.com", 443)

            assert result is False

    def test_connectivity_socket_error(self):
        with patch("production_test_framework.helper.socket.socket") as mock_socket_cls:
            mock_socket_cls.side_effect = socket.error("connection refused")

            result = check_tcp_connectivity("badhost", 9999)

            assert result is False

    def test_uses_custom_timeout(self):
        with patch("production_test_framework.helper.socket.socket") as mock_socket_cls:
            mock_sock = MagicMock()
            mock_socket_cls.return_value = mock_sock
            mock_sock.connect_ex.return_value = 0

            check_tcp_connectivity("localhost", 80, timeout=10.0)

            mock_sock.settimeout.assert_called_once_with(10.0)


class TestWaitForTcpConnectivity:
    """Tests for wait_for_tcp_connectivity."""

    @patch("production_test_framework.helper.check_tcp_connectivity")
    def test_returns_true_when_immediate_success(self, mock_check):
        mock_check.return_value = True

        result = wait_for_tcp_connectivity("localhost", 8080, timeout=5)

        assert result is True
        assert mock_check.call_count >= 1

    @patch("production_test_framework.helper.check_tcp_connectivity")
    @patch("production_test_framework.helper.time.sleep")
    def test_returns_false_on_timeout(self, mock_sleep, mock_check):
        mock_check.return_value = False

        result = wait_for_tcp_connectivity("localhost", 8080, timeout=1)

        assert result is False


class TestGetMimirBaseUrl:
    """Tests for get_mimir_base_url."""

    def test_returns_correct_url(self):
        assert get_mimir_base_url(9009) == "http://localhost:9009/prometheus"
        assert get_mimir_base_url(8080) == "http://localhost:8080/prometheus"


class TestQueryMimir:
    """Tests for query_mimir."""

    @patch("production_test_framework.helper.requests.get")
    def test_builds_url_and_calls_get(self, mock_get):
        mock_resp = MagicMock()
        mock_get.return_value = mock_resp

        result = query_mimir(9009, "/api/v1/query", params={"query": "up"})

        assert result is mock_resp
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] == "http://localhost:9009/prometheus/api/v1/query"
        assert call_args[1]["params"] == {"query": "up"}
        assert call_args[1]["timeout"] == 10

    @patch("production_test_framework.helper.requests.get")
    def test_default_params_and_timeout(self, mock_get):
        mock_get.return_value = MagicMock()

        query_mimir(9009, "/api/v1/query")

        mock_get.assert_called_once_with(
            "http://localhost:9009/prometheus/api/v1/query",
            params=None,
            timeout=10,
        )
