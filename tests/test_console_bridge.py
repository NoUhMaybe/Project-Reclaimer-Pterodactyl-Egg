"""Console bridge regression checks (no Docker or game assets required)."""
import importlib.util
import pathlib
import unittest

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


if __name__ == "__main__":
    unittest.main()
