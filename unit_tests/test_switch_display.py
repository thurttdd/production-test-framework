import logging

from docopt import docopt

from production_test_framework.switch import switch_status
from production_test_framework.switch.models import NetworkSwitchStatus, Port, Vlan
from production_test_framework.switch.switch_status import (
    _configure_logging,
    _resolve_log_level,
    format_ports,
    format_switch_report,
    format_switch_status,
    format_vlans,
)


def test_format_switch_status_plain():
    status = NetworkSwitchStatus(
        uptime="3 days",
        hostname="leaf01",
        asic_model="Spectrum-4",
        model="SN5600",
        serial_number="MT123",
        firmware_version="34.4.1000",
        software_version="Cumulus Linux 5.12.0",
    )
    text = format_switch_status(status, use_color=False)

    assert "Switch status — leaf01" in text
    assert "Hostname" in text
    assert "leaf01" in text
    assert "Uptime" in text
    assert "3 days" in text
    assert "SN5600" in text
    assert "34.4.1000" in text


def test_format_ports_plain():
    ports = [
        Port(id="swp1", admin_up=True, oper_up=True, description="server-1"),
        Port(id="swp2", admin_up=False, oper_up=False),
    ]
    text = format_ports(ports, use_color=False)

    assert "Ports" in text
    assert "swp1" in text
    assert "swp2" in text
    assert "server-1" in text
    assert "Admin" in text
    assert "Oper" in text


def test_format_switch_report_includes_ports():
    status = NetworkSwitchStatus(
        uptime="1 day",
        hostname="leaf01",
        asic_model="Spectrum-4",
        model="SN5600",
        serial_number="MT123",
        firmware_version="34.4.1000",
        software_version="Cumulus Linux 5.12.0",
    )
    ports = [Port(id="swp1", admin_up=True, oper_up=True)]
    vlans = [
        Vlan(
            id="10",
            ports=(
                Port(id="swp1", admin_up=True, oper_up=True, description="uplink"),
                Port(id="swp2", admin_up=True, oper_up=False),
            ),
        )
    ]
    text = format_switch_report(status, ports, vlans, use_color=False)

    assert "Switch status — leaf01" in text
    assert "Ports" in text
    assert "swp1" in text
    assert "VLANs" in text
    assert "VLAN 10" in text
    assert "swp2" in text


def test_format_vlans_empty():
    text = format_vlans([], use_color=False)
    assert "VLANs" in text
    assert "(none)" in text


def test_docopt_log_level_optional():
    args = docopt(switch_status.__doc__, argv=["--hostname=h", "--username=u"])
    assert args["--log-level"] is None

    args_debug = docopt(switch_status.__doc__, argv=["--hostname=h", "--username=u", "--log-level=DEBUG"])
    assert args_debug["--log-level"] == "DEBUG"


def test_resolve_log_level():
    assert _resolve_log_level("debug") == logging.DEBUG
    assert _resolve_log_level("INFO") == logging.INFO


def test_configure_logging_sets_switch_logger_level():
    _configure_logging("WARNING")
    switch_logger = logging.getLogger("production_test_framework.switch")
    assert switch_logger.level == logging.WARNING
    switch_logger.handlers.clear()
    switch_logger.setLevel(logging.NOTSET)
