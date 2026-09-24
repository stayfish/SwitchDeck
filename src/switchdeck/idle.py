from __future__ import annotations

import ctypes
import json
import logging
import os
import platform
import socket
import subprocess
import sys
import threading
import time
import uuid
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable

LOGGER = logging.getLogger("switchdeck")
MULTICAST_GROUP = "239.255.83.68"
MULTICAST_PORT = 45873
HEARTBEAT_SECONDS = 2.0
PEER_TTL_SECONDS = 7.0
DEFAULT_IDLE_SECONDS = 10 * 60


@dataclass(frozen=True, slots=True)
class PeerState:
    active: bool
    received_at: float


def should_prevent_sleep(
    local_idle_seconds: float,
    idle_threshold: float,
    peers: list[PeerState],
    now: float,
    peer_ttl: float = PEER_TTL_SECONDS,
) -> bool:
    if local_idle_seconds < idle_threshold:
        return True
    return any(peer.active and now - peer.received_at <= peer_ttl for peer in peers)


class AwakeLease:
    def __init__(self) -> None:
        self._held = False
        self._process: subprocess.Popen[bytes] | None = None

    def set_held(self, held: bool) -> None:
        if held == self._held:
            return
        if sys.platform == "win32":
            execution_state = 0x80000000 | (0x00000001 if held else 0)
            if not ctypes.windll.kernel32.SetThreadExecutionState(execution_state):
                raise OSError("SetThreadExecutionState 失败")
        elif sys.platform == "darwin":
            if held:
                self._process = subprocess.Popen(
                    ["/usr/bin/caffeinate", "-i", "-w", str(os.getpid())],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif self._process is not None:
                if self._process.poll() is None:
                    self._process.terminate()
                    self._process.wait(timeout=2)
                self._process = None
        self._held = held
        LOGGER.info("自动休眠锁: %s", "保持唤醒" if held else "允许休眠")

    def close(self) -> None:
        self.set_held(False)


class IdleCoordinator:
    def __init__(
        self,
        idle_threshold: float = DEFAULT_IDLE_SECONDS,
        idle_reader: Callable[[], float] | None = None,
    ) -> None:
        self.idle_threshold = idle_threshold
        self.idle_reader = idle_reader or read_idle_seconds
        self.instance_id = uuid.uuid4().hex
        self._peers: dict[str, PeerState] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None
        self._lease = AwakeLease()

    def start(self) -> None:
        self._socket = _create_multicast_socket()
        self._thread = threading.Thread(
            target=self._run, name="switchdeck-idle", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._socket is not None:
            self._socket.close()
        if self._thread is not None:
            self._thread.join(timeout=3)

    def _run(self) -> None:
        assert self._socket is not None
        next_send = 0.0
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                local_idle = self.idle_reader()
                if now >= next_send:
                    self._send(active=local_idle < self.idle_threshold)
                    next_send = now + HEARTBEAT_SECONDS
                self._receive(now)
                with self._lock:
                    peers = list(self._peers.values())
                    self._peers = {
                        peer_id: state
                        for peer_id, state in self._peers.items()
                        if now - state.received_at <= PEER_TTL_SECONDS
                    }
                held = should_prevent_sleep(
                    local_idle, self.idle_threshold, peers, now
                )
                self._lease.set_held(held)
        except (OSError, subprocess.SubprocessError):
            LOGGER.exception("协同休眠服务失败")
        finally:
            try:
                self._lease.close()
            except (OSError, subprocess.SubprocessError):
                LOGGER.exception("释放系统休眠锁失败")

    def _send(self, active: bool) -> None:
        assert self._socket is not None
        payload = json.dumps(
            {
                "protocol": 1,
                "id": self.instance_id,
                "host": platform.node(),
                "active": active,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            self._socket.sendto(payload, (MULTICAST_GROUP, MULTICAST_PORT))
        except OSError:
            if not self._stop.is_set():
                LOGGER.exception("发送空闲状态失败")

    def _receive(self, now: float) -> None:
        assert self._socket is not None
        try:
            payload, _address = self._socket.recvfrom(2048)
        except (TimeoutError, socket.timeout):
            return
        except OSError:
            if not self._stop.is_set():
                LOGGER.exception("接收空闲状态失败")
            return
        try:
            message = json.loads(payload)
            peer_id = message["id"]
            active = message["active"]
            if (
                message.get("protocol") != 1
                or not isinstance(peer_id, str)
                or len(peer_id) > 64
                or not isinstance(active, bool)
                or peer_id == self.instance_id
            ):
                return
        except (json.JSONDecodeError, KeyError, TypeError):
            return
        with self._lock:
            self._peers[peer_id] = PeerState(active=active, received_at=now)


def read_idle_seconds() -> float:
    if sys.platform == "win32":
        return _read_windows_idle_seconds()
    if sys.platform == "darwin":
        from Quartz import (
            CGEventSourceSecondsSinceLastEventType,
            kCGAnyInputEventType,
            kCGEventSourceStateCombinedSessionState,
        )

        return float(
            CGEventSourceSecondsSinceLastEventType(
                kCGEventSourceStateCombinedSessionState, kCGAnyInputEventType
            )
        )
    raise OSError("空闲检测仅支持 Windows 和 macOS")


def _read_windows_idle_seconds() -> float:
    class LastInputInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    info = LastInputInfo(cbSize=ctypes.sizeof(LastInputInfo))
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        raise ctypes.WinError()
    elapsed_ms = (ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF
    return elapsed_ms / 1000.0


def _create_multicast_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", MULTICAST_PORT))
    membership = socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton("0.0.0.0")
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    sock.settimeout(0.5)
    return sock
