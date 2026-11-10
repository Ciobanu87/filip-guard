"""Offline, read-only tests for FILIP GUARD's WordPress link resolver.

Run with: python -m unittest -v test_link_resolver.py
No website is contacted and no content is changed.
"""
import unittest
from link_resolver import suggest_replacements


class LinkResolverTests(unittest.TestCase):
    def setUp(self):
        self.broken = 'https://example.org/services/website-audti/'
        self.items = [
            {'status': 'publish', 'slug': 'website-audit',
             'title': {'rendered': 'Website Audit'},
             'link': 'https://example.org/services/website-audit/'},
            {'status': 'draft', 'slug': 'website-audti',
             'title': {'rendered': 'Draft'},
             'link': 'https://example.org/services/website-audti-draft/'},
            {'status': 'publish', 'slug': 'website-audit',
             'title': {'rendered': 'Other site'},
             'link': 'https://other.example.org/services/website-audit/'},
        ]

    def test_similar_published_page_is_suggested_for_review(self):
        matches = suggest_replacements(self.broken, self.items)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['candidate_url'], 'https://example.org/services/website-audit/')
        self.assertIs(matches[0]['verified'], False)
        self.assertIs(matches[0]['requires_review'], True)

    def test_other_hosts_and_drafts_are_excluded(self):
        matches = suggest_replacements(self.broken, self.items)
        self.assertTrue(all('other.example.org' not in x['candidate_url'] for x in matches))
        self.assertTrue(all('draft' not in x['candidate_url'] for x in matches))

    def test_invalid_url_returns_no_suggestions(self):
        self.assertEqual(suggest_replacements('not-a-url', self.items), [])

    def test_does_not_modify_input(self):
        import copy
        original = copy.deepcopy(self.items)
        suggest_replacements(self.broken, self.items)
        self.assertEqual(self.items, original)


if __name__ == '__main__':
    unittest.main()
