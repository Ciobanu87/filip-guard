"""Offline tests for the opt-in WordPress audit orchestration."""
import unittest
from unittest.mock import patch
from wordpress_public_audit import build_public_wordpress_audit


class PublicWordPressAuditTests(unittest.TestCase):
    @patch('wordpress_public_audit.collect_public_inventory')
    def test_end_to_end_report_with_existing_advisor(self, inventory):
        inventory.return_value = [
            {'resource': 'posts', 'id': 1, 'url': 'https://example.org/a'},
            {'resource': 'pages', 'id': 2, 'url': 'https://example.org/b'},
        ]
        rows = [{'page': 'https://example.org/a', 'http_status': 200,
                 'title': '', 'meta_description': '', 'h1_count': 0,
                 'images_missing_alt': 0, 'issues': 'Missing title'}]
        report = build_public_wordpress_audit('example.org', rows, per_page=5)
        self.assertEqual(report['inventory_coverage']['not_scanned_count'], 1)
        self.assertTrue(report['seo_recommendations'])
        self.assertTrue(all(x['page'] == 'https://example.org/a' for x in report['seo_recommendations']))
        self.assertIs(report['autofix'], False)
        inventory.assert_called_once_with('example.org', per_page=5, timeout=15)

    @patch('wordpress_public_audit.collect_public_inventory')
    def test_invalid_input_never_fetches(self, inventory):
        cases = [('', []), ('https://example.org', []), ('example.org', None),
                 ('example.org', [{}] * 31), ('example.org', [None])]
        for hostname, rows in cases:
            with self.subTest(hostname=hostname, rows_type=type(rows)):
                with self.assertRaises(ValueError):
                    build_public_wordpress_audit(hostname, rows)
        inventory.assert_not_called()

    @patch('wordpress_public_audit.collect_public_inventory')
    def test_invalid_limits_never_fetch(self, inventory):
        for per_page in (0, 101, True, '20', None):
            with self.subTest(per_page=per_page), self.assertRaises(ValueError):
                build_public_wordpress_audit('example.org', [], per_page=per_page)
        for timeout in (0, -1, True, '15'):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                build_public_wordpress_audit('example.org', [], timeout=timeout)
        inventory.assert_not_called()

    @patch('wordpress_public_audit.collect_public_inventory')
    def test_failed_inventory_is_not_silently_ignored(self, inventory):
        inventory.side_effect = ValueError('WordPress API unavailable')
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            build_public_wordpress_audit('example.org', [])

    @patch('wordpress_public_audit.build_inventory_advisor_report')
    @patch('wordpress_public_audit.collect_public_inventory', return_value=[])
    def test_rejects_mutation_flag(self, inventory, advisor):
        advisor.return_value = {'autofix': True}
        with self.assertRaisesRegex(ValueError, 'disabled'):
            build_public_wordpress_audit('example.org', [])

    @patch('wordpress_public_audit.collect_public_inventory', return_value=[])
    def test_empty_audit(self, inventory):
        report = build_public_wordpress_audit('example.org', [])
        self.assertEqual(report['inventory_coverage']['inventory_count'], 0)
        self.assertEqual(report['seo_recommendations'], [])
        self.assertIs(report['autofix'], False)


if __name__ == '__main__':
    unittest.main()
