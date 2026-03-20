"""
UE Remote Execution bridge.

Implements the Unreal Engine 5.7 Python Editor Script Plugin remote execution
protocol, as defined in PythonScriptRemoteExecution.cpp.

Protocol overview:
    1. Client joins UDP multicast group (default 239.0.0.1:6766)
    2. Client sends "ping" via UDP multicast -> UE replies "pong"
    3. Client starts a local TCP server
    4. Client sends "open_connection" via UDP with TCP server address
    5. UE connects TO the client's TCP server
    6. Commands and results flow over the TCP connection as raw JSON

Message format (both UDP and TCP):
    Raw UTF-8 JSON with fields: version, magic, type, source, [dest], [data]
"""

from __future__ import annotations

import json
import logging
import socket
import struct
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
PROTOCOL_MAGIC = "ue_py"
DEFAULT_MULTICAST_GROUP = "239.0.0.1"
DEFAULT_MULTICAST_PORT = 6766
DEFAULT_MULTICAST_TTL = 0  # 0 = local machine only


class UEConnectionError(Exception):
    """Raised when a connection to UE cannot be established or is lost."""


class UEExecutionError(Exception):
    """Raised when UE reports an error executing a command."""


def _encode_message(msg: dict) -> bytes:
    """Encode a message dict to wire format: raw UTF-8 JSON."""
    return json.dumps(msg, separators=(",", ":")).encode("utf-8")


def _decode_message(data: bytes) -> dict:
    """Decode a raw JSON message from bytes."""
    return json.loads(data.decode("utf-8"))


def _make_message(msg_type: str, source: str, dest: str = "",
                  data: Any = None) -> dict:
    """Build a protocol message dict."""
    msg = {
        "version": PROTOCOL_VERSION,
        "magic": PROTOCOL_MAGIC,
        "type": msg_type,
        "source": source,
    }
    if dest:
        msg["dest"] = dest
    if data is not None:
        msg["data"] = data
    return msg


