import unittest
from unittest.mock import patch
from wordpress_inventory_advisor_bridge import build_inventory_advisor_report, InvalidAdvisorBridge


class InventoryAdvisorBridgeTests(unittest.TestCase):
    def setUp(self):
        self.inventory = [
            {'resource': 'posts', 'id': 1, 'url': 'https://example.org/a'},
            {'resource': 'pages', 'id': 2, 'url': 'https://example.org/b'},
        ]

    def test_only_scanned_html_gets_seo_findings(self):
        rows = [{'page': 'https://example.org/a', 'http_status': 200,
                 'title': '', 'meta_description': '', 'h1_count': 0,
                 'images_missing_alt': 1, 'issues': 'Missing title'}]
        result = build_inventory_advisor_report(self.inventory, rows)
        self.assertEqual(result['inventory_coverage']['not_scanned_count'], 1)
        self.assertTrue(result['seo_recommendations'])
        self.assertTrue(all(r['page'] == 'https://example.org/a' for r in result['seo_recommendations']))
        self.assertFalse(result['autofix'])

    def test_failed_and_non_html_scans_not_called_advisor(self):
        rows = [
            {'page': 'https://example.org/a', 'http_status': 'ERROR'},
            {'page': 'https://example.org/b', 'http_status': 200, 'issues': 'Non-HTML or empty page'},
        ]
        with patch('wordpress_inventory_advisor_bridge.analyze_pages', return_value=[]) as advisor:
            result = build_inventory_advisor_report(self.inventory, rows)
            advisor.assert_called_once_with([])
        self.assertEqual(len(result['incomplete_scans']), 2)
        self.assertEqual(result['seo_recommendations'], [])
        self.assertEqual(result['inventory_coverage']['scan_attempted_count'], 2)

    def test_empty_report(self):
        result = build_inventory_advisor_report([], [])
        self.assertEqual(result['seo_recommendations'], [])
        self.assertEqual(result['inventory_coverage']['inventory_count'], 0)

    def test_invalid_coverage_rejected(self):
        with self.assertRaises(ValueError):
            build_inventory_advisor_report([{'url': 'http://unsafe'}], [])

    def test_reject_advisor_mutation(self):
        rows = [{'page': 'https://example.org/a', 'http_status': 200}]
        with patch('wordpress_inventory_advisor_bridge.analyze_pages', return_value=[{'autofix': True}]):
            with self.assertRaises(InvalidAdvisorBridge):
                build_inventory_advisor_report(self.inventory, rows)

    def test_http_errors_excluded_from_seo(self):
        rows = [{'page': 'https://example.org/a', 'http_status': 404}]
        result = build_inventory_advisor_report(self.inventory, rows)
        self.assertEqual(result['seo_recommendations'], [])
        self.assertEqual(result['incomplete_scans'][0]['http_status'], 404)


if __name__ == '__main__':
    unittest.main()
