import unittest
from advisor_context import evidence_bundle
from advisor_selection_contract import build_schema,normalize
from advisor_diagnostics import AdvisorFailure
from contextual_advisor import FOCUS,MISSING,validate_selection
from test_contextual_advisor import ROWS,CONTEXT,selection
from test_advisor_groq import indexed_selection

class EvidenceQualityTests(unittest.TestCase):
    def setUp(self):self.bundle,self.facts,self.base=evidence_bundle(ROWS,CONTEXT)
    def test_short_label_is_not_eligible_when_real_page_body_exists(self):
        schema=build_schema(self.base,self.facts,MISSING)
        properties=schema['properties']['recommendations']['properties']['f0']['properties']
        self.assertEqual(properties['evidence_id']['enum'],['p0e1'])
        self.assertNotIn('content_unavailable',properties['missing_information']['items']['enum'])
    def test_actual_owner_failure_pattern_cannot_pass_the_repaired_cloud_contract(self):
        # Replays the observed pattern, not another API/connection test.
        payload={'recommendations':{'f0':{'evidence_id':'p0e0','priority':'Medium',
            'missing_information':['content_unavailable'],'include_draft':False}}}
        with self.assertRaises(AdvisorFailure):normalize(payload,self.base,self.facts,FOCUS)
        payload['recommendations']['f0']['evidence_id']='p0e1'
        with self.assertRaises(AdvisorFailure) as caught:normalize(payload,self.base,self.facts,FOCUS)
        self.assertEqual(caught.exception.diagnostic['code'],'context_contradiction')
    def test_legacy_provider_cannot_claim_missing_content_when_it_exists_either(self):
        payload=selection(self.bundle);payload['recommendations'][0]['missing_information']=['content_unavailable']
        with self.assertRaises(AdvisorFailure):validate_selection(payload,self.bundle,self.facts,self.base,'simulated')
    def test_meaningful_titles_and_multiple_body_candidates_remain_selectable(self):
        rows=[{**ROWS[0],'title':'A detailed installation and upgrade guide'}]
        contexts={rows[0]['page']:['Package installation instructions and supported versions.','Subscription preferences and email notification settings.']}
        _,facts,base=evidence_bundle(rows,contexts)
        ids=build_schema(base,facts,MISSING)['properties']['recommendations']['properties']['f0']['properties']['evidence_id']['enum']
        self.assertEqual(len(ids),3) # Relevance still requires a model decision/evaluation.
    def test_unavailable_or_sparse_content_stays_honest_and_draftless(self):
        rows=[{**ROWS[0],'title':'Home'}]
        bundle,facts,base=evidence_bundle(rows,{})
        properties=build_schema(base,facts,MISSING)['properties']['recommendations']['properties']['f0']['properties']
        self.assertIn('content_unavailable',properties['missing_information']['items']['enum'])
        payload=indexed_selection(bundle)
        self.assertIsNone(validate_selection(normalize(payload,base,facts,FOCUS),bundle,facts,base,'simulated')[0]['seo_draft'])
