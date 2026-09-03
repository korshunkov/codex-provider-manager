import importlib.util
from importlib.machinery import SourceFileLoader
import unittest
from pathlib import Path


WATCH_PATH = Path(__file__).resolve().parents[1] / "src" / "codex-power-watch"
spec = importlib.util.spec_from_file_location(
    "codex_power_watch",
    WATCH_PATH,
    loader=SourceFileLoader("codex_power_watch", str(WATCH_PATH)),
)
codex_power_watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(codex_power_watch)


class CodexPowerWatchTests(unittest.TestCase):
    def test_detects_active_chatgpt_task(self) -> None:
        output = '   pid 40426(ChatGPT): [0x123] NoIdleSleepAssertion named: "Electron"'
        self.assertTrue(codex_power_watch.is_active_codex_assertion(output))

    def test_ignores_assertions_from_other_processes(self) -> None:
        output = '   pid 40426(WindowServer): [0x123] NoIdleSleepAssertion named: "User"'
        self.assertFalse(codex_power_watch.is_active_codex_assertion(output))

    def test_sleeps_only_after_long_network_loss_once(self) -> None:
        self.assertFalse(codex_power_watch.should_sleep_for_network_loss(59, False))
        self.assertTrue(codex_power_watch.should_sleep_for_network_loss(60, False))
        self.assertFalse(codex_power_watch.should_sleep_for_network_loss(90, True))


if __name__ == "__main__":
    unittest.main()
