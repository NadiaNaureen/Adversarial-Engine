"""Independent accounting and document-package checks; no network requests."""
from collections import Counter,defaultdict
import csv
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
from research_revision.evaluate import OUT,SEEDS,metrics,decide

def main():
    report={'checks':[]};groups=defaultdict(list)
    for seed in SEEDS:
        folder=OUT/str(seed);data=json.loads((folder/'dataset.json').read_text());ids={p['id'] for p in data['population']}
        assert len(ids)==10000
        a={r['truth'] for r in data['splits']['validation'] if r['truth']};b={r['truth'] for r in data['splits']['test'] if r['truth']};assert not a&b
        for file in ['predictions.csv','mitigation_predictions.csv','cloud_predictions.csv']:
            with (folder/file).open() as f:rows=list(csv.DictReader(f))
            keys=[(r['method'],r['target_id']) for r in rows];assert len(keys)==len(set(keys)),(seed,file,'duplicate target')
            for r in rows:
                r['truth']=r['truth'] or None;r['prediction']=r['prediction'] or None
                assert r['truth'] is None or r['truth'] in ids
                assert r['prediction'] is None or r['prediction'] in ids
                assert (r['prediction'] is not None)==(r['decision']=='match')
                groups[(file,r['method'],r['condition'] if file=='mitigation_predictions.csv' else 'all')].append(r)
        cfg=json.loads((folder/'pilot_configuration.json').read_text());key=json.loads((folder/'configuration.json').read_text())['local']['key']
        for prefix in ['pilot_hash','pilot_semantic']:
            for split in ['validation','test']:
                rows=json.loads((folder/(prefix+'_'+split+'.json')).read_text());assert len(rows)==24
                for r in rows:
                    assert r['cloud_response']['valid'],(seed,prefix,split,r['target_id'])
                    selected=r['raw']['llm']['candidate']
                    assert selected is None or selected in r['raw'][key]['candidates']
        assert len(json.loads((folder/'pilot_population_ids.json').read_text()))==150
        report['checks'].append(f'Seed {seed}: split, IDs, prediction uniqueness, all cloud responses and candidate constraints verified')
    for (file,method,condition),rows in groups.items():
        m=metrics(rows);expected=300 if file=='mitigation_predictions.csv' else 120 if file=='cloud_predictions.csv' else 1800
        assert m['n']==expected,(file,method,condition,m['n'])
        assert m['correct']+m['wrong_present']+m['present_abstain']==m['present']
        assert m['false_absent']+m['absent_abstain']==m['absent']
    report['checks'].append('Every method and policy has complete, mutually exclusive outcome counts')
    ref=Path(r'C:\NADIA\Sem7\adver gpt\Adversarial_ReID_Engine_Research_Paper_6_Pages.docx');final=ref.with_name('LLM_Privacy_Audit_Revised_6_Pages.docx')
    assert hashlib.sha256(ref.read_bytes()).hexdigest()=='c5c2886e72e87a6ca6249764ac1d7206c2d5463633cf25efd86d021f70e75cea'
    with ZipFile(ref) as a,ZipFile(final) as b:
        for part in ['word/styles.xml','word/numbering.xml','word/theme/theme1.xml']:assert a.read(part)==b.read(part)
        xml=b.read('word/document.xml').decode()
        assert 'Jai Vinita' in xml and 'jaivinita.l@vit.ac.in' in xml
        assert 'results are still being collected' not in xml and 'must be added only after' not in xml
        assert xml.index('VIII. Conclusion')<xml.index('References')
    report['checks'].append('Original reference unchanged; source styles, numbering and theme preserved; author block and conclusion order verified')
    (OUT/'validation_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
