import tempfile
from pathlib import Path
import unittest
from advisor_language import review_steps,render_language
from contextual_advisor_ui import render_advice
from contextual_advisor import ContextualAdvisor
from test_contextual_advisor import SimulatedProvider,ROWS,CONTEXT,SCOPE


class RecordingUI:
    def __init__(self):self.texts=[];self.captions=[]
    def caption(self,value):self.captions.append(value)
    def info(self,value):pass
    def dataframe(self,*args,**kwargs):pass
    def write(self,*args):pass
    def text(self,value):self.texts.append(value)
    def expander(self,*args):return self
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def button(self,*args,**kwargs):raise AssertionError('Advice cannot create repair controls')


class ReviewedStepsTests(unittest.TestCase):
    def item(self,problem='Missing meta description',text='Python package installation and version compatibility guide.'):
        return {'problem':problem,'source':'model-assisted','evidence':[{'id':'p0e1','kind':'content','text':text}],
                'reason':'Observed issue.','solution':'Review the page.','missing_information':['audience_unknown'],
                'seo_draft':None,'page':'https://synthetic-validation.test/guide','model':'simulated',
                'approval':'Informational only','autofix':False,'repair_supported':False}

    def test_known_findings_receive_three_distinct_localized_review_steps(self):
        for problem in ('Missing SEO title','Missing meta description','H1 structure needs review','Images missing ALT text','Page unavailable or scan failed'):
            with self.subTest(problem=problem):
                en=review_steps(self.item(problem),'en');ro=review_steps(self.item(problem),'ro')
                self.assertEqual(len(en),3);self.assertEqual(len(set(en)),3)
                self.assertEqual(len(ro),3);self.assertNotEqual(ro,en)

    def test_seo_guidance_quotes_observed_context_without_inventing_business_facts(self):
        item=self.item();steps=review_steps(item)
        self.assertIn(item['evidence'][0]['text'],steps[1])
        self.assertIn('public HTML',steps[0]);self.assertIn('separately authorized',steps[2])
        self.assertIn('without inventing',steps[1])
        self.assertIsNone(item['seo_draft']);self.assertFalse(item['autofix'])

    def test_sparse_or_redacted_context_requests_information_without_guessing(self):
        for evidence in ([{'kind':'title','text':'Home'}],[{'kind':'content','text':'[redacted] information about a business'}],[]):
            item=self.item();item['evidence']=evidence
            self.assertIn('Obtain page content',review_steps(item)[1])
            self.assertIn('Obține conținutul',review_steps(item,'ro')[1])

    def test_heading_count_and_image_caption_are_not_treated_as_proof(self):
        self.assertIn('count alone does not establish a defect',review_steps(self.item('H1 structure needs review'))[0])
        self.assertIn('caption alone does not prove',review_steps(self.item('Images missing ALT text'))[1])
        self.assertIn('decorative',review_steps(self.item('Images missing ALT text'))[2])

    def test_cached_language_switch_adds_guidance_without_new_model_calls_or_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            provider=SimulatedProvider();engine=ContextualAdvisor(Path(directory)/'ledger.sqlite',provider)
            english=engine.analyze(ROWS,CONTEXT,scope=SCOPE)
            romanian=engine.analyze(ROWS,CONTEXT,scope=SCOPE,language='ro')
        self.assertEqual(provider.calls,1)
        for result in (english,romanian):
            for item in result['recommendations']:
                self.assertEqual(len(item['review_steps']),3)
                self.assertEqual(item['review_guidance_source'],'reviewed-templates')
                self.assertFalse(item['autofix']);self.assertFalse(item['repair_supported'])

    def test_ui_also_renders_guidance_for_old_saved_results_as_plain_text_without_buttons(self):
        item=self.item(text='<script>untrusted text is not executable review guidance</script>')
        self.assertNotIn('review_steps',item)
        ui=RecordingUI();render_advice(ui,{'status':'model-assisted','recommendations':[item]})
        self.assertTrue(any('2. Confirm the topic' in text for text in ui.texts))
        self.assertTrue(any('<script>' in text for text in ui.texts))
        self.assertTrue(any('not model-generated technical diagnoses' in text for text in ui.captions))
        self.assertNotIn('review_steps',item)
