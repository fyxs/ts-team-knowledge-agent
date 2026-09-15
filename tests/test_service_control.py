from ts_knowledge_agent.services.service_control import (
    DEFAULT_WEB_PORT,
    listening_pid,
    service_status,
)


def test_status_reports_not_running_on_free_port():
    status = service_status(port=59999)
    assert status.listening is False
    assert status.pid is None
    assert status.detail == "not_running"


def test_default_port_constant():
    assert DEFAULT_WEB_PORT == 8088


def test_status_payload_fields():
    payload = service_status(port=59999).to_dict()
    assert set(payload) == {"port", "listening", "pid", "health", "detail"}
    assert payload["port"] == 59999


def test_listening_pid_returns_none_for_unused_port():
    assert listening_pid(59998) is None
