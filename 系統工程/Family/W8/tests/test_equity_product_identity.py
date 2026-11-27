"""Official objectives route each fund; no ticker or proxy-price inference."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,sys,tempfile,unittest

HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(HERE.parent/'W5')]
from equity_product_identity import classify
from native_asset_source import classification,FORMAL_CLASSES

RULE=('中度集中／成長或大型權值集中，但仍屬Broad核心曝險 → `B`\n'
    '`SECTOR_ETF / INDUSTRY_ETF / THEME_ETF` → `C`\n'
    '## 32.8 Semiconductor｜半導體\n'
    'Forward P/E → EV/EBITDA → EV/Sales → P/S → FCF Yield\n')


class EquityProductIdentityTest(unittest.TestCase):
    def record(self,symbol):return json.loads((HERE/(symbol+'_product_identity.json')).read_text())

    def test_cpai_ai_method_is_not_an_ai_industry_objective(self):
        product=self.record('CPAI');out=classify('CPAI',product,RULE)
        self.assertEqual((out['asset_type'],out['asset_grade']),('BROAD_ETF','B'))
        self.assertEqual(out['analysis_capabilities'],['V82_BROAD_EQUITY_CORE'])
        self.assertIn('ALL_CAP',out['framework_scope'])
        self.assertEqual(out['grade_evidence']['facts']['minimum_equity_name_count'],50)
        self.assertFalse(out['grade_evidence']['current_safety_or_valuation_inferred'])

    def test_dynf_active_factor_rotation_is_its_own_broad_equity_route(self):
        out=classify('DYNF',self.record('DYNF'),RULE)
        self.assertEqual((out['asset_type'],out['asset_grade']),('BROAD_ETF','B'))
        self.assertNotIn('V82_QQQ_CORE',out['analysis_capabilities'])
        self.assertNotIn('V82_GLOBAL_ETF_CORE',out['analysis_capabilities'])

    def test_dram_retains_derivative_and_concentration_risks(self):
        out=classify('DRAM',self.record('DRAM'),RULE)
        self.assertEqual((out['asset_type'],out['asset_grade']),('INDUSTRY_ETF','C'))
        self.assertIn('DERIVATIVE_LOOKTHROUGH_REQUIRED',out['secondary_style_tags'])
        self.assertIn('NONDIVERSIFIED',out['secondary_style_tags'])
        self.assertEqual(out['valuation_waterfall'],['FORWARD_PE','EV_EBITDA','EV_SALES','PS','FCF_YIELD'])

    def test_wrong_fund_identity_or_missing_structure_is_rejected(self):
        wrong=self.record('CPAI');wrong['symbol']='DYNF'
        with self.assertRaisesRegex(ValueError,'STRUCTURE_EVIDENCE'):classify('CPAI',wrong,RULE)
        wrong=self.record('CPAI');wrong['structure_kind']='AI_INDUSTRY_THEME'
        with self.assertRaisesRegex(ValueError,'CPAI_OFFICIAL'):classify('CPAI',wrong,RULE)
        wrong=self.record('DRAM');wrong['sources']=[]
        with self.assertRaisesRegex(ValueError,'STRUCTURE_EVIDENCE'):classify('DRAM',wrong,RULE)

    def test_source_evidence_does_not_override_the_formal_grade_dictionary(self):
        with self.assertRaisesRegex(ValueError,'FORMAL_MODERATELY'):classify('DYNF',self.record('DYNF'),'')
        with self.assertRaisesRegex(ValueError,'DRAM_OFFICIAL'):classify('DRAM',self.record('DRAM'),'')

    def test_actual_classification_entry_keeps_each_funds_evidence_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic-v82.md';path.write_text('\n'.join(FORMAL_CLASSES)+'\n'+RULE)
            source={'local_path':str(path),'sha256':sha256(path.read_bytes()).hexdigest(),
                'source_reference':'SYNTHETIC_CLASSIFICATION_RULE'}
            outputs={symbol:classification(symbol,source) for symbol in ('CPAI','DYNF','DRAM')}
            self.assertEqual(outputs['CPAI']['grade_evidence']['facts']['symbol'],'CPAI')
            self.assertEqual(outputs['DRAM']['grade_evidence']['facts']['symbol'],'DRAM')
            self.assertNotEqual(outputs['DYNF']['grade_evidence']['source_sha256'],outputs['CPAI']['grade_evidence']['source_sha256'])


if __name__=='__main__':unittest.main()
