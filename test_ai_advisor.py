import unittest
from ai_advisor import analyze_pages


class AdvisorTests(unittest.TestCase):
    def test_healthy_html_has_no_recommendations(self):
        self.assertEqual(analyze_pages([dict(http_status=200, title='Title',
            meta_description='Description', h1_count=1, images_missing_alt=0)]), [])

    def test_unavailable_pages_do_not_generate_invented_seo_issues(self):
        for status in ('ERROR', None, True, 0, 199, 404, 503):
            with self.subTest(status=status):
                result = analyze_pages([dict(page='https://example.com', http_status=status)])
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0]['problem'], 'Page unavailable or scan failed')
                self.assertFalse(result[0]['autofix'])

    def test_non_html_and_bodyless_responses_are_not_seo_failures(self):
        rows = [dict(http_status=200, issues='Non-HTML or empty page')]
        rows += [dict(http_status=status) for status in (204, 205, 206, 304)]
        self.assertEqual(analyze_pages(rows), [])

    def test_real_missing_metadata_still_has_reviewable_recommendations(self):
        result = analyze_pages([dict(http_status=200, title='', meta_description='',
            h1_count=0, images_missing_alt=2)])
        self.assertEqual(len(result), 4)
        for item in result:
            self.assertTrue(item['reason'])
            self.assertTrue(item['risk'])
            self.assertFalse(item['autofix'])
