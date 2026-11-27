from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from advisor_ledger import require_existing_advisor_ledger,validate_budget_history


class ExistingAdvisorLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'advisor.sqlite'
        with sqlite3.connect(self.path) as db:
            db.executescript('''CREATE TABLE advisor_requests(scope TEXT,request_hash TEXT,started REAL,expires REAL,day INTEGER,state TEXT,result TEXT);
            CREATE TABLE advisor_budget(day INTEGER PRIMARY KEY,calls INTEGER NOT NULL);
            CREATE TABLE advisor_provider_cooldown(provider TEXT PRIMARY KEY,observed REAL,blocked_until REAL,source TEXT,diagnostic TEXT);
            INSERT INTO advisor_requests VALUES ('synthetic','hash',86400,86430,1,'complete','{}');
            INSERT INTO advisor_budget VALUES (1,17);''')
        self.path.chmod(0o600)
    def change(self,sql):
        with sqlite3.connect(self.path) as db:db.executescript(sql)
    def assert_held_unchanged(self):
        before=self.path.read_bytes()
        with self.assertRaises(ValueError):require_existing_advisor_ledger(self.path)
        self.assertEqual(self.path.read_bytes(),before)
    def test_retained_conservative_hold_above_surviving_requests_is_valid(self):
        before=self.path.read_bytes();require_existing_advisor_ledger(self.path)
        self.assertEqual(self.path.read_bytes(),before)
    def test_missing_budget_table_is_not_created(self):
        self.change('DROP TABLE advisor_budget');self.assert_held_unchanged()
    def test_missing_day_counter_is_not_reconstructed(self):
        self.change('DELETE FROM advisor_budget');self.assert_held_unchanged()
    def test_counter_below_reservations_is_not_increased_or_reset(self):
        self.change('UPDATE advisor_budget SET calls=0');self.assert_held_unchanged()
    def test_negative_or_fractional_counter_is_rejected(self):
        for value in ('-1','1.5'):
            self.change('UPDATE advisor_budget SET calls='+value);self.assert_held_unchanged()
    def test_missing_provider_holds_table_is_not_recreated(self):
        self.change('DROP TABLE advisor_provider_cooldown');self.assert_held_unchanged()
    def test_inverted_provider_hold_fails_closed(self):
        self.change("INSERT INTO advisor_provider_cooldown VALUES ('synthetic',100,99,'provider','{}')");self.assert_held_unchanged()
    def test_restore_review_marker_blocks_runtime(self):
        (self.root/'FG-RESTORE-REVIEW-REQUIRED').write_text('hold');self.assert_held_unchanged()
    def test_unsafe_permissions_and_symlink_fail_closed(self):
        self.path.chmod(0o644);self.assert_held_unchanged();self.path.chmod(0o600)
        link=self.root/'link.sqlite';link.symlink_to(self.path)
        with self.assertRaises(ValueError):require_existing_advisor_ledger(link)
    def test_missing_file_is_not_created(self):
        path=self.root/'lost.sqlite'
        with self.assertRaises(ValueError):require_existing_advisor_ledger(path)
        self.assertFalse(path.exists())
    def test_transaction_validation_detects_counter_loss_after_startup(self):
        require_existing_advisor_ledger(self.path);self.change('DELETE FROM advisor_budget')
        with sqlite3.connect(self.path) as db,self.assertRaises(ValueError):validate_budget_history(db)

    def check_connections_closed(self,should_fail):
        real_connect=sqlite3.connect;connections=[]
        def track(*args,**kwargs):
            connection=real_connect(*args,**kwargs);connections.append(connection);return connection
        with patch('sqlite3.connect',side_effect=track):
            if should_fail:
                with self.assertRaises(ValueError):require_existing_advisor_ledger(self.path)
            else:require_existing_advisor_ledger(self.path)
        self.assertTrue(connections)
        for connection in connections:
            with self.assertRaises(sqlite3.ProgrammingError):connection.execute('SELECT 1')

    def test_readonly_connections_close_after_success(self):
        self.check_connections_closed(False)

    def test_readonly_connections_close_when_ledger_is_partial(self):
        self.change('DROP TABLE advisor_budget');self.check_connections_closed(True)


if __name__=='__main__':unittest.main()
