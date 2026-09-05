from pathlib import Path
import importlib.util
from importlib.machinery import SourceFileLoader
import signal
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "codex-provider"
SPEC = importlib.util.spec_from_loader(
    "codex_provider", SourceFileLoader("codex_provider", str(MODULE_PATH))
)
codex_provider = importlib.util.module_from_spec(SPEC)
sys.modules["codex_provider"] = codex_provider
SPEC.loader.exec_module(codex_provider)


class CodexProviderTests(unittest.TestCase):
    def test_managed_table_with_comment_is_replaced(self) -> None:
        text = "\n".join(
            [
                'model = "gpt-5.6-terra"',
                "",
                "[model_providers.custom]",
                'name = "Custom"',
                "",
                "[model_providers.codex-sale] # installed by codex-provider",
                'name = "Old"',
                'base_url = "https://old.example/v1"',
                "",
            ]
        )

        updated = codex_provider.configured_text(text, "anymodel")
        config = tomllib.loads(updated)

        self.assertEqual(config["model_provider"], "codex-sale")
        self.assertEqual(config["model_providers"]["codex-sale"]["base_url"], "https://anymodel.org/v1")
        self.assertEqual(config["model_providers"]["custom"]["name"], "Custom")
        self.assertEqual(updated.count("[model_providers.codex-sale]"), 1)

    def test_zcode_provider_is_created_and_model_list_is_replaced(self) -> None:
        config = {"provider": {"other": {"name": "Other", "models": {"old": {}}}}}
        selections = [
            {"provider_id": "a6api", "model_id": "gpt-5.6-terra", "proxy_id": "a6/gpt-5.6-terra"},
            {"provider_id": "openrouter-all", "model_id": "z-ai/glm-5.3", "proxy_id": "or/z-ai/glm-5.3"},
        ]
        models = {
            "a6api": {"gpt-5.6-terra": {"context_window": 200_000, "input_modalities": ["text", "image"]}},
            "openrouter-all": {"z-ai/glm-5.3": {"context_window": 100_000, "input_modalities": ["text"]}},
        }
        names = {}
        config, provider_key = codex_provider.upsert_zcode_provider(
            config, selections, models, names
        )

        provider = config["provider"][provider_key]
        self.assertEqual(provider_key, "codex-provider-manager")
        self.assertEqual(provider["options"]["baseURL"], codex_provider.PROXY_BASE_URL)
        self.assertEqual(list(provider["models"]), [item["proxy_id"] for item in selections])
        self.assertEqual(provider["models"]["a6/gpt-5.6-terra"]["limit"]["context"], 200_000)
        self.assertEqual(
            provider["models"]["a6/gpt-5.6-terra"]["modalities"]["input"],
            ["text", "image"],
        )
        self.assertEqual(config["provider"]["other"]["models"], {"old": {}})

        selections = [selections[0]]
        config, provider_key = codex_provider.upsert_zcode_provider(
            config, selections, models, names
        )
        provider = config["provider"][provider_key]
        self.assertEqual(list(provider["models"]), ["a6/gpt-5.6-terra"])
        self.assertEqual(config["provider"]["other"]["models"], {"old": {}})


class CodexProviderProxyLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.pid_path = Path(tmp.name) / "provider-proxy.pid"
        self.log_path = Path(tmp.name) / "provider-proxy.log"
        self.script_path = Path(tmp.name) / "codex-provider-proxy"
        self.script_path.write_text("", encoding="utf-8")
        self.subprocess_calls: list[list[str]] = []
        for name, value in (
            ("PROXY_PID_PATH", self.pid_path),
            ("PROXY_LOG_PATH", self.log_path),
            ("PROXY_SCRIPT_PATH", self.script_path),
        ):
            patcher = mock.patch.object(codex_provider, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def fake_subprocess_run(self, lsof_pids: str, commands: dict[int, str]):
        def run(args, **_kwargs):
            self.subprocess_calls.append(list(args))
            if args[0] == "lsof":
                return subprocess.CompletedProcess(args, 0, stdout=lsof_pids, stderr="")
            if args[0] == "ps":
                return subprocess.CompletedProcess(
                    args, 0, stdout=commands.get(int(args[2]), ""), stderr=""
                )
            raise AssertionError(f"Неожиданная команда: {args}")

        return run

    def fake_popen(self, pid: int):
        def popen(*args, **kwargs):
            process = mock.MagicMock()
            process.pid = pid
            return process

        return popen

    def fake_urlopen(self, status: int):
        urlopen = mock.MagicMock()
        urlopen.return_value.__enter__.return_value.status = status
        return urlopen

    def test_proxy_process_pid_falls_back_to_port_discovery_and_heals_file(self) -> None:
        run = self.fake_subprocess_run(
            "4242\n",
            {4242: "/opt/homebrew/bin/python3 /Users/me/.codex/bin/codex-provider-proxy --port 8765"},
        )
        with mock.patch.object(codex_provider.subprocess, "run", side_effect=run):
            self.assertEqual(codex_provider.proxy_process_pid(), 4242)

        self.assertEqual(self.pid_path.read_text(encoding="ascii"), "4242\n")

    def test_discovery_uses_lsof_on_proxy_port(self) -> None:
        run = self.fake_subprocess_run("4242\n", {4242: "python3 codex-provider-proxy"})
        with mock.patch.object(codex_provider.subprocess, "run", side_effect=run):
            self.assertEqual(codex_provider.discover_proxy_pid(), 4242)

        self.assertEqual(self.subprocess_calls[0][0], "lsof")
        self.assertIn(f"-iTCP:{codex_provider.PROXY_PORT}", self.subprocess_calls[0])
        self.assertIn("-sTCP:LISTEN", self.subprocess_calls[0])

    def test_discovery_ignores_foreign_process_on_port(self) -> None:
        run = self.fake_subprocess_run(
            "4242\n", {4242: "/Applications/Other.app/Contents/MacOS/otherd --listen"}
        )
        with mock.patch.object(codex_provider.subprocess, "run", side_effect=run):
            self.assertIsNone(codex_provider.discover_proxy_pid())
            self.assertIsNone(codex_provider.proxy_process_pid())

        self.assertFalse(self.pid_path.exists())

    def test_proxy_process_pid_falls_back_when_file_is_stale(self) -> None:
        self.pid_path.write_text("999\n", encoding="ascii")
        run = self.fake_subprocess_run("4242\n", {4242: "python3 codex-provider-proxy --port 8765"})
        with mock.patch.object(codex_provider.subprocess, "run", side_effect=run):
            self.assertEqual(codex_provider.proxy_process_pid(), 4242)

        self.assertEqual(self.pid_path.read_text(encoding="ascii"), "4242\n")

    def test_proxy_process_pid_falls_back_when_file_points_to_foreign_process(self) -> None:
        self.pid_path.write_text("999\n", encoding="ascii")
        run = self.fake_subprocess_run(
            "4242\n",
            {999: "/sbin/launchd", 4242: "python3 codex-provider-proxy"},
        )
        with mock.patch.object(codex_provider.subprocess, "run", side_effect=run):
            self.assertEqual(codex_provider.proxy_process_pid(), 4242)

        self.assertEqual(self.pid_path.read_text(encoding="ascii"), "4242\n")

    def test_proxy_is_running_uses_discovered_pid(self) -> None:
        run = self.fake_subprocess_run("4242\n", {4242: "python3 codex-provider-proxy"})
        with mock.patch.object(codex_provider.subprocess, "run", side_effect=run), mock.patch.object(
            codex_provider.os, "kill"
        ) as kill:
            self.assertTrue(codex_provider.proxy_is_running())

        kill.assert_called_once_with(4242, 0)

    def test_stop_proxy_stops_discovered_orphan(self) -> None:
        self.pid_path.write_text("999\n", encoding="ascii")
        run = self.fake_subprocess_run("4242\n", {4242: "python3 codex-provider-proxy"})
        kills: list[tuple[int, int]] = []
        alive_checks = 0

        def fake_kill(pid: int, sig: int) -> None:
            nonlocal alive_checks
            kills.append((pid, sig))
            if sig == 0:
                alive_checks += 1
                if alive_checks > 1:
                    raise ProcessLookupError

        with mock.patch.object(codex_provider.subprocess, "run", side_effect=run), mock.patch.object(
            codex_provider.os, "kill", side_effect=fake_kill
        ):
            self.assertTrue(codex_provider.stop_proxy())

        self.assertIn((4242, signal.SIGTERM), kills)
        self.assertFalse(self.pid_path.exists())

    def test_terminate_proxy_process_escalates_to_sigkill(self) -> None:
        kills: list[tuple[int, int]] = []

        def fake_kill(pid: int, sig: int) -> None:
            kills.append((pid, sig))

        with mock.patch.object(codex_provider.os, "kill", side_effect=fake_kill), mock.patch.object(
            codex_provider.time, "sleep"
        ):
            codex_provider.terminate_proxy_process(4242)

        self.assertEqual(kills[0], (4242, signal.SIGTERM))
        self.assertEqual(kills[-1], (4242, signal.SIGKILL))

    def test_start_proxy_terminates_orphan_before_start(self) -> None:
        self.pid_path.write_text("999\n", encoding="ascii")
        run = self.fake_subprocess_run("4242\n", {4242: "python3 codex-provider-proxy"})
        events: list[tuple] = []

        def fake_kill(pid: int, sig: int) -> None:
            events.append(("kill", pid, sig))
            if sig == 0:
                raise ProcessLookupError

        def popen(*args, **kwargs) -> mock.MagicMock:
            events.append(("popen", args))
            process = mock.MagicMock()
            process.pid = 5555
            return process

        with mock.patch.object(codex_provider.subprocess, "run", side_effect=run), mock.patch.object(
            codex_provider.os, "kill", side_effect=fake_kill
        ), mock.patch.object(codex_provider.subprocess, "Popen", side_effect=popen), mock.patch.object(
            codex_provider.urllib.request, "urlopen", self.fake_urlopen(200)
        ):
            self.assertTrue(codex_provider.start_proxy())

        self.assertEqual(events[0], ("kill", 4242, signal.SIGTERM))
        popen_events = [event for event in events if event[0] == "popen"]
        self.assertEqual(len(popen_events), 1)
        self.assertEqual(self.pid_path.read_text(encoding="ascii"), "5555\n")

    def test_start_proxy_keeps_running_proxy_with_valid_pid_file(self) -> None:
        self.pid_path.write_text("4242\n", encoding="ascii")
        run = self.fake_subprocess_run("", {4242: "python3 codex-provider-proxy"})
        with mock.patch.object(codex_provider.subprocess, "run", side_effect=run), mock.patch.object(
            codex_provider.subprocess, "Popen"
        ) as popen:
            self.assertFalse(codex_provider.start_proxy())

        popen.assert_not_called()
        self.assertEqual(self.pid_path.read_text(encoding="ascii"), "4242\n")

    def test_start_proxy_starts_fresh_when_nothing_listens(self) -> None:
        run = self.fake_subprocess_run("", {})
        with mock.patch.object(codex_provider.subprocess, "run", side_effect=run), mock.patch.object(
            codex_provider.subprocess, "Popen", side_effect=self.fake_popen(5555)
        ), mock.patch.object(codex_provider.urllib.request, "urlopen", self.fake_urlopen(200)):
            self.assertTrue(codex_provider.start_proxy())

        self.assertEqual(self.pid_path.read_text(encoding="ascii"), "5555\n")


if __name__ == "__main__":
    unittest.main()
