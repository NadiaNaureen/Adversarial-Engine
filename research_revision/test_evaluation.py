import unittest
import numpy as np
from app.linkage import score_candidates
from research_revision.evaluate import Matcher, generate, metrics, decide, policy, k_level, k_stats,utility

class EvaluationTests(unittest.TestCase):
    def test_vectorized_score_matches_application(self):
        d=generate(7,200);m=Matcher(d['population']);ii=np.arange(16)
        for condition in ('clean','missing','age_band','postal_prefix','combined'):
            t=d['splits']['test'][0]
            if condition!='clean':t=policy(t,condition)
            actual=m.score(t,ii,3)
            ranked=score_candidates(t,[{'id':m.pop[i]['id'],'metadata':m.pop[i]} for i in ii],m.pop)
            lookup={r['id']:r['linkage_score'] for r in ranked}
            np.testing.assert_allclose(actual,[lookup[m.pop[i]['id']] for i in ii],atol=1e-6)

    def test_identity_splits_and_variants(self):
        d=generate(8,200);a=d['splits']['validation'];b=d['splits']['test']
        self.assertFalse({r['truth'] for r in a if r['truth']} & {r['truth'] for r in b if r['truth']})
        self.assertEqual(len(a),240);self.assertEqual(len(b),360)
        self.assertEqual(sum(r['cloud'] for r in b),60)
        self.assertEqual(d,generate(8,200))

    def test_wrong_present_predictions_count_against_precision(self):
        rows=[dict(truth='a',prediction='a',decision='match'),dict(truth='b',prediction='a',decision='match'),dict(truth=None,prediction='c',decision='match'),dict(truth=None,prediction=None,decision='ambiguous')]
        m=metrics(rows)
        self.assertAlmostEqual(m['precision'],1/3);self.assertEqual(m['wrong_present'],1)
        self.assertEqual(m['fpr'],.5);self.assertEqual(m['coverage'],.75)

    def test_failed_calls_never_become_matches(self):
        self.assertEqual(decide(dict(valid=False,candidate='x',score=1,margin=1)),(None,'error'))
        self.assertEqual(decide(dict(valid=True,candidate='x',score=1,margin=0)),(None,'ambiguous'))

    def test_k_is_verified_on_release(self):
        base=[r for r in generate(11,200)['splits']['test'] if r['condition']=='clean']
        release=[policy(t,'k5',k_level(base)) for t in base]
        self.assertGreaterEqual(k_stats(release)[0],5)

    def test_coarse_age_interval_does_not_invent_decade_counts(self):
        row=dict(age=55,occupation='Teacher',zip_code='110001',gender='woman',medical_flag='none')
        band=dict(row,age='40-79',occupation=None)
        self.assertEqual(utility([row],[band])['marginal_tv'],1.)
        self.assertEqual(utility([row],[dict(row,age='50-59')])['marginal_tv'],0.)

if __name__=='__main__':unittest.main()
