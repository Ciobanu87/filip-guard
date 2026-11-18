import unittest
from wordpress_inventory_scan_bridge import compare_inventory_to_scan, InvalidInventoryComparison


class InventoryScanBridgeTests(unittest.TestCase):
    def setUp(self):
        self.inventory = [
            {'resource': 'posts', 'id': 1, 'url': 'https://example.org/a'},
            {'resource': 'pages', 'id': 1, 'url': 'https://example.org/b'},
        ]

    def test_coverage_only(self):
        result = compare_inventory_to_scan(self.inventory, [{'page': 'https://example.org/a', 'http_status': 'ERROR'}])
        self.assertEqual(result['inventory_count'], 2)
        self.assertEqual(result['scan_attempted_count'], 1)
        self.assertEqual(result['not_scanned_count'], 1)
        self.assertEqual(result['not_scanned'][0]['url'], 'https://example.org/b')
        self.assertIn('not SEO issues', result['note'])

    def test_empty(self):
        result = compare_inventory_to_scan([], [])
        self.assertEqual(result['not_scanned'], [])
        self.assertEqual(result['inventory_count'], 0)

    def test_duplicate_id_rejected(self):
        with self.assertRaises(InvalidInventoryComparison):
            compare_inventory_to_scan(self.inventory + [self.inventory[0]], [])

    def test_invalid_urls(self):
        for url in ('http://example.org/a', 'https://localhost:8080/', 'https://user@example.org/',
                    'https://example.org/a#fragment', 'https://example.org/\n', 'not-a-url'):
            with self.subTest(url=url), self.assertRaises(InvalidInventoryComparison):
                compare_inventory_to_scan([{'resource': 'posts', 'id': 1, 'url': url}], [])

    def test_invalid_inputs(self):
        for inventory, scan in ((None, []), ([], None), ([{}], []), ([], [{}]),
                                ([], [{'page': 5}]), (self.inventory * 101, [])):
            with self.subTest(inventory=str(inventory)[:30], scan=scan), self.assertRaises(InvalidInventoryComparison):
                compare_inventory_to_scan(inventory, scan)


if __name__ == '__main__':
    unittest.main()
