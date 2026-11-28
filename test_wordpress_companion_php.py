"""Execute the companion PHP against controlled WordPress/wpdb stubs, not a site."""
import os
from pathlib import Path
import shutil
import subprocess
import unittest

PHP = os.environ.get('FILIP_GUARD_PHP_BINARY') or shutil.which('php')
ROOT = Path(__file__).resolve().parent


@unittest.skipUnless(PHP, 'PHP runtime unavailable; PHP checks are required in GitHub Actions')
class CompanionPHPTests(unittest.TestCase):
    def test_php_syntax(self):
        for path in ('wordpress_companion/filip-guard-companion.php', 'tests/php/companion_harness.php'):
            result = subprocess.run([PHP, '-n', '-l', str(ROOT / path)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def run_scenario(self, scenario):
        result = subprocess.run([PHP, '-n', str(ROOT / 'tests/php/companion_harness.php'), scenario],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), 'PASS ' + scenario)
        self.assertNotIn('fictitious-never-retained', result.stdout + result.stderr)

    def test_unsupported_content_profile_is_blocked_before_write(self):self.run_scenario('unsupported_profile')
    def test_production_exact_href_profile(self):self.run_scenario('production_link_profile')
    def test_default_gate(self): self.run_scenario('disabled')
    def test_production_gate(self): self.run_scenario('production')
    def test_https_required(self): self.run_scenario('http')
    def test_cookie_auth_rejected(self): self.run_scenario('cookie')
    def test_resource_permission_required(self): self.run_scenario('forbidden')
    def test_invalid_payload_rejected(self): self.run_scenario('invalid_payload')
    def test_stale_snapshot_rejected(self): self.run_scenario('stale')
    def test_atomic_race_preserves_other_edit(self): self.run_scenario('race')
    def test_database_failure(self): self.run_scenario('database_error')
    def test_later_change_not_reported_as_success(self): self.run_scenario('later_change')
    def test_lost_receipt_pending_operation_not_repeated(self): self.run_scenario('lost_receipt')
    def test_write_receipt_and_idempotency(self): self.run_scenario('success')
    def test_conditional_rollback(self): self.run_scenario('rollback')
    def test_rollback_race(self): self.run_scenario('rollback_race')
