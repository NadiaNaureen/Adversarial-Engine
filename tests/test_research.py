import pytest
from app.linkage import score_candidates,decide
from app.models import Assessment, ReleasedRecord
from app.demo import TARGETS
from app.rag import GeminiRAG
from research.datasets import generate,validate
from research.methods import prediction,tune
from research.metrics import metrics
from research.utility import aggregate_error,record_utility


def candidate(identifier,**changes):
    return {'id':identifier,'metadata':dict(TARGETS[0].model_dump(),name=identifier,**changes) if not changes else {**TARGETS[0].model_dump(),'name':identifier,**changes}}


def test_selected_candidate_compared_to_strongest_competitor():
    ranked=[{'id':'retrieved-first','linkage_score':.2},{'id':'selected','linkage_score':.9},{'id':'competitor','linkage_score':.87}]
    result=decide(ranked,selected_id='selected')
    assert result['decision']=='ambiguous'
    assert result['margin']==pytest.approx(.03)
    assert decide(ranked,selected_id='invented')['candidate_id'] is None


def test_tied_candidates_abstain_but_no_margin_ablation_does_not():
    ranked=score_candidates(TARGETS[0],[candidate('x'),candidate('y')])
    assert decide(ranked)['decision']=='ambiguous'
    assert decide(ranked,use_margin=False)['decision']=='match'


def test_missing_fields_are_not_matches_and_suppression_not_automatic_no_match():
    record=ReleasedRecord(**{**TARGETS[0].model_dump(),'occupation':None,'medical_flag':None})
    ranked=score_candidates(record,[candidate('x')])
    assert decide(ranked)['decision']=='match'
    assert ranked[0]['linkage_score']==pytest.approx((3/5)**.5,abs=1e-6)
    empty=ReleasedRecord(id='empty',**{f:None for f in ('age','zip_code','occupation','gender','medical_flag')})
    assert decide(score_candidates(empty,[candidate('x')]))['decision']=='insufficient_evidence'


def test_contradictions_and_generalization():
    record=ReleasedRecord(**{**TARGETS[0].model_dump(),'age':'30-39','zip_code':'560*'})
    ranked=score_candidates(record,[candidate('right'),candidate('wrong',age=70,zip_code='110001')])
    assert ranked[0]['id']=='right'
    assert any(r['status']=='contradiction' for r in ranked[1]['comparisons'])


def test_cost_does_not_change_score_and_cloud_evidence_is_replaced(tmp_path,monkeypatch):
    from app.config import Settings
    from app.demo import ARSENAL
    rag=GeminiRAG(Settings(_env_file=None,rag_mode='local',chroma_path=tmp_path))
    rag.index(ARSENAL)
    proposed=ARSENAL[0].id
    def assess(tokens):
        return Assessment(candidate_id=proposed,decision='match',confidence=1,evidence=['invented evidence']),tokens,'{}','gemini'
    monkeypatch.setattr(rag,'_assess',lambda *a:assess(10))
    low=rag.audit_one(TARGETS[0],4)
    monkeypatch.setattr(rag,'_assess',lambda *a:assess(10000))
    high=rag.audit_one(TARGETS[0],4)
    assert low['linkage_score']==high['linkage_score']
    assert 'invented evidence' not in low['assessment']['evidence']
    monkeypatch.setattr(rag,'_assess',lambda *a:(Assessment(candidate_id='invented',decision='match',confidence=1),0,'{}','gemini'))
    invalid=rag.audit_one(TARGETS[0],4)
    assert invalid['candidate_id'] is None and not invalid['assessment_valid']
    monkeypatch.setattr(rag,'_assess',lambda *a:(Assessment(confidence=0),0,'{}','gemini'))
    assert rag.audit_one(TARGETS[0],4)['risk_score']==0
    rag.llm.close()