class UERemoteExecution:
    """Client for Unreal Engine's Python remote execution endpoint.

    Usage::

        with UERemoteExecution() as ue:
            result = ue.execute("print('hello from UE')")
    """

    def __init__(
        self,
        multicast_group: str = DEFAULT_MULTICAST_GROUP,
        multicast_port: int = DEFAULT_MULTICAST_PORT,
        multicast_bind: str = "127.0.0.1",
        multicast_ttl: int = DEFAULT_MULTICAST_TTL,
        timeout: float = 30.0,
    ) -> None:
        self._mcast_group = multicast_group
        self._mcast_port = multicast_port
        self._mcast_bind = multicast_bind
        self._mcast_ttl = multicast_ttl
        self._timeout = timeout
        self._node_id: str = str(uuid.uuid4())

        # Discovered UE node
        self._ue_node_id: str = ""

        # Sockets
        self._udp_sock: socket.socket | None = None
        self._tcp_server: socket.socket | None = None
        self._tcp_conn: socket.socket | None = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Discover UE via multicast, start TCP server, request connection."""
        if self._tcp_conn is not None:
            return

        # Step 1: Create UDP multicast socket
        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                       socket.IPPROTO_UDP)
        self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._udp_sock.settimeout(self._timeout)

        # Set multicast TTL and loopback BEFORE binding
        self._udp_sock.setsockopt(socket.IPPROTO_IP,
                                  socket.IP_MULTICAST_TTL, self._mcast_ttl)
        self._udp_sock.setsockopt(socket.IPPROTO_IP,
                                  socket.IP_MULTICAST_LOOP, 1)
        # Set the outgoing multicast interface
        self._udp_sock.setsockopt(socket.IPPROTO_IP,
                                  socket.IP_MULTICAST_IF,
                                  socket.inet_aton(self._mcast_bind))

        # Bind to INADDR_ANY on the multicast port (Windows requires this)
        self._udp_sock.bind(("0.0.0.0", self._mcast_port))

        # Join multicast group on the bind interface
        mreq = struct.pack(
            "4s4s",
            socket.inet_aton(self._mcast_group),
            socket.inet_aton(self._mcast_bind),
        )
        self._udp_sock.setsockopt(socket.IPPROTO_IP,
                                  socket.IP_ADD_MEMBERSHIP, mreq)

        # Step 2: Send ping and wait for pong
        ping = _make_message("ping", self._node_id)
        self._udp_send(ping)
        logger.info("Sent ping to %s:%s", self._mcast_group, self._mcast_port)

        self._ue_node_id = self._wait_for_pong()
        logger.info("Discovered UE node: %s", self._ue_node_id)

        # Step 3: Start TCP server on a random local port
        self._tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._tcp_server.bind(("127.0.0.1", 0))
        self._tcp_server.listen(1)
        self._tcp_server.settimeout(self._timeout)
        tcp_ip, tcp_port = self._tcp_server.getsockname()
        logger.info("TCP server listening on %s:%s", tcp_ip, tcp_port)

        # Step 4: Send open_connection via UDP telling UE where to connect
        open_msg = _make_message(
            "open_connection", self._node_id, self._ue_node_id,
            data={"command_ip": tcp_ip, "command_port": tcp_port},
        )
        self._udp_send(open_msg)
        logger.info("Sent open_connection, waiting for UE to connect...")

        # Step 5: Wait for UE to connect to our TCP server
        try:
            self._tcp_conn, addr = self._tcp_server.accept()
            self._tcp_conn.settimeout(self._timeout)
            logger.info("UE connected from %s:%s", *addr)
        except socket.timeout:
            raise UEConnectionError(
                "Timed out waiting for UE to connect to our TCP server. "
                "Is Remote Execution enabled in UE? (Plugins -> Python -> "
                "Enable Remote Execution)"
            )

    def close(self) -> None:
        """Send close_connection and tear down all sockets."""
        if self._udp_sock and self._ue_node_id:
            try:
                close_msg = _make_message(
                    "close_connection", self._node_id, self._ue_node_id,
                )
                self._udp_send(close_msg)
            except OSError:
                pass

        for sock in (self._tcp_conn, self._tcp_server, self._udp_sock):
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass

        self._tcp_conn = None
        self._tcp_server = None
        self._udp_sock = None
        self._ue_node_id = ""
        logger.info("Disconnected from UE")

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "UERemoteExecution":
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, python_code: str) -> dict:
        """Execute *python_code* inside UE and return the result dict.

        Returns a dict with at least::

            {
                "success": bool,
                "output": str,   # combined log output
                "result": str,   # result string from UE
            }
        """
        if self._tcp_conn is None:
            raise UEConnectionError("Not connected -- call connect() first")

        command_msg = _make_message(
            "command", self._node_id, self._ue_node_id,
            data={
                "command": python_code,
                "unattended": True,
                "exec_mode": "ExecuteFile",
            },
        )
        self._tcp_send(command_msg)
        response = self._tcp_recv()

        if response.get("type") != "command_result":
            raise UEExecutionError(
                f"Unexpected response type: {response.get('type')}"
            )

        resp_data = response.get("data", {})
        success = resp_data.get("success", False)
        result_str = resp_data.get("result", "")

        # Combine log output entries into a single string
        output_entries = resp_data.get("output", [])
        output_lines = []
        for entry in output_entries:
            if isinstance(entry, dict):
                output_lines.append(entry.get("output", ""))
            elif isinstance(entry, str):
                output_lines.append(entry)
        output = "\n".join(output_lines)

        if not success:
            raise UEExecutionError(
                f"UE execution failed.\nOutput: {output}\nResult: {result_str}"
            )

        return {"success": success, "output": output, "result": result_str}

    def execute_file(self, script_path: str, **kwargs: Any) -> dict:
        """Read a Python file and execute it inside UE.

        If *kwargs* are provided they are injected as a global dict named
        ``_ue_eyes_params`` at the top of the script so the UE-side code can
        read them.
        """
        path = Path(script_path)
        if not path.is_file():
            raise FileNotFoundError(f"Script not found: {path}")

        code = path.read_text(encoding="utf-8")

        if kwargs:
            params_json = json.dumps(kwargs)
            injection = f"_ue_eyes_params = {params_json}\n"
            code = injection + code

        return self.execute(code)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        """Return *True* if UE is reachable via multicast."""
        try:
            self.connect()
            self.execute("pass")
            return True
        except (UEConnectionError, UEExecutionError, OSError):
            return False
        finally:
            self.close()

    # ------------------------------------------------------------------
    # UDP I/O
    # ------------------------------------------------------------------

    def _udp_send(self, msg: dict) -> None:
        """Send a JSON message via UDP multicast."""
        assert self._udp_sock is not None
        data = _encode_message(msg)
        self._udp_sock.sendto(
            data, (self._mcast_group, self._mcast_port)
        )

    def _wait_for_pong(self) -> str:
        """Listen for a 'pong' response and return the UE node ID."""
        assert self._udp_sock is not None
        deadline = time.monotonic() + self._timeout

        while time.monotonic() < deadline:
            remaining = max(0.1, deadline - time.monotonic())
            self._udp_sock.settimeout(remaining)
            try:
                data, addr = self._udp_sock.recvfrom(65536)
            except socket.timeout:
                break

            try:
                msg = _decode_message(data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

            if (msg.get("magic") != PROTOCOL_MAGIC or
                    msg.get("type") != "pong"):
                continue

            # Check this pong is for us
            if msg.get("dest") and msg.get("dest") != self._node_id:
                continue

            source = msg.get("source", "")
            if source and source != self._node_id:
                logger.info("Received pong from %s (addr %s:%s)",
                            source, *addr)
                return source

        raise UEConnectionError(
            f"No UE instance responded to ping on "
            f"{self._mcast_group}:{self._mcast_port}. "
            f"Is UE running with Remote Execution enabled?"
        )

    # ------------------------------------------------------------------
    # TCP I/O (raw JSON, no length prefix)
    # ------------------------------------------------------------------

    def _tcp_send(self, msg: dict) -> None:
        """Send a raw JSON message over the TCP connection."""
        assert self._tcp_conn is not None
        data = _encode_message(msg)
        try:
            self._tcp_conn.sendall(data)
        except OSError as exc:
            raise UEConnectionError(f"TCP send failed: {exc}") from exc

    def _tcp_recv(self) -> dict:
        """Read one raw JSON message from the TCP connection.

        UE sends raw JSON without a length prefix or delimiter.  We read
        available data in chunks and try to parse complete JSON objects.
        """
        assert self._tcp_conn is not None
        buf = b""
        deadline = time.monotonic() + self._timeout

        while time.monotonic() < deadline:
            remaining = max(0.1, deadline - time.monotonic())
            self._tcp_conn.settimeout(remaining)
            try:
                chunk = self._tcp_conn.recv(2 * 1024 * 1024)  # 2 MiB
            except socket.timeout:
                raise UEConnectionError("Timed out waiting for UE response")
            if not chunk:
                raise UEConnectionError("TCP connection closed by UE")
            buf += chunk

            try:
                return json.loads(buf.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Incomplete message, keep reading
                continue

        raise UEConnectionError("Timed out assembling UE response")
