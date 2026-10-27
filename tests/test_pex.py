"""Regression tests: no actual printer, service, update, or network is invoked."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pex import config, updater
from pex.jobs import JobManager, QueueFullError
from pex.services import printer, server, service_linux, service_windows


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="pex-tests-")
        self.root = Path(self.directory.name)
        self.settings = config._default_config()
        self.settings["printers"] = {"labels": "Warehouse"}
        self.settings["printer_default"] = "labels"
        self.settings["server"].update(token="test-token", cors=["https://warehouse.example"])
        def option(name, default=""):
            from pex.utils import deep_get
            return deep_get(self.settings, name, default)
        self.patches = [patch.object(config, "get_option", side_effect=option),
                        patch.object(config, "ROOT_PATH", self.root),
                        patch.object(printer, "list_printers", return_value=["Warehouse"]),
                        patch.dict(os.environ, {"PEX_API_TOKEN": ""})]
        for item in self.patches:
            item.start()

    def tearDown(self):
        manager = server.app.extensions.pop("pex_jobs", None)
        if manager:
            manager.close()
        for item in reversed(self.patches):
            item.stop()
        self.directory.cleanup()

    def client(self):
        return server.app.test_client()

    def post(self, data=None, headers=None):
        response = self.client().post("/pex/print", data=data or {"lines": "Test", "paper_format": "label"},
            headers={"Authorization": "Bearer test-token", **(headers or {})})
        # Werkzeug may spool multipart test bodies to disk before invoking Flask.
        # Rejected requests do not consume that stream; the test owns its lifetime.
        response.request.environ["wsgi.input"].close()
        return response

    def test_quantity_invalid_returns_json_400(self):
        response = self.post({"lines": "x", "quantity": "bad"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["code"], "validation_failed")

    def test_quantity_bounds(self):
        for value in ("0", "-1", "101", "1.5"):
            with self.subTest(value=value):
                self.assertEqual(self.post({"lines": "x", "quantity": value}).status_code, 400)

    @patch.object(printer, "print_file", return_value={"backend": "mock", "spooler_ids": []})
    def test_documented_format_and_legacy_alias(self, submit):
        for field in ("paper_format", "format"):
            response = self.post({"lines": "Test", field: "label"})
            self.assertEqual(response.status_code, 200, response.json)
            self.assertEqual(submit.call_args.kwargs["paper_format"], [51.0, 25.0])
            self.assertEqual(response.json["result"]["job"]["state"], "submitted")
            self.assertNotIn("filepath", response.json["result"]["arguments"])

    def test_conflicting_formats_rejected(self):
        response = self.post({"lines": "x", "format": "A4", "paper_format": "label"})
        self.assertEqual(response.status_code, 400)

    @patch.object(printer, "print_file", return_value={"backend": "mock"})
    def test_numeric_dimensions(self, submit):
        response = self.post({"lines": "x", "paper_format": "[51,25]"})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(submit.call_args.kwargs["paper_format"], [51.0, 25.0])

    def test_dimension_bounds(self):
        for value in ("[0,25]", "[51,-1]", "[51,25,1]", "[51,NaN]", "[true,25]"):
            self.assertEqual(self.post({"lines": "x", "paper_format": value}).status_code, 400)

    def test_authentication(self):
        for endpoint in ("/pex/status", "/pex/printers", "/pex/jobs/unknown"):
            self.assertEqual(self.client().get(endpoint).status_code, 401)
        self.assertEqual(self.post(headers={"Authorization": "Bearer wrong"}).status_code, 401)

    def test_printer_listing_includes_aliases_and_resolved_default(self):
        self.settings["printers"] = {"labels": "Warehouse", "shipping": "Warehouse", "offline": "Offline printer"}
        response = self.client().get("/pex/printers", headers={"Authorization": "Bearer test-token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["result"], {
            "printers": ["Warehouse"], "aliases": self.settings["printers"], "printer_default": "Warehouse"})

    def test_printer_listing_without_aliases_or_default(self):
        self.settings["printers"] = {}
        self.settings["printer_default"] = None
        response = self.client().get("/pex/printers", headers={"Authorization": "Bearer test-token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["result"], {
            "printers": ["Warehouse"], "aliases": {}, "printer_default": None})

    def test_missing_token_fails_closed(self):
        self.settings["server"]["token"] = ""
        self.assertEqual(self.post().status_code, 503)

    def test_origin_is_enforced_before_print(self):
        with patch.object(printer, "print_file") as submit:
            self.assertEqual(self.post(headers={"Origin": "https://evil.example"}).status_code, 403)
            self.assertEqual(self.post(headers={"Origin": "null"}).status_code, 403)
            submit.assert_not_called()

    def test_preflight(self):
        response = self.client().options("/pex/print", headers={"Origin": "https://warehouse.example",
            "Access-Control-Request-Method": "POST", "Access-Control-Request-Private-Network": "true"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "https://warehouse.example")
        self.assertEqual(response.headers["Access-Control-Allow-Private-Network"], "true")
        self.assertIn("Idempotency-Key", response.headers["Access-Control-Allow-Headers"])

    def test_http_errors_are_json(self):
        response = self.client().get("/not-found", headers={"Authorization": "Bearer test-token"})
        self.assertEqual(response.status_code, 404)
        self.assertTrue(response.is_json)

    def test_upload_limit(self):
        self.settings["server"]["max_upload_mb"] = 1
        response = self.post({"file": (io.BytesIO(b"%PDF-" + b"x" * (1024 * 1024)), "a.pdf")})
        self.assertEqual(response.status_code, 413)
        self.assertTrue(response.is_json)

    def test_exactly_one_source(self):
        self.assertEqual(self.post({"file": (io.BytesIO(b"%PDF-1.4"), "a.pdf"), "lines": "x"}).status_code, 400)
        self.assertEqual(self.post({"printer": "labels"}).status_code, 400)

    def test_non_pdf_rejected_and_cleaned(self):
        self.assertEqual(self.post({"file": (io.BytesIO(b"not a PDF"), "x.pdf")}).status_code, 400)
        self.assertFalse(list((self.root / "temp").glob("pex-job-*")))

    def test_unknown_printer(self):
        self.assertEqual(self.post({"lines": "x", "printer": "missing"}).status_code, 400)

    @patch.object(printer, "print_file", return_value={"backend": "mock"})
    def test_idempotent_replay_and_conflict(self, submit):
        first = self.post(headers={"Idempotency-Key": "order-1"})
        second = self.post(headers={"Idempotency-Key": "order-1"})
        self.assertEqual(first.status_code, 200, first.json)
        self.assertEqual(first.json["result"]["job"]["id"], second.json["result"]["job"]["id"])
        self.assertTrue(second.json["result"]["replayed"])
        self.assertEqual(submit.call_count, 1)
        conflict = self.post({"lines": "different", "paper_format": "label"}, {"Idempotency-Key": "order-1"})
        self.assertEqual(conflict.status_code, 409)
        self.assertFalse(list((self.root / "temp").glob("pex-job-*")))

    def test_asynchronous_status(self):
        gate = threading.Event()
        with patch.object(printer, "print_file", side_effect=lambda **kw: gate.wait(2) or {}):
            try:
                response = self.post(headers={"Prefer": "respond-async"})
                self.assertEqual(response.status_code, 202, response.json)
                location = response.headers["Location"]
                status = self.client().get(location, headers={"Authorization": "Bearer test-token"})
                self.assertEqual(status.status_code, 200)
                self.assertIn(status.json["result"]["job"]["state"], ("queued", "processing"))
            finally:
                gate.set()
                server.app.extensions["pex_jobs"].wait(response.json["result"]["job"]["id"], 2)

    @patch.object(printer, "print_file", side_effect=subprocess.TimeoutExpired("mock", 1))
    def test_uncertain_submission_never_retried(self, submit):
        for _ in range(2):
            response = self.post(headers={"Idempotency-Key": "uncertain"})
            self.assertEqual(response.status_code, 502, response.json)
            self.assertEqual(response.json["details"]["job"]["state"], "unknown")
        self.assertEqual(submit.call_count, 1)

    @patch.object(printer, "print_file", return_value={})
    def test_identical_upload_names_are_isolated(self, submit):
        for _ in range(2):
            response = self.post({"file": (io.BytesIO(b"%PDF-1.4 dummy"), "same.pdf")})
            self.assertEqual(response.status_code, 200)
        paths = [call.kwargs["filepath"] for call in submit.call_args_list]
        self.assertEqual(len(set(paths)), 2)


class PrinterTest(unittest.TestCase):
    def setUp(self):
        self.option = patch.object(config, "get_option", side_effect=lambda key, default="": {"server.process_timeout": 10,
            "linux_command": "-n", "formats": {"label": [51, 25]}}.get(key, default))
        self.option.start()

    def tearDown(self):
        self.option.stop()

    def test_linux_submits_once_with_options(self):
        with patch.object(printer.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="request id is p-42")) as run:
            result = printer._print_on_linux("fake.pdf", "P", (51, 25), "landscape", 3)
            self.assertEqual(run.call_count, 1)
            command = run.call_args.args[0]
            self.assertIn("media=Custom.51x25mm", command)
            self.assertIn("orientation-requested=4", command)
            self.assertEqual(command[command.index("-n") + 1], "3")
            self.assertEqual(result["spooler_ids"], ["p-42"])
            self.assertEqual(run.call_args.kwargs["timeout"], 10)

    def test_linux_legacy_modes(self):
        for mode, count in (("for", 3), ("-o", 1)):
            with self.subTest(mode=mode), patch.object(config, "get_option", side_effect=lambda key, default="": mode if key == "linux_command" else 10), patch.object(printer.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="request id is p-1")) as run:
                printer._print_on_linux("x.pdf", "P", (51,25), "portrait", 3)
                self.assertEqual(run.call_count, count)
                if mode == "-o":
                    self.assertIn("copies=3", run.call_args.args[0])

    def test_windows_uses_per_job_settings(self):
        api = MagicMock()
        api.GetPrinter.return_value = {"pPortName": "PORT"}
        api.DeviceCapabilities.side_effect = [[256], [{"x": 510, "y": 250}]]
        with patch.object(printer, "win32print", api, create=True), patch.object(printer, "_get_sumatra_path", return_value="sumatra.exe"), patch.object(printer.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
            printer._print_on_windows("x.pdf", "P", (51,25), "landscape", 3)
            api.SetPrinter.assert_not_called()
            api.OpenPrinter.assert_any_call("P")
            self.assertIn("noscale,landscape,3x,paper=256", run.call_args.args[0])
            self.assertNotIn("-exit-on-print", run.call_args.args[0])

    def test_windows_missing_form_uses_validated_pdf_size(self):
        api = MagicMock()
        api.GetPrinter.return_value = {"pPortName": "PORT"}
        api.DeviceCapabilities.side_effect = [[], []]
        with patch.object(printer, "win32print", api, create=True), patch.object(printer, "_validate_pdf_paper") as validate, patch.object(printer, "_get_sumatra_path", return_value="sumatra.exe"), patch.object(printer.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
            printer._print_on_windows("x.pdf", "P", (51,25), "portrait", 1)
            validate.assert_called_once_with("x.pdf", (51,25), "portrait")
            self.assertIn("noscale,1x,paperkind=0", run.call_args.args[0])
            api.SetPrinter.assert_not_called()
            api.AddForm.assert_not_called()

    def test_render_german_and_styles(self):
        content = printer.render_lines([{"text": "Größe: äöü ß €", "bold": True, "size": 8}], "label")
        self.assertTrue(content.startswith(b"%PDF-"))

    def test_blank_lines_and_long_words(self):
        pdf = printer.FPDF()
        pdf.add_page()
        pdf.set_font("helvetica", size=10)
        wrapped = printer._wrap_text({"text": "\nABCDEFGHIJKLMNOPQRSTUV\n"}, pdf, 12)
        self.assertEqual(wrapped[0]["text"], "")
        self.assertEqual(wrapped[-1]["text"], "")
        self.assertTrue(all(pdf.get_string_width(line["text"]) <= 12 for line in wrapped))
        self.assertEqual("".join(line["text"] for line in wrapped), "ABCDEFGHIJKLMNOPQRSTUV")

    def test_render_rejects_overflow_and_unsupported_text(self):
        for lines in ([{"text": "x"}] * 100, [{"text": "漢字"}], [{"text": "x", "font": "missing"}], [{"text": "x", "size": float("nan")}], [{"text": "x", "bold": "yes"}]):
            with self.subTest(lines=lines[:1]), self.assertRaises(ValueError):
                printer.render_lines(lines, "label")

    def test_landscape_uses_actual_page_dimensions(self):
        positions = []
        original = printer.FPDF.text
        def capture(pdf, **kwargs):
            positions.append((pdf.w, pdf.h, kwargs["x"], pdf.get_string_width(kwargs["text"])))
            return original(pdf, **kwargs)
        with patch.object(printer.FPDF, "text", capture):
            printer.render_lines([{"text": "Centered", "size": 8}], "label", "landscape")
        width, height, x, text_width = positions[0]
        self.assertAlmostEqual(x, (width - text_width) / 2)
        self.assertGreater(width, height)

    def test_direct_file_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "original.pdf"
            path.write_bytes(b"%PDF-1.4")
            with patch.object(printer, "validate_options", return_value=("P", (51,25), "portrait")), patch.object(printer, "_print_on_windows", return_value={}), patch.object(printer, "_print_on_linux", return_value={}):
                printer.print_file(str(path), "P", "label")
            self.assertTrue(path.exists())


class JobTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="pex-jobs-")
        self.root = Path(self.directory.name)
        self.manager = JobManager(self.root / "jobs.db", limit=2)
        self.arguments = {"printer_name": "A", "paper_format": [51,25], "orientation": "portrait", "quantity": 1}

    def tearDown(self):
        self.manager.close()
        self.directory.cleanup()

    def file(self, name):
        path = self.root / name
        path.write_bytes(b"%PDF-1.4")
        return str(path)

    def test_queue_bound_and_fifo(self):
        gate = threading.Event()
        seen = []
        def submit(**kwargs):
            seen.append(Path(kwargs["filepath"]).name)
            gate.wait(2)
            return {}
        with patch.object(printer, "print_file", side_effect=submit):
            first, _ = self.manager.submit(self.file("1.pdf"), self.arguments, "1")
            second, _ = self.manager.submit(self.file("2.pdf"), self.arguments, "2")
            with self.assertRaises(QueueFullError):
                self.manager.submit(self.file("3.pdf"), self.arguments, "3")
            gate.set()
            self.manager.wait(second["id"], 2)
            self.assertEqual(seen, ["1.pdf", "2.pdf"])
            self.assertEqual(self.manager.get(first["id"])["state"], "submitted")

    def test_other_printer_is_not_blocked(self):
        gate = threading.Event()
        def submit(**kwargs):
            if kwargs["printer_name"] == "A":
                gate.wait(2)
            return {}
        with patch.object(printer, "print_file", side_effect=submit):
            self.manager.submit(self.file("a.pdf"), self.arguments, "a")
            job, _ = self.manager.submit(self.file("b.pdf"), {**self.arguments, "printer_name": "B"}, "b")
            try:
                self.assertEqual(self.manager.wait(job["id"], 1)["state"], "submitted")
            finally:
                gate.set()
                self.manager.close()

    def test_restart_retains_deduplication_without_reprinting(self):
        with patch.object(printer, "print_file", return_value={}) as submit:
            job, _ = self.manager.submit(self.file("a.pdf"), self.arguments, "same", "stable-key")
            self.manager.wait(job["id"], 2)
            self.manager.close()
            self.manager = JobManager(self.root / "jobs.db")
            duplicate, replay = self.manager.submit(self.file("b.pdf"), self.arguments, "same", "stable-key")
            self.assertTrue(replay)
            self.assertEqual(duplicate["id"], job["id"])
            self.assertEqual(submit.call_count, 1)

    def test_incomplete_job_becomes_unknown(self):
        self.manager.db.execute("INSERT INTO jobs VALUES ('interrupted',NULL,'f','A','processing',0,0,NULL,NULL)")
        self.manager.db.commit()
        self.manager.close()
        self.manager = JobManager(self.root / "jobs.db")
        self.assertEqual(self.manager.get("interrupted")["state"], "unknown")
        self.assertEqual(self.manager.get("interrupted")["error_code"], "service_restarted")


class ConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="pex-config-")
        self.root = Path(self.directory.name)
        self.patches = [patch.object(config, "CONFIG_FILE", self.root / "config.json"),
                        patch.object(config, "LEGACY_CONFIG_FILE", self.root / "pexconfig.json")]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.directory.cleanup()

    def test_atomic_updates_keep_existing_values(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: config.set_option(f"custom.key{i}", i), range(20)))
        self.assertEqual(len(config.load_config()["custom"]), 20)
        self.assertFalse(list(self.root.glob(".pex-config-*")))

    def test_invalid_save_preserves_previous_config(self):
        config.set_option("server.port", 4422)
        before = config.CONFIG_FILE.read_bytes()
        with self.assertRaises(ValueError):
            config.set_option("server.port", 0)
        self.assertEqual(config.CONFIG_FILE.read_bytes(), before)

    def test_related_options_saved_together(self):
        config.set_options({"printers": {"labels": "P"}, "printer_default": "labels"})
        data = json.loads(config.CONFIG_FILE.read_text())
        self.assertEqual(data["printer_default"], "labels")
        self.assertEqual(data["printers"], {"labels": "P"})

    def test_legacy_source_is_preserved(self):
        config.LEGACY_CONFIG_FILE.write_text('{"file_printer":"P"}')
        self.assertEqual(config.load_config()["printers"]["file"], "P")
        self.assertTrue(config.LEGACY_CONFIG_FILE.exists())

    def test_defaults_are_packaged(self):
        self.assertEqual(config._default_config()["server"]["host"], "127.0.0.1")

    def test_separate_processes_do_not_lose_updates(self):
        environment = {**os.environ, "PEX_DATA_DIR": str(self.root),
                       "PYTHONPATH": str(Path(config.__file__).resolve().parents[1])}
        children = [subprocess.Popen([sys.executable, "-B", "-c",
            f"from pex import config; config.set_option('parallel.key{i}', {i})"],
            env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(4)]
        for child in children:
            _, error = child.communicate(timeout=15)
            self.assertEqual(child.returncode, 0, error.decode(errors="replace"))
        self.assertEqual(len(config.load_config()["parallel"]), 4)


class ServiceTest(unittest.TestCase):
    def test_missing_pm2_always_returns_tuple(self):
        with patch.object(service_linux, "_ensure_pm2", return_value=(False, "missing")):
            for method in (service_linux.start, service_linux.stop, service_linux.restart, service_linux.status):
                self.assertEqual(method(), (False, "missing"))

    def test_windows_install_checks_every_configuration_step(self):
        with patch.object(service_windows.NSSM_PATH.__class__, "exists", return_value=True), patch.object(service_windows.os, "makedirs"), patch.object(service_windows.subprocess, "run", side_effect=[SimpleNamespace(returncode=0), subprocess.CalledProcessError(1,"nssm")]):
            self.assertFalse(service_windows.install()[0])

    def test_windows_status_has_timeout_without_shell(self):
        with patch.object(service_windows.os.path, "exists", return_value=True), patch.object(service_windows.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="SERVICE_RUNNING", stderr="")) as run:
            self.assertTrue(service_windows.is_running())
            self.assertEqual(run.call_args.kwargs["timeout"], 30)
            self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_cli_does_not_import_tkinter(self):
        script = "import sys; sys.modules['tkinter']=None; from pex.cli import main; main(['--version'])"
        result = subprocess.run([sys.executable, "-B", "-c", script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0.5.1", result.stdout)


class UpdaterTest(unittest.TestCase):
    def test_metadata_refresh_preserves_running_console_launcher(self):
        with tempfile.TemporaryDirectory(prefix="pex-registration-test-") as folder:
            root = Path(folder)
            purelib, scripts, recovery = root / "site-packages", root / "Scripts", root / "recovery"
            purelib.mkdir()
            scripts.mkdir()
            launcher = scripts / ("pex.exe" if os.name == "nt" else "pex")
            launcher.write_bytes(b"original launcher must stay unchanged")
            old = purelib / "pex-0.4.1.dist-info"
            old.mkdir()
            (old / "METADATA").write_text("Name: PEX\nVersion: 0.4.1\n")
            unrelated = purelib / "pex-tools-1.0.dist-info"
            unrelated.mkdir()
            (purelib / "__editable__.pex-0.4.1.pth").write_text("old-path")
            def install(cmd, **kwargs):
                target = Path(cmd[cmd.index("--target") + 1])
                metadata = target / "pex-0.5.0.dist-info"
                metadata.mkdir()
                (metadata / "entry_points.txt").write_text("[console_scripts]\npex = pex.cli:main\n")
                (metadata / "RECORD").write_text("bin/pex.exe,,\n")
                (target / "__editable__.pex-0.5.0.pth").write_text("new-path")
                return SimpleNamespace(stdout="")
            with patch.object(updater.sysconfig, "get_path", side_effect=lambda name: str(purelib if name == "purelib" else scripts)), patch.object(updater, "_run", side_effect=install):
                updater._install_editable(recovery)
            self.assertEqual(launcher.read_bytes(), b"original launcher must stay unchanged")
            self.assertFalse(old.exists())
            self.assertTrue(unrelated.exists())
            self.assertTrue((purelib / "pex-0.5.0.dist-info").is_dir())
            record = (purelib / "pex-0.5.0.dist-info/RECORD").read_text()
            self.assertIn("sha256=", record)
            self.assertNotIn("bin/pex.exe", record)

    def test_dirty_checkout_never_stops_service(self):
        with patch.object(updater, "FileLock"), patch.object(updater.Path, "exists", return_value=True), patch.object(updater, "_run", return_value=SimpleNamespace(stdout=" M local.py")), patch.object(updater.service, "stop") as stop:
            self.assertFalse(updater.perform(lambda message: None))
            stop.assert_not_called()

    def test_commands_use_project_directory_and_clean_git_environment(self):
        with patch.dict(os.environ, {"GIT_DIR": "wrong"}), patch.object(updater.subprocess, "run", return_value=SimpleNamespace()) as run:
            updater._run(["git", "status"])
            self.assertEqual(run.call_args.kwargs["cwd"], updater.PROJECT_PATH)
            self.assertNotIn("GIT_DIR", run.call_args.kwargs["env"])

    def test_deployment_failure_still_restarts_previous_service(self):
        with tempfile.TemporaryDirectory(prefix="pex-updater-test-") as folder:
            root = Path(folder)
            (root / ".git").mkdir()
            deployed = False
            def command(cmd, **kwargs):
                nonlocal deployed
                if cmd[:3] == ["git", "rev-parse", "HEAD"]:
                    return SimpleNamespace(stdout="previous")
                if cmd[:2] == ["git", "rev-parse"]:
                    return SimpleNamespace(stdout="candidate")
                if cmd[:2] == ["git", "archive"]:
                    archive = next(value[9:] for value in cmd if value.startswith("--output="))
                    with zipfile.ZipFile(archive, "w") as bundle:
                        bundle.writestr("requirements.lock", "")
                if cmd[:2] == ["git", "merge"]:
                    deployed = True
                if deployed and "pip" in cmd:
                    raise subprocess.CalledProcessError(1, cmd)
                return SimpleNamespace(stdout="")
            with patch.object(updater, "ROOT_PATH", root), patch.object(updater, "PROJECT_PATH", root), patch.object(updater, "_run", side_effect=command), patch.object(updater.service, "is_installed", return_value=True), patch.object(updater.service, "is_running", return_value=True), patch.object(updater.service, "stop", return_value=(True,"stopped")) as stop, patch.object(updater.service, "start", return_value=(True,"started")) as start:
                messages = []
                self.assertFalse(updater.perform(messages.append))
                stop.assert_called_once()
                start.assert_called_once()
                self.assertTrue(list((root / "recovery").glob("*/previous.zip")))

    def test_preflight_failure_never_stops_service(self):
        with patch.object(updater, "FileLock"), patch.object(updater.Path, "exists", return_value=True), patch.object(updater, "_run", side_effect=[SimpleNamespace(stdout=""), SimpleNamespace(stdout="previous"), subprocess.CalledProcessError(1,"git fetch")]), patch.object(updater.service, "stop") as stop:
            self.assertFalse(updater.perform(lambda message: None))
            stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
