"""clamd INSTREAM без живого демона."""

from __future__ import annotations

from kontur.application.intake import antivirus_rejection
from kontur.infrastructure.clamd import AvStatus, parse_clamd_reply, scan_bytes


class _Fake:
    def __init__(self, reply: bytes) -> None:
        self.reply = reply
        self.sent = b""
        self._sent_reply = False

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def recv(self, _size: int) -> bytes:
        if self._sent_reply:
            return b""
        self._sent_reply = True
        return self.reply

    def close(self) -> None:
        return None


def test_clean_reply_is_not_a_rejection() -> None:
    assert parse_clamd_reply("stream: OK") == (AvStatus.CLEAN, "")


def test_found_reply_names_the_signature() -> None:
    status, detail = parse_clamd_reply("stream: Eicar-Test-Signature FOUND")
    assert status is AvStatus.INFECTED
    assert "Eicar" in detail


def test_instream_writes_the_length_prefix() -> None:
    fake = _Fake(b"stream: OK\0")
    status, _detail = scan_bytes(b"pdf", host="clamd", opener=lambda: fake)
    assert status is AvStatus.CLEAN
    assert fake.sent.startswith(b"zINSTREAM\0")
    assert fake.sent.endswith(b"\0\0\0\0")


def test_unconfigured_scanner_does_not_block_dev_intake(monkeypatch) -> None:
    monkeypatch.delenv("KONTUR_CLAMD_HOST", raising=False)
    monkeypatch.delenv("KONTUR_CLAMD_REQUIRED", raising=False)
    assert antivirus_rejection("note.pdf", b"%PDF-") is None


def test_required_scanner_without_a_daemon_rejects(monkeypatch) -> None:
    monkeypatch.delenv("KONTUR_CLAMD_HOST", raising=False)
    monkeypatch.setenv("KONTUR_CLAMD_REQUIRED", "true")
    rejection = antivirus_rejection("note.pdf", b"%PDF-")
    assert rejection is not None
    assert rejection.reason.value == "ANTIVIRUS_REJECTED"