def test_reproducible_disjoint_splits_and_all_scenarios():
    data=generate(42,28)
    assert data==generate(42,28)
    validate(data)
    assert len({r['scenario'] for r in data['splits']['test']['targets']})==7
    data['splits']['test']['targets'][0]['group']=data['splits']['validation']['targets'][0]['group']
    with pytest.raises(ValueError,match='cross split'): validate(data)


def test_metrics_correct_denominators():
    rows=[{'truth':'a','prediction':'a'},{'truth':'b','prediction':'wrong'},{'truth':None,'prediction':'x'},{'truth':None,'prediction':None}]
    result=metrics(rows)
    assert result['precision']==pytest.approx(1/3)
    assert result['identification_rate']==.5
    assert result['false_identification_rate_absent']==.5
    assert metrics([{'truth':None,'prediction':None}])['precision'] is None


def test_utility_keeps_age_band_counts_but_detects_occupation_loss():
    original=[{'age':34,'occupation':'Teacher'}]
    released=[{'age':'30-39','occupation':None}]
    assert aggregate_error(original,released,'age')==0
    assert aggregate_error(original,released,'occupation')==1


def test_validation_thresholds_and_failed_assessments():
    rows=[{'truth':'a','raw':{'method':{'candidate':'a','score':.8,'margin':.2,'valid':True}}},
          {'truth':None,'raw':{'method':{'candidate':'b','score':.4,'margin':.2,'valid':True}}}]
    settings=tune(rows,'method')
    assert prediction(rows[0]['raw']['method'],**settings)=='a'
    assert prediction(rows[1]['raw']['method'],**settings) is None
    assert prediction(dict(rows[0]['raw']['method'],valid=False),**settings) is None


def test_no_candidate_name_leaks_synthetic_truth():
    for cohort in generate(42,28)['splits'].values():
        assert all(r['id']==r['name'] for r in cohort['arsenal'])


def test_released_age_validation():
    from pydantic import ValidationError
    for age in ('bad','60-20','120-130',-1):
        with pytest.raises(ValidationError):
            ReleasedRecord(**{**TARGETS[0].model_dump(),'age':age})


def test_uci_nested_zip_and_component_splits(tmp_path):
    import io
    import zipfile
    from research.uci import iter_rows,UnionFind,split_for,rates
    content=io.BytesIO()
    with zipfile.ZipFile(content,'w') as inner:
        inner.writestr('block_1.csv','id_1,id_2,is_match\n1,2,TRUE\n2,3,TRUE\n1,4,FALSE\n')
    archive=tmp_path/'data.zip'
    with zipfile.ZipFile(archive,'w') as outer: outer.writestr('donation.zip',content.getvalue())
    rows=list(iter_rows(archive));uf=UnionFind()
    for row in rows:
        if row['is_match']=='TRUE': uf.union(row['id_1'],row['id_2'])
    assert uf.root('1')==uf.root('3')
    assert split_for(uf.root('1'),42)==split_for(uf.root('3'),42)
    assert rates([True,False],[True,True])['precision']==.5


def test_runner_writes_reproducible_outputs_without_touching_app_index(tmp_path):
    import json
    from research.evaluate import run
    summaries,mitigations=run(generate(9,14),tmp_path,[2])
    assert (tmp_path/'predictions.csv').exists()
    manifest=json.loads((tmp_path/'manifest.json').read_text())
    assert not manifest['cloud_enabled'] and manifest['source_sha256']
    assert all(r['n']>0 for r in summaries)
    assert {r['transformation'] for r in mitigations}=={'original','age_band','postal_prefix','occupation_suppression','medical_suppression','combined'}


def test_cloud_failure_is_counted_without_local_fallback():
    from unittest.mock import Mock
    from research.methods import Methods
    from app.demo import ARSENAL
    cloud=Mock()
    cloud.retrieve.side_effect=RuntimeError('provider unavailable')
    methods=Methods([r.model_dump() for r in ARSENAL],cloud)
    result=methods.raw(TARGETS[0].model_dump(),[2])['retrieval_gemini_k2']
    assert not result['valid'] and result['assessment_mode']=='error'
    assert prediction(result,.1,0) is None
