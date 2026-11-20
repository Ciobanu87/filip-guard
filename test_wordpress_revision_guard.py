import unittest
from unittest.mock import patch
from wordpress_revision_guard import ResourceSnapshot, RevisionMismatchError, verify_unchanged


class RevisionGuardTests(unittest.TestCase):
    def setUp(self):
        self.original = ResourceSnapshot('https://example.com', 'post', 7, 'Original', 'rev-1')

    def check(self, **changes):
        data = vars(self.original).copy()
        data.update(changes)
        return verify_unchanged(self.original, ResourceSnapshot(**data))

    def test_identical_snapshot_remains_read_only(self):
        self.assertEqual(self.check(), {'unchanged_for_offline_review': True, 'remote_write_authorized': False})

    def test_content_changed(self):
        with self.assertRaises(RevisionMismatchError): self.check(content='Changed')

    def test_revision_changed_even_if_content_same(self):
        with self.assertRaises(RevisionMismatchError): self.check(revision='rev-2')

    def test_site_changed(self):
        with self.assertRaises(RevisionMismatchError): self.check(site_url='https://other.com')

    def test_resource_id_changed(self):
        with self.assertRaises(RevisionMismatchError): self.check(resource_id=8)

    def test_resource_type_changed(self):
        with self.assertRaises(RevisionMismatchError): self.check(resource_type='page')

    def test_empty_revision_rejected(self):
        with self.assertRaises(RevisionMismatchError): self.check(revision='')

    def test_bool_id_rejected(self):
        with self.assertRaises(RevisionMismatchError): self.check(resource_id=True)

    def test_missing_snapshot_rejected(self):
        with self.assertRaises(RevisionMismatchError): verify_unchanged(self.original, None)

    def test_no_network(self):
        with patch('socket.create_connection') as connection:
            self.check()
            connection.assert_not_called()


if __name__ == '__main__':
    unittest.main()
