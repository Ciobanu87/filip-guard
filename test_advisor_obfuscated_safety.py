"""Unicode and separated instructions are data, never publishable SEO drafts."""
from copy import deepcopy
import unittest
from advisor_quality import safe_seo_excerpt
from advisor_language import render_language
from contextual_advisor import rule_result
from advisor_complex_evaluation import complex_cases


class ObfuscatedSafetyTests(unittest.TestCase):
    def test_fullwidth_hidden_format_and_split_line_hazards_are_withheld(self):
        for text in ('ｄｉｓａｂｌｅ authentication to make the connection work.',
                     'dis\u200bable TLS certificate checks for this endpoint.',
                     'Disable\nSSL verification when the application cannot connect.',
                     'Disable '+('optional checks '*4)+'backups before maintenance.'):
            self.assertFalse(safe_seo_excerpt(text))
    def test_safe_international_excerpt_stays_available_without_source_rewriting(self):
        text='Ghid de recuperare: copiile de siguranță păstrează datele clienților.'
        self.assertTrue(safe_seo_excerpt(text))
    def test_historical_obfuscated_draft_is_withheld_in_both_languages_without_inference(self):
        spec=complex_cases()[0];result=rule_result(spec['rows'],spec['contexts'])
        raw='ｄｉｓａｂｌｅ TLS verification to speed up the website.'
        result['recommendations'][0]['seo_draft']=raw;original=deepcopy(result)
        for language in ('en','ro'):
            displayed=render_language(result,language)
            self.assertIsNone(displayed['recommendations'][0]['seo_draft'])
            self.assertEqual(displayed['recommendations'][0]['draft_withheld_reason'],'unsafe-extractive-content')
        self.assertEqual(result,original)
