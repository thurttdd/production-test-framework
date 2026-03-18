# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2025 Delos Data, Inc.

"""Unit tests for telemetry.otelp module."""

import socket
from unittest.mock import MagicMock, patch

import pytest

from production_test_framework.telemetry.otelp import (
    Otelp,
    OtelpConfig,
    create_otelp,
)


class TestOtelpConfig:
    """Tests for OtelpConfig."""

    def test_defaults(self):
        config = OtelpConfig()
        assert config.service_name == ""
        assert config.service_version == "1.0.0"
        assert config.friendly_name == ""


class TestOtelp:
    """Tests for Otelp class."""

    def test_empty_endpoint_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            Otelp("")

    def test_init_sets_endpoint_and_config(self):
        otelp = Otelp("host:4317")
        assert otelp.otel_collector_endpoint == "host:4317"
        assert otelp.is_connected is False
        assert otelp.config.service_name == ""

    @patch("production_test_framework.telemetry.otelp.socket.socket")
    def test_test_otlp_connectivity_success(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.connect_ex.return_value = 0

        otelp = Otelp("collector:4317")
        result = otelp._test_otlp_connectivity()

        assert result is True
        mock_sock.connect_ex.assert_called_once_with(("collector", 4317))

    @patch("production_test_framework.telemetry.otelp.socket.socket")
    def test_test_otlp_connectivity_failure(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.connect_ex.return_value = 1

        otelp = Otelp("collector:4317")
        result = otelp._test_otlp_connectivity()

        assert result is False

    @patch("production_test_framework.telemetry.otelp.socket.socket")
    def test_test_otlp_connectivity_strips_protocol(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.connect_ex.return_value = 0

        otelp = Otelp("grpc://collector:4317")
        result = otelp._test_otlp_connectivity()

        assert result is True
        mock_sock.connect_ex.assert_called_once_with(("collector", 4317))

    def test_test_otlp_connectivity_invalid_port_returns_false(self):
        otelp = Otelp("host:notaport")
        result = otelp._test_otlp_connectivity()
        assert result is False

    @patch("production_test_framework.telemetry.otelp.socket.socket")
    def test_test_otlp_connectivity_socket_error(self, mock_socket_cls):
        mock_socket_cls.return_value.connect_ex.side_effect = socket.error("refused")
        otelp = Otelp("host:4317")
        result = otelp._test_otlp_connectivity()
        assert result is False

    def test_check_initialized_raises_when_not_connected(self):
        otelp = Otelp("host:4317")
        with pytest.raises(RuntimeError, match="OTLP not connected"):
            otelp._check_initialized()

    def test_check_initialized_raises_when_meter_none(self):
        otelp = Otelp("host:4317")
        otelp.is_connected = True
        otelp._meter = None
        with pytest.raises(RuntimeError, match="Meter not initialized"):
            otelp._check_initialized()

    @patch.object(Otelp, "_init_meter_provider")
    def test_initialize_sets_config_and_connected(self, mock_init):
        with patch.object(Otelp, "_test_otlp_connectivity", return_value=True):
            otelp = Otelp("host:4317")
            otelp.initialize(
                service_name="svc",
                service_version="1.0.0",
                friendly_name="friendly",
            )
            assert otelp.config.service_name == "svc"
            assert otelp.config.friendly_name == "friendly"
            assert otelp.is_connected is True
            mock_init.assert_called_once()

    @patch.object(Otelp, "_init_meter_provider")
    def test_initialize_not_connected_when_test_fails(self, mock_init):
        with patch.object(Otelp, "_test_otlp_connectivity", return_value=False):
            otelp = Otelp("host:4317")
            otelp.initialize(
                service_name="svc",
                service_version="1.0.0",
                friendly_name="friendly",
            )
            assert otelp.is_connected is False
            mock_init.assert_not_called()

    def test_get_instrument_returns_none_when_empty(self):
        otelp = Otelp("host:4317")
        assert otelp.get_instrument("nonexistent") is None

    def test_get_connection_status(self):
        otelp = Otelp("host:4317")
        assert otelp.get_connection_status() is False
        otelp.is_connected = True
        assert otelp.get_connection_status() is True

    def test_cleanup_clears_instruments_and_sets_connected_false(self):
        otelp = Otelp("host:4317")
        otelp._instruments["c1"] = MagicMock()
        otelp._meter_provider = None
        otelp.cleanup()
        assert len(otelp._instruments) == 0
        assert otelp.is_connected is False

    def test_cleanup_flushes_and_shuts_down_provider(self):
        otelp = Otelp("host:4317")
        provider = MagicMock()
        otelp._meter_provider = provider
        otelp.cleanup()
        provider.force_flush.assert_called_once()
        provider.shutdown.assert_called_once()

    def test_context_manager_exit_calls_cleanup(self):
        otelp = Otelp("host:4317")
        with patch.object(otelp, "cleanup") as mock_cleanup:
            with otelp:
                pass
            mock_cleanup.assert_called_once()


class TestCreateOtelp:
    """Tests for create_otelp context manager."""

    def test_yields_initialized_otelp_and_cleans_up(self):
        with patch.object(Otelp, "_test_otlp_connectivity", return_value=True):
            with create_otelp("host:4317", "svc", "1.0.0", "friendly") as otelp:
                assert otelp.config.service_name == "svc"
                assert otelp.is_connected is True
            # cleanup is called on exit
            assert otelp.is_connected is False
