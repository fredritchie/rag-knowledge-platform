from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/deploy_application_release.sh"


class DeploymentBootstrapTests(unittest.TestCase):
    def run_deployment(self, status: str, fail_bootstrap: bool = False):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            mock = f"""#!{sys.executable}
import json, os, sys
from pathlib import Path
with open(os.environ['CALL_LOG'], 'a') as log:
    log.write(json.dumps([Path(sys.argv[0]).name, *sys.argv[1:]]) + '\\n')
if sys.argv[1] == 'status':
    status = os.environ['TEST_STATUS']
    if status == 'missing':
        print('Error: release: not found', file=sys.stderr)
        sys.exit(1)
    if status == 'unreachable':
        print('Error: Kubernetes cluster unreachable', file=sys.stderr)
        sys.exit(1)
    print(json.dumps({{'info': {{'status': status}}}}))
if 'replicaCount.frontend=0' in sys.argv and os.environ['FAIL_BOOTSTRAP'] == '1':
    sys.exit(1)
"""
            for name in ("helm", "kubectl"):
                executable = work / name
                executable.write_text(mock)
                executable.chmod(0o755)
            log = work / "calls.jsonl"
            result = subprocess.run(
                ["bash", str(SCRIPT), "environment.yaml", "images.yaml"],
                cwd=ROOT,
                env={
                    **os.environ,
                    "PATH": f"{work}:{os.environ['PATH']}",
                    "CALL_LOG": str(log),
                    "TEST_STATUS": status,
                    "FAIL_BOOTSTRAP": "1" if fail_bootstrap else "0",
                },
                capture_output=True,
                text=True,
                check=False,
            )
            return result, [json.loads(line) for line in log.read_text().splitlines()]

    def test_fresh_install_migrates_with_workloads_and_keda_disabled(self):
        result, calls = self.run_deployment("missing")
        self.assertEqual(result.returncode, 0, result.stderr)
        upgrades = [call for call in calls if call[:2] == ["helm", "upgrade"]]
        self.assertEqual(len(upgrades), 2)
        for component in ("frontend", "api", "ingestionWorker", "driveSync"):
            self.assertIn(f"replicaCount.{component}=0", upgrades[0])
        self.assertIn("keda.enabled=false", upgrades[0])
        self.assertIn("--atomic", upgrades[0])
        self.assertIn("--wait", upgrades[0])
        self.assertIn("--reset-values", upgrades[1])
        self.assertNotIn("keda.enabled=false", upgrades[1])
        self.assertFalse(any("replicaCount." in arg for arg in upgrades[1]))
        self.assertEqual(sum(call[0] == "kubectl" for call in calls), 4)

    def test_existing_release_does_not_scale_down_for_bootstrap(self):
        for status in ("deployed", "failed"):
            with self.subTest(status=status):
                result, calls = self.run_deployment(status)
                self.assertEqual(result.returncode, 0, result.stderr)
                upgrades = [call for call in calls if call[:2] == ["helm", "upgrade"]]
                self.assertEqual(len(upgrades), 1)
                self.assertFalse(any("replicaCount." in arg for arg in upgrades[0]))

    def test_failed_bootstrap_never_starts_application(self):
        result, calls = self.run_deployment("missing", fail_bootstrap=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sum(call[:2] == ["helm", "upgrade"] for call in calls), 1)
        self.assertFalse(any(call[0] == "kubectl" for call in calls))

    def test_unreachable_or_busy_cluster_does_not_trigger_install(self):
        for status in ("unreachable", "pending-install", "pending-upgrade"):
            with self.subTest(status=status):
                result, calls = self.run_deployment(status)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(call[:2] == ["helm", "upgrade"] for call in calls))

    @unittest.skipUnless(shutil.which("helm"), "Helm required for render test")
    def test_bootstrap_manifest_keeps_migration_prerequisites(self):
        args = ["helm", "template", "rag-platform", str(ROOT / "helm/rag-platform")]
        for image in ("frontend", "api", "ingestionWorker", "driveSync", "ollamaRuntime", "qdrant"):
            args += ["--set-string", f"images.{image}.digest=sha256:{'a' * 64}"]
        for component in ("frontend", "api", "ingestionWorker", "driveSync"):
            args += ["--set", f"replicaCount.{component}=0"]
        args += [
            "--set",
            "keda.enabled=false",
            "--set",
            "externalSecrets.enabled=true",
            "--set-string",
            "externalSecrets.databaseSecretArn=test-database-secret",
        ]
        result = subprocess.run(args, check=True, capture_output=True, text=True)
        docs = result.stdout.split("\n---")
        deployments = [doc for doc in docs if "kind: Deployment\n" in doc]
        self.assertEqual(len(deployments), 4)
        self.assertTrue(all("replicas: 0" in doc for doc in deployments))
        self.assertNotIn("kind: ScaledObject\n", result.stdout)
        for kind in ("Job", "ServiceAccount", "ExternalSecret", "NetworkPolicy"):
            self.assertIn(f"kind: {kind}\n", result.stdout)
        self.assertIn("helm.sh/hook: post-install,pre-upgrade", result.stdout)


if __name__ == "__main__":
    unittest.main()
