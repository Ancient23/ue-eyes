"""Tests for ue_eyes.remote_exec — UE Python remote execution client.

All tests use mocked sockets and do NOT require a running UE instance.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from ue_eyes.remote_exec import (
    DEFAULT_MULTICAST_GROUP,
    DEFAULT_MULTICAST_PORT,
    DEFAULT_MULTICAST_TTL,
    PROTOCOL_MAGIC,
    PROTOCOL_VERSION,
    UEConnectionError,
    UEExecutionError,
    UERemoteExecution,
    _decode_message,
    _encode_message,
    _make_message,
)


# ======================================================================
# Message encoding / decoding
# ======================================================================


class TestMessageEncoding:
    """Tests for _encode_message and _decode_message."""

    def test_roundtrip_simple(self):
        msg = {"version": 1, "magic": "ue_py", "type": "ping", "source": "abc"}
        assert _decode_message(_encode_message(msg)) == msg

    def test_roundtrip_with_data(self):
        msg = {
            "version": 1,
            "magic": "ue_py",
            "type": "command",
            "source": "abc",
            "dest": "def",
            "data": {"command": "print('hi')", "unattended": True},
        }
        assert _decode_message(_encode_message(msg)) == msg

    def test_encode_is_utf8_json(self):
        msg = {"type": "ping"}
        encoded = _encode_message(msg)
        assert isinstance(encoded, bytes)
        # No spaces — compact separators
        assert b" " not in encoded
        parsed = json.loads(encoded.decode("utf-8"))
        assert parsed == msg

    def test_decode_from_raw_bytes(self):
        raw = b'{"type":"pong","source":"ue-node-1"}'
        result = _decode_message(raw)
        assert result["type"] == "pong"
        assert result["source"] == "ue-node-1"

    def test_roundtrip_unicode(self):
        msg = {"type": "command", "data": {"command": "x = '\u00e9\u00e8\u00ea'"}}
        assert _decode_message(_encode_message(msg)) == msg


class TestMakeMessage:
    """Tests for _make_message helper."""

    def test_ping_message(self):
        msg = _make_message("ping", "my-node")
        assert msg["version"] == PROTOCOL_VERSION
        assert msg["magic"] == PROTOCOL_MAGIC
        assert msg["type"] == "ping"
        assert msg["source"] == "my-node"
        assert "dest" not in msg
        assert "data" not in msg

    def test_command_message_with_dest_and_data(self):
        msg = _make_message(
            "command", "client-1", "ue-node-2",
            data={"command": "pass", "unattended": True},
        )
        assert msg["dest"] == "ue-node-2"
        assert msg["data"]["command"] == "pass"
        assert msg["data"]["unattended"] is True

    def test_open_connection_message(self):
        msg = _make_message(
            "open_connection", "client-1", "ue-node-2",
            data={"command_ip": "127.0.0.1", "command_port": 12345},
        )
        assert msg["type"] == "open_connection"
        assert msg["data"]["command_ip"] == "127.0.0.1"
        assert msg["data"]["command_port"] == 12345

    def test_empty_dest_omitted(self):
        msg = _make_message("ping", "src", "")
        assert "dest" not in msg

    def test_none_data_omitted(self):
        msg = _make_message("ping", "src", data=None)
        assert "data" not in msg

    def test_falsy_data_included(self):
        """data=0, data=[], data={} should be included (only None omitted)."""
        msg = _make_message("test", "src", data=0)
        assert "data" in msg and msg["data"] == 0

        msg = _make_message("test", "src", data=[])
        assert "data" in msg and msg["data"] == []

        msg = _make_message("test", "src", data={})
        assert "data" in msg and msg["data"] == {}


# ======================================================================
# Constructor
# ======================================================================


class TestConstructor:
    """Tests for UERemoteExecution.__init__."""

    def test_default_parameters(self):
        ue = UERemoteExecution()
        assert ue._mcast_group == DEFAULT_MULTICAST_GROUP
        assert ue._mcast_port == DEFAULT_MULTICAST_PORT
        assert ue._mcast_bind == "127.0.0.1"
        assert ue._mcast_ttl == DEFAULT_MULTICAST_TTL
        assert ue._timeout == 30.0
        assert ue._ue_node_id == ""
        assert ue._udp_sock is None
        assert ue._tcp_server is None
        assert ue._tcp_conn is None

    def test_custom_parameters(self):
        ue = UERemoteExecution(
            multicast_group="239.1.2.3",
            multicast_port=7777,
            multicast_bind="192.168.1.1",
            multicast_ttl=2,
            timeout=5.0,
        )
        assert ue._mcast_group == "239.1.2.3"
        assert ue._mcast_port == 7777
        assert ue._mcast_bind == "192.168.1.1"
        assert ue._mcast_ttl == 2
        assert ue._timeout == 5.0

    def test_node_id_is_uuid(self):
        ue = UERemoteExecution()
        import uuid
        # Should not raise
        uuid.UUID(ue._node_id)

    def test_each_instance_gets_unique_node_id(self):
        ue1 = UERemoteExecution()
        ue2 = UERemoteExecution()
        assert ue1._node_id != ue2._node_id


# ======================================================================
# Connection lifecycle (mocked sockets)
# ======================================================================


class TestConnectionLifecycle:
    """Tests for connect/close lifecycle with mocked sockets."""

    def test_execute_raises_when_not_connected(self):
        ue = UERemoteExecution()
        with pytest.raises(UEConnectionError, match="Not connected"):
            ue.execute("pass")

    def test_execute_file_raises_for_missing_script(self, tmp_path):
        ue = UERemoteExecution()
        # Force a connection so execute_file reaches the file check
        # (execute_file checks file existence before calling execute)
        with pytest.raises(FileNotFoundError, match="Script not found"):
            ue.execute_file(str(tmp_path / "nonexistent.py"))

    def test_execute_file_injects_params(self, tmp_path):
        """execute_file injects _ue_eyes_params dict at top of script code."""
        script = tmp_path / "test_script.py"
        script.write_text("print('hello')", encoding="utf-8")

        ue = UERemoteExecution()
        # Mock TCP conn so execute() works
        mock_tcp = MagicMock()
        ue._tcp_conn = mock_tcp
        ue._ue_node_id = "ue-node"

        # Make _tcp_recv return a successful response
        success_response = json.dumps({
            "type": "command_result",
            "data": {"success": True, "result": "", "output": []},
        }).encode("utf-8")
        mock_tcp.recv.return_value = success_response

        result = ue.execute_file(str(script), foo="bar", num=42)

        # Verify the sent command contains the injected params
        sent_data = mock_tcp.sendall.call_args[0][0]
        sent_msg = json.loads(sent_data.decode("utf-8"))
        code = sent_msg["data"]["command"]
        assert code.startswith("_ue_eyes_params = ")
        assert '"foo": "bar"' in code
        assert '"num": 42' in code
        assert "print('hello')" in code

    def test_execute_file_no_params_no_injection(self, tmp_path):
        """execute_file without kwargs does not inject _ue_eyes_params."""
        script = tmp_path / "test_script.py"
        script.write_text("x = 1", encoding="utf-8")

        ue = UERemoteExecution()
        mock_tcp = MagicMock()
        ue._tcp_conn = mock_tcp
        ue._ue_node_id = "ue-node"

        success_response = json.dumps({
            "type": "command_result",
            "data": {"success": True, "result": "", "output": []},
        }).encode("utf-8")
        mock_tcp.recv.return_value = success_response

        ue.execute_file(str(script))

        sent_data = mock_tcp.sendall.call_args[0][0]
        sent_msg = json.loads(sent_data.decode("utf-8"))
        code = sent_msg["data"]["command"]
        assert "_ue_eyes_params" not in code
        assert "x = 1" in code

    def test_context_manager_calls_connect_and_close(self):
        ue = UERemoteExecution()
        ue.connect = MagicMock()
        ue.close = MagicMock()

        with ue as ctx:
            assert ctx is ue
            ue.connect.assert_called_once()
            ue.close.assert_not_called()

        ue.close.assert_called_once()

    def test_context_manager_calls_close_on_exception(self):
        ue = UERemoteExecution()
        ue.connect = MagicMock()
        ue.close = MagicMock()

        with pytest.raises(ValueError):
            with ue:
                raise ValueError("boom")

        ue.close.assert_called_once()

    def test_close_sends_close_connection_and_cleans_up(self):
        ue = UERemoteExecution()
        mock_udp = MagicMock()
        mock_tcp_server = MagicMock()
        mock_tcp_conn = MagicMock()

        ue._udp_sock = mock_udp
        ue._tcp_server = mock_tcp_server
        ue._tcp_conn = mock_tcp_conn
        ue._ue_node_id = "ue-node-id"
        ue._node_id = "my-node-id"

        ue.close()

        # Verify close_connection was sent via UDP
        sent_data = mock_udp.sendto.call_args[0][0]
        sent_msg = json.loads(sent_data.decode("utf-8"))
        assert sent_msg["type"] == "close_connection"
        assert sent_msg["source"] == "my-node-id"
        assert sent_msg["dest"] == "ue-node-id"

        # Verify all sockets were closed
        mock_tcp_conn.close.assert_called_once()
        mock_tcp_server.close.assert_called_once()
        mock_udp.close.assert_called_once()

        # Verify state reset
        assert ue._tcp_conn is None
        assert ue._tcp_server is None
        assert ue._udp_sock is None
        assert ue._ue_node_id == ""

    def test_close_without_connection_is_safe(self):
        """close() on a never-connected instance should not raise."""
        ue = UERemoteExecution()
        ue.close()  # Should not raise

    def test_close_tolerates_socket_errors(self):
        """close() should not raise even if sockets raise OSError."""
        ue = UERemoteExecution()
        mock_udp = MagicMock()
        mock_udp.sendto.side_effect = OSError("send failed")
        mock_udp.close.side_effect = OSError("close failed")
        ue._udp_sock = mock_udp
        ue._ue_node_id = "ue"

        ue.close()  # Should not raise

    def test_connect_skips_if_already_connected(self):
        """connect() should be a no-op if _tcp_conn is already set."""
        ue = UERemoteExecution()
        ue._tcp_conn = MagicMock()  # Pretend already connected

        # If connect tried to create sockets, it would fail here
        # because we didn't mock socket.socket
        ue.connect()  # Should return immediately


# ======================================================================
# Ping
# ======================================================================


class TestPing:
    def test_ping_returns_false_when_no_ue(self):
        """ping() returns False when no UE instance responds."""
        ue = UERemoteExecution(timeout=0.1)

        with patch("ue_eyes.remote_exec.socket.socket") as mock_socket_cls:
            mock_sock = MagicMock()
            mock_socket_cls.return_value = mock_sock
            # recvfrom times out immediately -> no pong
            mock_sock.recvfrom.side_effect = socket.timeout("timed out")

            result = ue.ping()
            assert result is False

    def test_ping_returns_true_on_success(self):
        """ping() returns True when connect and execute succeed."""
        ue = UERemoteExecution()
        ue.connect = MagicMock()
        ue.execute = MagicMock(return_value={"success": True, "output": "", "result": ""})
        ue.close = MagicMock()

        assert ue.ping() is True
        ue.connect.assert_called_once()
        ue.execute.assert_called_once_with("pass")
        ue.close.assert_called_once()

    def test_ping_calls_close_even_on_failure(self):
        """ping() always calls close(), even on connection failure."""
        ue = UERemoteExecution()
        ue.connect = MagicMock(side_effect=UEConnectionError("no UE"))
        ue.close = MagicMock()

        assert ue.ping() is False
        ue.close.assert_called_once()


# ======================================================================
# Execute response parsing
# ======================================================================


class TestExecuteResponseParsing:
    """Tests for execute() response handling."""

    def _make_ue(self) -> UERemoteExecution:
        """Create a UERemoteExecution with a mocked TCP connection."""
        ue = UERemoteExecution()
        ue._tcp_conn = MagicMock()
        ue._ue_node_id = "ue-node"
        return ue

    def _set_response(self, ue: UERemoteExecution, response: dict) -> None:
        """Configure the mock TCP to return the given response dict."""
        encoded = json.dumps(response).encode("utf-8")
        ue._tcp_conn.recv.return_value = encoded

    def test_successful_execution(self):
        ue = self._make_ue()
        self._set_response(ue, {
            "type": "command_result",
            "data": {
                "success": True,
                "result": "42",
                "output": [{"output": "line1"}, {"output": "line2"}],
            },
        })

        result = ue.execute("1 + 1")
        assert result["success"] is True
        assert result["result"] == "42"
        assert result["output"] == "line1\nline2"

    def test_failed_execution_raises(self):
        ue = self._make_ue()
        self._set_response(ue, {
            "type": "command_result",
            "data": {
                "success": False,
                "result": "NameError: name 'x' is not defined",
                "output": [{"output": "Traceback..."}],
            },
        })

        with pytest.raises(UEExecutionError, match="UE execution failed"):
            ue.execute("print(x)")

    def test_non_command_result_type_raises(self):
        ue = self._make_ue()
        self._set_response(ue, {
            "type": "pong",
            "source": "ue-node",
        })

        with pytest.raises(UEExecutionError, match="Unexpected response type.*pong"):
            ue.execute("pass")

    def test_output_entries_as_dicts(self):
        ue = self._make_ue()
        self._set_response(ue, {
            "type": "command_result",
            "data": {
                "success": True,
                "result": "",
                "output": [
                    {"output": "first line"},
                    {"output": "second line"},
                    {"output": "third line"},
                ],
            },
        })

        result = ue.execute("pass")
        assert result["output"] == "first line\nsecond line\nthird line"

    def test_output_entries_as_strings(self):
        ue = self._make_ue()
        self._set_response(ue, {
            "type": "command_result",
            "data": {
                "success": True,
                "result": "",
                "output": ["alpha", "beta", "gamma"],
            },
        })

        result = ue.execute("pass")
        assert result["output"] == "alpha\nbeta\ngamma"

    def test_output_entries_mixed(self):
        ue = self._make_ue()
        self._set_response(ue, {
            "type": "command_result",
            "data": {
                "success": True,
                "result": "",
                "output": [{"output": "dict-line"}, "string-line"],
            },
        })

        result = ue.execute("pass")
        assert result["output"] == "dict-line\nstring-line"

    def test_empty_output(self):
        ue = self._make_ue()
        self._set_response(ue, {
            "type": "command_result",
            "data": {
                "success": True,
                "result": "ok",
                "output": [],
            },
        })

        result = ue.execute("pass")
        assert result["output"] == ""
        assert result["result"] == "ok"

    def test_missing_output_key(self):
        ue = self._make_ue()
        self._set_response(ue, {
            "type": "command_result",
            "data": {
                "success": True,
                "result": "",
            },
        })

        result = ue.execute("pass")
        assert result["output"] == ""

    def test_missing_result_key(self):
        ue = self._make_ue()
        self._set_response(ue, {
            "type": "command_result",
            "data": {
                "success": True,
                "output": [],
            },
        })

        result = ue.execute("pass")
        assert result["result"] == ""

    def test_execute_sends_correct_command_message(self):
        ue = self._make_ue()
        ue._node_id = "client-node"
        self._set_response(ue, {
            "type": "command_result",
            "data": {"success": True, "result": "", "output": []},
        })

        ue.execute("print('hello')")

        sent_data = ue._tcp_conn.sendall.call_args[0][0]
        sent_msg = json.loads(sent_data.decode("utf-8"))
        assert sent_msg["type"] == "command"
        assert sent_msg["source"] == "client-node"
        assert sent_msg["dest"] == "ue-node"
        assert sent_msg["data"]["command"] == "print('hello')"
        assert sent_msg["data"]["unattended"] is True
        assert sent_msg["data"]["exec_mode"] == "ExecuteFile"


# ======================================================================
# Protocol constants
# ======================================================================


class TestProtocolConstants:
    def test_protocol_version(self):
        assert PROTOCOL_VERSION == 1

    def test_protocol_magic(self):
        assert PROTOCOL_MAGIC == "ue_py"

    def test_default_multicast_group(self):
        assert DEFAULT_MULTICAST_GROUP == "239.0.0.1"

    def test_default_multicast_port(self):
        assert DEFAULT_MULTICAST_PORT == 6766

    def test_default_multicast_ttl(self):
        assert DEFAULT_MULTICAST_TTL == 0
