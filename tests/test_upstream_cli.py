"""Optional REAL upstream CLI against a local fake WebSocket service.

Set RECLAIMER_TEST_BINARY to an official 0.9.13 dedicated executable.
No game assets or running game server; never auto-download executables.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "docker"))
from manager.rcon_client import command_text


def exact(stream, count):
    result = b""
    while len(result) < count:
        data = stream.recv(count - len(result))
        if not data:
            raise OSError("Unexpected EOF")
        result += data
    return result


def frame(stream):
    header = exact(stream, 2)
    length = header[1] & 127
    if length == 126:
        length = struct.unpack("!H", exact(stream, 2))[0]
    if length > 16384:
        raise ValueError("Frame too large")
    mask = exact(stream, 4) if header[1] & 128 else None
    data = exact(stream, length)
    if mask:
        data = bytes(value ^ mask[i % 4] for i, value in enumerate(data))
    return json.loads(data)


def send(stream, data):
    raw = json.dumps(data).encode()
    stream.sendall(b"\x81" + (bytes([len(raw)]) if len(raw) < 126 else b"\x7e" + struct.pack("!H", len(raw))) + raw)


@unittest.skipUnless(os.environ.get("RECLAIMER_TEST_BINARY"), "Optional official CLI not supplied")
class UpstreamCliTests(unittest.TestCase):
    def test_quoted_arguments_survive_the_real_cli(self):
        binary = Path(os.environ["RECLAIMER_TEST_BINARY"]).resolve()
        for tokens in (["load", "The Pit", "Capture the Flag"], ["password", ""], ["say", 'special "quotes" \\ $() ; `'], ["say", "--config"]):
            with self.subTest(tokens=tokens), tempfile.TemporaryDirectory() as work, socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(1)
                listener.settimeout(10)
                port = listener.getsockname()[1]
                config = f'[rcon]\npassword = "test-only-password"\naddress = "127.0.0.1"\n[[server]]\nname = "Test"\nport = {port}\nmap = "Guardian"\ngame = "Slayer"\n'
                Path(work, "dedicated.toml").write_text(config, encoding="utf-8")
                messages, errors = [], []
                def serve():
                    try:
                        with listener.accept()[0] as stream:
                            stream.settimeout(10)
                            header = b""
                            while not header.endswith(b"\r\n\r\n"):
                                header += exact(stream, 1)
                            headers = dict(line.split(":", 1) for line in header.decode().split("\r\n")[1:] if ":" in line)
                            key = next(v.strip() for k, v in headers.items() if k.lower() == "sec-websocket-key")
                            accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
                            stream.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + accept + b"\r\n\r\n")
                            auth = frame(stream)
                            if auth.get("type") != "auth":
                                raise ValueError("Expected authentication")
                            send(stream, {"type": "auth", "ok": True, "protocol": 1, "server": "Test", "version": "0.9.13"})
                            request = frame(stream)
                            messages.append(request)
                            send(stream, {"type": "reply", "id": request.get("id"), "ok": True, "text": "Accepted", "data": {"accepted": True}})
                    except Exception as exc:
                        errors.append(str(exc))
                thread = threading.Thread(target=serve, daemon=True)
                thread.start()
                command_text(tokens)
                result = subprocess.run([str(binary), "dedicated", "rcon", "--json", "--", *tokens], cwd=work, capture_output=True, text=True, timeout=15)
                thread.join(timeout=11)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr + str(errors))
                self.assertFalse(errors)
                self.assertTrue(messages)
                request = messages[0]
                received = [request["command"], *request["args"]] if "args" in request else shlex.split(request["command"])
                self.assertEqual(received, tokens)
                self.assertEqual(json.loads(result.stdout), {"accepted": True})
