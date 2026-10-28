"""Quota-aware cloud experiment; protocol amendment precedes predictions."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
import random
import re
import time
import argparse
import numpy as np
from app.config import Settings
from research_revision.evaluate import OUT,SEEDS,Cloud,Matcher,text,dump,write_csv,tune,predictions,aggregate,FIELDS

def selected(t):
    return int(t['group'].rsplit('-',1)[1])<2

def embed(cloud,texts):
    result=[];cache=OUT/'pilot_embeddings';cache.mkdir(exist_ok=True)
    for offset in range(0,len(texts),16):
        batch=texts[offset:offset+16];p=cache/(hashlib.sha256((cloud.settings.gemini_embedding_model+json.dumps(batch)).encode()).hexdigest()+'.npy')
        if p.exists():result.extend(np.load(p));continue
        for attempt in range(5):
            start=time.perf_counter()
            try:
                response=cloud.client.embeddings.create(model=cloud.settings.gemini_embedding_model,input=batch,encoding_format='float')
                data=sorted(response.data,key=lambda r:r.index if r.index is not None else 0)
                vec=np.asarray([r.embedding for r in data],dtype=np.float32)
                assert len(vec)==len(batch)
                vec/=np.maximum(np.linalg.norm(vec,axis=1,keepdims=True),1e-12);np.save(p,vec);result.extend(vec)
                usage=dict(kind='pilot_embedding',n=len(batch),seconds=time.perf_counter()-start,tokens=getattr(response.usage,'total_tokens',None))
                with (OUT/'pilot_embedding_usage.jsonl').open('a') as f:f.write(json.dumps(usage)+'\n')
                print(f'Embedded pilot {offset+len(batch)}/{len(texts)}',flush=True)
                time.sleep(max(0,.68*len(batch)-(time.perf_counter()-start)))
                break
            except Exception as exc:
                body=getattr(exc,'body',{});dump(OUT/'last_cloud_error.json',body)
                if getattr(exc,'status_code',None)==429:
                    retry=re.search(r'retry in ([0-9.]+)s',str(exc))
                    delay=min(59,float(retry.group(1))+2) if retry else 40
                    print(f'Embedding rate limit: waiting {delay:.0f}s',flush=True);time.sleep(delay)
                elif attempt<4:time.sleep(3)
                else:raise
        else:raise RuntimeError('Embedding quota unavailable after paced retries')
    return np.asarray(result,dtype=np.float32)

def nominate(cloud,m,t,r,key,cap):
    ids=r['raw'][key]['candidates'];response=cloud.assess(t,[m.byid[x] for x in ids]);cr=dict(r['raw'][key]);cr['valid']=response['valid']
    a=response.get('assessment',{});selected=a.get('candidate_id');cr.update(candidate=selected,llm_decision=a.get('decision','insufficient_evidence'))
    if selected in ids:
        ii=np.array([int(np.flatnonzero(m.ids==x)[0]) for x in ids]);ss=m.score(t,ii,cap);pos=ids.index(selected)
        cr['score']=float(ss[pos]);cr['margin']=float(ss[pos]-max(np.delete(ss,pos),default=0))
    else:cr.update(score=0.,margin=0.)
    r['raw']['llm']=cr;r['cloud_response']=response
    return r

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--hash-only',action='store_true');parser.add_argument('--embeddings-only',action='store_true');args=parser.parse_args()
    cloud=Cloud(Settings())
    for seed in SEEDS:
        folder=OUT/str(seed);data=json.loads((folder/'dataset.json').read_text());config=json.loads((folder/'configuration.json').read_text())
        key=config['local']['key'];k=int(key.split('_')[0][1:]);cap=int(key.split('_c')[1]);m=Matcher(data['population'])
        if args.embeddings_only:
            present={t['truth'] for split in data['splits'].values() for t in split if t['truth']}
            remaining=[p for p in data['population'] if p['id'] not in present]
            pilot=[p for p in data['population'] if p['id'] in present]+random.Random(seed+400).sample(remaining,150-len(present))
            embed(cloud,[text(r) for r in pilot])
            for split in ['validation','test']:embed(cloud,[text(t) for t in data['splits'][split] if selected(t)])
            print(f'Pilot embeddings seed {seed} complete',flush=True);continue
        # Core LLM experiment uses full-index hash retrieval, with cached candidates.
        hashraw={};semraw={}
        for split in ['validation','test']:
            path=folder/f'pilot_hash_{split}.json'
            if path.exists():
                old=json.loads(path.read_text())
                if all('error' not in r['cloud_response'] for r in old):hashraw[split]=old;continue
            raw=[r for r in json.loads((folder/f'raw_{split}.json').read_text()) if selected(r)]
            targets={t['target_id']:t for t in data['splits'][split]}
            with ThreadPoolExecutor(max_workers=3) as pool:
                done=[]
                for future in as_completed([pool.submit(nominate,cloud,m,targets[r['target_id']],r,key,cap) for r in raw]):
                    done.append(future.result());print(f'LLM full index seed {seed} {split}: {len(done)}/{len(raw)}',flush=True)
            hashraw[split]=sorted(done,key=lambda r:r['target_id']);dump(path,hashraw[split])
        settings,_=tune(hashraw['validation'],'llm')
        pred=predictions(hashraw['test'],'llm',settings,'hash_llm')
        control,_=tune(hashraw['validation'],key)
        pred+=predictions(hashraw['test'],key,control,'full_hash_control')
        if args.hash_only:
            dump(folder/'pilot_configuration.json',dict(full_hash_llm=settings,full_hash_control=control,k=k,cap=cap,targets_per_split=24))
            write_csv(folder/'cloud_predictions.csv',pred);aggregate();continue
        # Include all target truth identities in the semantic pilot, plus random distractors.
        present={t['truth'] for split in data['splits'].values() for t in split if t['truth']}
        remaining=[p for p in data['population'] if p['id'] not in present]
        pilot=[p for p in data['population'] if p['id'] in present]+random.Random(seed+400).sample(remaining,150-len(present))
        dump(folder/'pilot_population_ids.json',[r['id'] for r in pilot]);pm=Matcher(pilot)
        pm.semantic=embed(cloud,[text(r) for r in pilot])
        for split in ['validation','test']:
            path=folder/f'pilot_semantic_{split}.json'
            if path.exists():semraw[split]=json.loads(path.read_text());continue
            targets=[t for t in data['splits'][split] if selected(t)]
            vectors=embed(cloud,[text(t) for t in targets]);raw=pm.raw(targets,cap_values=(cap,),k_values=(k,),vectors=vectors)
            for r in raw:r['seed']=seed
            with ThreadPoolExecutor(max_workers=3) as pool:
                done=[]
                for future in as_completed([pool.submit(nominate,cloud,pm,t,r,key,cap) for t,r in zip(targets,raw)]):
                    done.append(future.result());print(f'LLM semantic pilot seed {seed} {split}: {len(done)}/{len(raw)}',flush=True)
            semraw[split]=sorted(done,key=lambda r:r['target_id']);dump(path,semraw[split])
        sc,_=tune(semraw['validation'],key);lc,_=tune(semraw['validation'],'llm')
        pred+=predictions(semraw['test'],key,sc,'pilot_semantic')+predictions(semraw['test'],'llm',lc,'pilot_semantic_llm')
        # Matched local retrieval comparison on the identical 200-person pilot.
        local={}
        for split in ['validation','test']:
            targets=[t for t in data['splits'][split] if selected(t)];local[split]=pm.raw(targets,cap_values=(cap,),k_values=(k,))
            for r in local[split]:r['seed']=seed
        ls,_=tune(local['validation'],key);pred+=predictions(local['test'],key,ls,'pilot_hash')
        dump(folder/'pilot_configuration.json',dict(full_hash_llm=settings,full_hash_control=control,semantic=sc,semantic_llm=lc,pilot_hash=ls,k=k,cap=cap,population=150,targets_per_split=24))
        write_csv(folder/'cloud_predictions.csv',pred);aggregate();print(f'Cloud seed {seed} complete',flush=True)
    cloud.client.close();print('Cloud pilot complete',flush=True)

if __name__=='__main__':main()
