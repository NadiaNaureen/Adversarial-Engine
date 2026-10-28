"""Build checked, compact statistical inputs for manuscript authoring."""
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import statistics
from research_revision.evaluate import OUT,SEEDS,aggregate,dump,metrics
from app.config import Settings

def main():
    summary=aggregate();result={};cloud_settings=Settings()
    for seed in SEEDS:
        path=OUT/str(seed)/'pilot_configuration.json'
        if path.exists():
            cfg=json.loads(path.read_text());cfg.update(cloud_model=cloud_settings.gemini_model,embedding_model=cloud_settings.gemini_embedding_model,temperature=0,max_completion_tokens=400,fallback_enabled=False)
            dump(path,cfg)
    groups=defaultdict(list)
    for r in summary:groups[(r['dataset'],r['method'],r['condition'])].append(r)
    for (dataset,method,condition),rows in groups.items():
        item={'seeds':len(rows),'totals':{k:sum(r.get(k,0) for r in rows) for k in ['n','present','absent','correct','wrong_present','present_abstain','false_absent','absent_abstain','match','ambiguous','insufficient_evidence','error']}}
        for k in ['recall','fpr','wrong_rate','precision','coverage']:
            values=[r[k] for r in rows if r[k] is not None]
            item[k]={'mean':statistics.mean(values) if values else None,'sd':statistics.stdev(values) if len(values)>1 else 0}
        result['|'.join([dataset,method,condition])]=item
    with (OUT/'utility.csv').open() as f:utility=list(csv.DictReader(f))
    util={}
    for policy in sorted({r['policy'] for r in utility}):
        rows=[r for r in utility if r['policy']==policy]
        util[policy]={k:{'mean':statistics.mean(float(r[k]) for r in rows),'min':min(float(r[k]) for r in rows),'max':max(float(r[k]) for r in rows)} for k in ['min_k','singleton_fraction','changed_fraction','suppression_fraction','normalized_loss','marginal_tv']}
    evidence=[];usage=[]
    for seed in SEEDS:
        folder=OUT/str(seed)
        raw=json.loads((folder/'raw_mitigations.json').read_text());config=json.loads((folder/'configuration.json').read_text());key=config['local']['key']
        evidence.append(dict(seed=seed,means={p:statistics.mean(r['raw'][key]['score'] for r in raw if r['condition']==p) for p in ['original','age_band','combined']}))
        for name in ['pilot_hash_validation.json','pilot_hash_test.json','pilot_semantic_validation.json','pilot_semantic_test.json']:
            p=folder/name
            if p.exists():
                for r in json.loads(p.read_text()):usage.append(dict(seed=seed,experiment='semantic' if 'semantic' in name else 'full_hash',split='test' if 'test' in name else 'validation',**r['cloud_response']))
    operational={}
    for exp in ['full_hash','semantic']:
        rows=[r for r in usage if r['experiment']==exp]
        times=[r['seconds'] for r in rows];tokens=[r['input_tokens']+r['output_tokens'] for r in rows if r.get('input_tokens') is not None and r.get('output_tokens') is not None]
        metered=[r for r in rows if r.get('input_tokens') is not None and r.get('output_tokens') is not None]
        operational[exp]=dict(n=len(rows),valid=sum(r['valid'] for r in rows),mean_seconds=statistics.mean(times) if times else None,median_seconds=statistics.median(times) if times else None,token_rows=len(tokens),total_tokens=sum(tokens) if tokens else None,mean_tokens=statistics.mean(tokens) if tokens else None,mean_input_tokens=statistics.mean(r['input_tokens'] for r in metered) if metered else None,mean_output_tokens=statistics.mean(r['output_tokens'] for r in metered) if metered else None,paid_tier_text_cost_estimate_per_assessment=statistics.mean((.30*r['input_tokens']+2.50*r['output_tokens'])/1e6 for r in metered) if metered else None,billing_cost=None)
    dump(OUT/'paper_numbers.json',dict(metrics=result,utility=util,evidence=evidence,operational=operational))
    dump(OUT/'pricing_basis.json',dict(model='gemini-3.5-flash-lite',accessed='2026-10-23',source='https://ai.google.dev/gemini-api/docs/pricing',paid_standard_input_usd_per_million=.30,paid_standard_output_usd_per_million=2.50,exclusions=['embedding and indexing','failed attempts with unavailable usage','unreported billable tokens','taxes'],actual_billing_cost=None))
    dump(OUT/'final_source_hashes.json',{str(p.relative_to(Path(__file__).parent.parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')})
    for k,v in result.items():
        if k.endswith('|all'):print(k,v['totals'],{q:round(v[q]['mean'] or 0,4) for q in ['recall','fpr','precision']})
    print('operation',operational)

if __name__=='__main__':main()
