import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from deployment import oracle_groq_key_entry as entry


class GroqOwnerEntryTests(unittest.TestCase):
    def test_activation_and_different_path_are_rejected(self):
        for text in ('FG_AI_AUTHORIZED=1\nFG_STATE_BACKUP_AUTHORIZED=0\n',
                     'FG_AI_AUTHORIZED=0\nFG_STATE_BACKUP_AUTHORIZED=0\nFG_GROQ_API_KEY_FILE=/other\n',
                     'FG_AI_AUTHORIZED=0\nFG_AI_AUTHORIZED=0\nFG_STATE_BACKUP_AUTHORIZED=0\n'):
            with self.assertRaises(ValueError): entry.proposed_configuration(text)

    def test_only_private_path_added_without_activation(self):
        old='FG_AI_AUTHORIZED=0\nFG_STATE_BACKUP_AUTHORIZED=0\n'
        new=entry.proposed_configuration(old)
        self.assertTrue(new.startswith(old))
        self.assertEqual(entry.proposed_configuration(new), new)
        self.assertNotIn('groq-free', new)

    def test_mismatch_and_malformed_candidates_rejected(self):
        for first, second in [('gsk_'+'a'*30, 'gsk_'+'b'*30), ('not-a-key', 'not-a-key'), ('gsk_'+'a'*300, 'gsk_'+'a'*300)]:
            with self.assertRaises(ValueError): entry.validate_candidate(first, second)

    def test_exclusive_private_install_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); key=root/'candidate'; env=root/'runtime.env'; env.write_text('old')
            entry.install_candidate(b'synthetic-fixture-only', 'held-path-config', os.getuid(), os.getgid(), key_path=key, env_path=env)
            self.assertEqual(key.stat().st_mode & 0o777, 0o400)
            self.assertEqual(env.stat().st_mode & 0o777, 0o600)
            self.assertEqual(env.read_text(), 'held-path-config')
            with self.assertRaises(FileExistsError):
                entry.install_candidate(b'different', 'different', os.getuid(), os.getgid(), key_path=key, env_path=env)
            self.assertEqual(key.read_bytes(), b'synthetic-fixture-only')

    def test_failed_config_commit_removes_only_new_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); key=root/'candidate'; env=root/'runtime.env'; env.write_text('old')
            with patch.object(entry.os, 'replace', side_effect=OSError('fixture')):
                with self.assertRaises(OSError):
                    entry.install_candidate(b'synthetic', 'new', os.getuid(), os.getgid(), key_path=key, env_path=env)
            self.assertFalse(key.exists()); self.assertEqual(env.read_text(), 'old')
            self.assertEqual(list(root.iterdir()), [env])


if __name__=='__main__': unittest.main()
