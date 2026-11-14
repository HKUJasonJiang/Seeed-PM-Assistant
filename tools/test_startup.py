import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import bootstrap
import startup_report
import launch


class StartupTests(unittest.TestCase):
    def test_slow_service_is_pending_and_can_reconnect(self):
        from types import SimpleNamespace
        args=SimpleNamespace(data_dir=Path("unused"))
        child=SimpleNamespace(poll=lambda:None)
        with patch.object(launch,"open_existing",return_value=None),patch.object(launch.time,"monotonic",side_effect=[0,61]),patch.object(launch,"record") as message:
            self.assertEqual(launch.await_startup(args,child),2)
        self.assertEqual(message.call_args.args[0],"STARTING")
        with patch.object(launch,"open_existing",return_value=0),patch.object(launch.time,"monotonic",side_effect=[0,1]):
            self.assertEqual(launch.await_startup(args,child),0)

    def test_dependency_failure_has_a_safe_actionable_code(self):
        result=subprocess.CompletedProcess([],1,"ProxyError https://secret-user:secret-token@example.invalid")
        with patch.object(bootstrap.subprocess,"run",return_value=result),patch.object(bootstrap,"record") as message:
            with self.assertRaises(RuntimeError):bootstrap.install(["pip"],"PACKAGE")
        self.assertEqual(message.call_args.args,("NETWORK","exit=1"))

    def test_certificate_failure_does_not_suggest_bypassing_validation(self):
        result=subprocess.CompletedProcess([],1,"CERTIFICATE_VERIFY_FAILED")
        with patch.object(bootstrap.subprocess,"run",return_value=result),patch.object(bootstrap,"record") as message:
            with self.assertRaises(RuntimeError):bootstrap.install(["pip"],"PACKAGE")
        self.assertEqual(message.call_args.args[0],"CERTIFICATE")

    def test_raw_exception_and_private_path_are_not_saved(self):
        scratch=Path(__file__).resolve().parents[1]/"tmp"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            report=Path(directory)/"report.txt"
            with patch.object(startup_report,"REPORT",report):
                startup_report.failure(PermissionError("Private credentials here"),"ACCESS")
            text=report.read_text("utf-8")
            self.assertIn("ACCESS",text)
            self.assertNotIn("Private",text)


if __name__=="__main__":unittest.main()
