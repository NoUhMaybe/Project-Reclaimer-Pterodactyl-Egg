"""Console bridge regression checks (no Docker or game assets required)."""
import importlib.util
import pathlib
import unittest
import subprocess
import sys
import tempfile
import textwrap
import os

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("console_bridge", ROOT / "docker" / "console_bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class ConsoleBridgeTests(unittest.TestCase):
    def test_help(self):
        self.assertEqual(bridge.parse_command("help\n"), "help")

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

    def run_bridge(self, source, commands="", timeout=10, wait_for=None):
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


if __name__ == "__main__":
    unittest.main()
