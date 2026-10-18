"""Console bridge regression checks (no Docker or game assets required)."""
import importlib.util
import pathlib
import unittest
import subprocess
import sys
import tempfile
import textwrap
import os
import signal
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("console_bridge", ROOT / "docker" / "console_bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class ConsoleBridgeTests(unittest.TestCase):
    def test_help(self):
        self.assertEqual(bridge.parse_command("help\n"), "help")

    def test_manager_aliases(self):
        for value in ("menu", "manager", "console help"):
            self.assertEqual(bridge.parse_command(value), "menu")

    def test_stop_and_ctrl_c(self):
        self.assertEqual(bridge.parse_command("stop\n"), "stop")
        self.assertEqual(bridge.parse_command("\x03\n"), "stop")

    def test_quoted_map(self):
        self.assertEqual(
            bridge.parse_command('load "The Pit" "Capture the Flag"\n'),
            ["load", "The Pit", "Capture the Flag"],
        )

    def test_blank(self):
        self.assertIsNone(bridge.parse_command("  \n"))

    def test_malformed_quote(self):
        with self.assertRaises(ValueError):
            bridge.parse_command('load "Guardian\n')



@unittest.skipUnless(os.name == "posix", "Console supervisor integration requires POSIX process groups")
class ConsoleBridgeProcessTests(unittest.TestCase):
    """Exercise the bridge as a real subprocess; no Wine or assets needed."""

    def run_bridge(self, source, commands="", timeout=10, wait_for=None, send_signal=None):
        with tempfile.TemporaryDirectory() as work:
            fake = pathlib.Path(work) / "fake_server.py"
            fake.write_text(textwrap.dedent(source), encoding="utf-8")
            env = dict(os.environ, RCON_ENABLED="false", RCON_PASSWORD="")
            proc = subprocess.Popen(
                [sys.executable, "-u", str(ROOT / "docker" / "console_bridge.py"),
                 sys.executable, "-u", str(fake)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, env=env,
            )
            try:
                prefix = ""
                if wait_for:
                    while wait_for not in prefix:
                        line = proc.stdout.readline()
                        if not line:
                            break
                        prefix += line
                if send_signal is not None:
                    proc.send_signal(send_signal)
                output, _ = proc.communicate(commands, timeout=timeout)
                output = prefix + output
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                raise
            return proc.returncode, output

    def test_child_exit_code_is_preserved(self):
        code, output = self.run_bridge("import sys\nsys.exit(23)\n")
        self.assertEqual(code, 23, output)
        self.assertIn("Bridge ready", output)

    def test_stop_reaches_child_and_exits(self):
        code, output = self.run_bridge(
            """
            import signal
            import sys
            import time
            def shutdown(signum, frame):
                print("FAKE_SERVER_HANDLED_SIGINT", flush=True)
                sys.exit(0)
            signal.signal(signal.SIGINT, shutdown)
            print("FAKE_SERVER_RUNNING", flush=True)
            while True:
                time.sleep(0.02)
            """,
            commands="help\nstop\n",
            wait_for="FAKE_SERVER_RUNNING",
        )
        self.assertEqual(code, 0, output)
        self.assertIn("Stopping Project Reclaimer", output)
        self.assertIn("FAKE_SERVER_HANDLED_SIGINT", output)

    def test_rcon_disabled_returns_message(self):
        code, output = self.run_bridge(
            "import time\ntime.sleep(0.5)\n",
            commands="maps\n",
        )
        self.assertEqual(code, 0, output)
        self.assertIn("Enable RCON and set a password", output)

    def test_menu_burst_exit_and_raw_input_do_not_stop_server(self):
        code, output = self.run_bridge(
            "import time\nprint('GAME_LOG', flush=True)\ntime.sleep(1)\nprint('GAME_COMPLETED', flush=True)\n",
            commands="menu\n1\nback\nexit\nmaps\n",
        )
        self.assertEqual(code, 0, output)
        self.assertIn("CONTROL CENTER", output)
        self.assertIn("Returned to RCON", output)
        self.assertIn("Enable RCON", output)
        self.assertIn("GAME_COMPLETED", output)
        self.assertNotIn("Stopping Project", output)

    def test_eof_does_not_keep_exited_child_alive(self):
        code, output = self.run_bridge("import time,sys\ntime.sleep(.3)\nsys.exit(17)\n", commands="menu\n")
        self.assertEqual(code, 17, output)

    def test_sigint_and_sigterm_still_send_graceful_sigint(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            code, output = self.run_bridge(
                "import signal,time,sys\n"
                "def stop(sig, frame):\n print('HANDLED_SIGINT', flush=True)\n sys.exit(0)\n"
                "signal.signal(signal.SIGINT,stop)\nprint('READY',flush=True)\ntime.sleep(30)\n",
                wait_for="READY", send_signal=sig,
            )
            self.assertEqual(code, 0, output)
            self.assertIn("HANDLED_SIGINT", output)

    def test_stop_during_slow_rcon_does_not_wait_for_timeout(self):
        with tempfile.TemporaryDirectory() as work:
            area = pathlib.Path(work)
            fake = area / "dedicated"
            fake.write_text("#!" + sys.executable + "\nimport time,pathlib\npathlib.Path('rcon-started').touch()\ntime.sleep(30)\n", encoding="utf-8")
            fake.chmod(0o755)
            source = "import signal,time,sys\nsignal.signal(signal.SIGINT,lambda s,f: sys.exit(0))\nprint('READY',flush=True)\ntime.sleep(30)\n"
            env = dict(os.environ, RCON_ENABLED="true", RCON_PASSWORD="test-only", RECLAIMER_SERVER_DIR=work,
                       PATH=work + os.pathsep + os.environ["PATH"])
            proc = subprocess.Popen([sys.executable, "-u", str(ROOT / "docker/console_bridge.py"), sys.executable, "-u", "-c", source],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
            try:
                while "READY" not in proc.stdout.readline():
                    if proc.poll() is not None:
                        self.fail("Bridge exited before fake server was ready")
                proc.stdin.write("status\n")
                proc.stdin.flush()
                deadline = time.monotonic() + 5
                while not (area / "rcon-started").exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue((area / "rcon-started").exists())
                started = time.monotonic()
                output, _ = proc.communicate("stop\n", timeout=5)
                self.assertEqual(proc.returncode, 0, output)
                self.assertLess(time.monotonic() - started, 3)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.communicate()


if __name__ == "__main__":
    unittest.main()
