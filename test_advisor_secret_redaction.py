"""Synthetic credentials only; no provider requests or actual secret reads."""
import json
import unittest
from advisor_context import clean,extract_context,evidence_bundle


class GroqPrefixRedactionTests(unittest.TestCase):
    def test_bare_groq_token_is_redacted_without_needing_a_secret_label(self):
        fake='gsk_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop'
        for value in ('Integration value: '+fake,'Reference ('+fake+') in text'):
            redacted=clean(value)
            self.assertNotIn(fake,redacted)
            self.assertIn('[redacted]',redacted)
        self.assertEqual(clean('A guide to public package installation.'),'A guide to public package installation.')

    def test_groq_token_cannot_reach_provider_evidence_from_title_meta_or_html(self):
        fake='gsk_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop'
        url='https://synthetic-validation.test/redaction'
        contexts=extract_context('<p>Integration value: '+fake+'</p><p>Public installation guide.</p>')
        rows=[dict(page=url,http_status=200,title='Integration '+fake,
                   meta_description='Reference '+fake,h1_count=2,images_missing_alt=0)]
        bundle,facts,_=evidence_bundle(rows,{url:contexts})
        outgoing=json.dumps({'bundle':bundle,'facts':facts})
        self.assertNotIn(fake,outgoing)
        self.assertNotIn('gsk_',outgoing)
        self.assertIn('[redacted]',outgoing)
        self.assertIn('Public installation guide.',outgoing)
