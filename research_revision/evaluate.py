"""Run with the application venv: python -m research_revision.evaluate [--cloud]."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import re
import sys
import time
import threading

import numpy as np
from app.config import Settings
from app.linkage import FIELDS, score_candidates
from app.models import ReleasedRecord
from app.rag import GeminiRAG, narrative

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'results'
SEEDS = [11, 22, 33, 44, 55]
CONDITIONS = ['clean', 'age_noise', 'missing', 'changed', 'combined_noise', 'paraphrase']
OCC = ['Teacher', 'Nurse', 'Accountant', 'Civil engineer', 'Data analyst', 'Shop assistant', 'Driver', 'Architect', 'Pharmacist', 'Researcher', 'Farmer', 'Student']
PARA = ['School educator', 'Registered nursing professional', 'Accounting professional', 'Civil engineering professional', 'Data analysis specialist', 'Retail sales assistant', 'Vehicle operator', 'Building designer', 'Pharmacy professional', 'Scientific researcher', 'Agricultural worker', 'University learner']
AGE = [42, 39, 43, 40, 34, 32, 46, 45, 41, 38, 51, 24]

def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')

def profile(rng):
    o = rng.choices(range(12), weights=[12,10,9,7,10,12,10,4,4,5,10,7])[0]
    age = int(np.clip(round(rng.gauss(AGE[o], 9)), 18, 85))
    city = rng.randrange(8)
    return dict(age=age, zip_code=f'{110+city*10:03d}{rng.randrange(30):03d}', occupation=OCC[o],
                gender=rng.choices(['woman','man','nonbinary'],[49,49,2])[0],
                medical_flag=rng.choices(['none','asthma','diabetes','hypertension','allergy'],
                [60 if age<45 else 35,8,8 if age<45 else 20,8 if age<45 else 25,10])[0])

def generate(seed, n=10000):
    rng=random.Random(seed)
    pop=[dict(id=f's{seed}-a{i:05d}', **profile(rng)) for i in range(n)]
    # Independent identity sampling; collisions in observable attributes are retained.
    chosen=rng.sample(range(n),100)
    data={'seed':seed,'population':pop,'splits':{}}
    offset=0
    for split,count in [('validation',20),('test',30)]:
        bases=[]
        for present in [True,False]:
            for i in range(count):
                truth=pop[chosen[offset+i]]['id'] if present else None
                p={f:pop[chosen[offset+i]][f] for f in FIELDS} if present else profile(rng)
                bases.append(dict(id=f's{seed}-{split}-{int(present)}-{i:03d}',truth=truth,cloud=i<5,**p))
            if present:offset+=count
        targets=[]
        for base in bases:
            for cond in CONDITIONS:
                t=dict(base,condition=cond,target_id=base['id']+'-'+cond,group=base['id'])
                if cond in ('age_noise','combined_noise'):t['age']=max(0,base['age']+rng.choice([-1,1]))
                if cond in ('missing','combined_noise'):t['occupation']=None
                if cond=='changed':t['occupation']=rng.choice([x for x in OCC if x!=base['occupation']])
                if cond=='combined_noise':t['zip_code']=f"{110+rng.randrange(8)*10:03d}{rng.randrange(30):03d}"
                if cond=='paraphrase':t['occupation']=PARA[OCC.index(base['occupation'])]
                targets.append(t)
        data['splits'][split]=targets
    assert not ({t['group'] for t in data['splits']['validation']} & {t['group'] for t in data['splits']['test']})
    return data

def text(row):
    return narrative(ReleasedRecord(id=row['id'],**{f:row.get(f) for f in FIELDS}))

def compatible(value, arr, field):
    if value is None:return np.zeros(len(arr), dtype=float)
    if field=='age' and isinstance(value,str) and '-' in value:
        low, high=map(int,value.split('-'));return ((arr.astype(int)>=low)&(arr.astype(int)<=high)).astype(float)
    if field=='zip_code' and str(value).endswith('*'):
        return np.char.startswith(arr.astype(str), str(value)[:-1]).astype(float)
    return (arr==value).astype(float)

class Matcher:
    def __init__(self,pop):
        self.pop=pop;self.ids=np.array([r['id'] for r in pop]);self.byid={r['id']:r for r in pop}
        self.arr={f:np.array([r[f] for r in pop]) for f in FIELDS}
        self.freq={f:Counter(r[f] for r in pop) for f in FIELDS}
        self.vec=np.asarray(GeminiRAG._local_embeddings([text(r) for r in pop]),dtype=np.float32)
        self.fs_logs=None

    def score(self,t,indices,cap=3):
        sup=np.zeros(len(indices));contra=np.zeros(len(indices));avail=0
        for f in FIELDS:
            v=t.get(f)
            if v is None:continue
            avail+=1
            generalized=(f=='age' and isinstance(v,str)) or (f=='zip_code' and str(v).endswith('*'))
            freq=int(compatible(v,self.arr[f],f).sum()) if generalized else self.freq[f].get(v,0)
            w=1+min(cap,math.log((len(self.pop)+1)/(freq+1)))
            a=compatible(v,self.arr[f][indices],f);sup+=w*a;contra+=w*(1-a)
        den=sup+contra
        return np.round(np.maximum(0,np.divide(sup-contra,den,out=np.zeros_like(sup),where=den>0))*math.sqrt(avail/5),6)

    def field_levels(self,t,indices):
        levels=[]
        for f in FIELDS:
            v=t.get(f);a=self.arr[f][indices]
            if v is None:level=np.full(len(indices),3)
            else:
                level=np.where(compatible(v,a,f)==1,0,2)
                if f=='age' and isinstance(v,int):level=np.where((level!=0)&(np.abs(a.astype(int)-v)<=1),1,level)
                elif f=='zip_code':level=np.where((level!=0)&np.char.startswith(a.astype(str),str(v)[:3]),1,level)
            levels.append(level)
        return levels

    def train_fs(self,seed):
        rng=random.Random(seed+9000);m=np.ones((5,4));u=np.ones((5,4))
        # Independent generated training entities, never validation or test identities.
        for _ in range(1200):
            p=profile(rng);q=dict(p)
            if rng.random()<.5:q['age']+=rng.choice([-1,1])
            if rng.random()<.3:q['occupation']=None
            elif rng.random()<.3:q['occupation']=rng.choice(OCC+PARA)
            if rng.random()<.15:q['zip_code']=profile(rng)['zip_code']
            other=profile(rng)
            for j,f in enumerate(FIELDS):
                for counts,r in [(m,p),(u,other)]:
                    v=q[f];b=r[f]
                    level=3 if v is None else 0 if v==b else 1 if ((f=='age' and abs(v-b)<=1) or (f=='zip_code' and v[:3]==b[:3])) else 2
                    counts[j,level]+=1
        self.fs_logs=np.log((m/m.sum(axis=1,keepdims=True))/(u/u.sum(axis=1,keepdims=True)))

    def raw(self,targets,cap_values=(1,3),k_values=(4,8,16),vectors=None):
        q=np.asarray(GeminiRAG._local_embeddings([text(r) for r in targets]),dtype=np.float32) if vectors is None else vectors
        index=self.vec if vectors is None else self.semantic
        rows=[]
        for block in range(0,len(targets),64):
            sims=q[block:block+64]@index.T
            for j,t in enumerate(targets[block:block+64]):
                start=time.perf_counter();sim=sims[j]
                top=np.argpartition(-sim,min(15,len(sim)-1))[:16]
                top=top[np.lexsort((self.ids[top],-sim[top]))]
                raw={}
                for cap in cap_values:
                    for k in k_values:
                        ii=top[:k];ss=self.score(t,ii,cap);order=np.lexsort((self.ids[ii],-ss));ii=ii[order];ss=ss[order]
                        raw[f'k{k}_c{cap}']=dict(candidate=str(self.ids[ii[0]]),score=float(ss[0]),margin=float(ss[0]-ss[1]),valid=True,
                            candidates=[str(x) for x in self.ids[top[:k]]],scores=[float(x) for x in ss])
                # Full-index exact baseline: require all five fields observed; tie means ambiguity.
                allidx=np.arange(len(self.pop));eq=np.ones(len(self.pop),dtype=bool)
                for f in FIELDS:eq &= compatible(t.get(f),self.arr[f],f)==1
                found=np.flatnonzero(eq)
                raw['exact']=dict(candidate=str(self.ids[found[0]]) if len(found)==1 else None,score=float(len(found)==1),margin=1.,valid=True,tie=len(found)>1)
                if self.fs_logs is not None:
                    fs=sum(self.fs_logs[z,l] for z,l in enumerate(self.field_levels(t,allidx)))
                    best=np.argpartition(-fs,1)[:2];best=best[np.lexsort((self.ids[best],-fs[best]))]
                    raw['fs']=dict(candidate=str(self.ids[best[0]]),score=float(fs[best[0]]),margin=float(fs[best[0]]-fs[best[1]]),valid=True)
                rows.append(dict(seed=t.get('seed'),target_id=t['target_id'],group=t['group'],truth=t['truth'],condition=t['condition'],cloud=t.get('cloud',False),target={f:t.get(f) for f in FIELDS},raw=raw,local_scoring_seconds=time.perf_counter()-start))
        return rows

def decide(raw,tau=.65,gamma=.08,always=False):
    if not raw.get('valid',True):return None,'error'
    if always:return raw['candidate'],'match'
    if raw.get('candidate') is None:return None,'ambiguous' if raw.get('tie') else 'insufficient_evidence'
    if raw.get('llm_decision')=='insufficient_evidence' or raw['score']<tau:return None,'insufficient_evidence'
    if raw.get('llm_decision')=='ambiguous' or raw['margin']<=gamma:return None,'ambiguous'
    return raw['candidate'],'match'

def metrics(rows):
    c=Counter(n=0,present=0,absent=0,correct=0,wrong_present=0,false_absent=0,present_abstain=0,absent_abstain=0)
    for r in rows:
        c['n']+=1;p=r['truth'] is not None;c['present' if p else 'absent']+=1
        pred=r['prediction'];dec=r['decision'];c[dec]+=1
        c['correct' if p and pred==r['truth'] else 'wrong_present' if p and pred is not None else 'false_absent' if not p and pred is not None else 'present_abstain' if p else 'absent_abstain']+=1
    issued=c['correct']+c['wrong_present']+c['false_absent']
    assert sum(c[x] for x in ['correct','wrong_present','false_absent','present_abstain','absent_abstain'])==c['n']
    return dict(c,recall=c['correct']/c['present'] if c['present'] else None,
        fpr=c['false_absent']/c['absent'] if c['absent'] else None,
        wrong_rate=c['wrong_present']/c['present'] if c['present'] else None,
        precision=c['correct']/issued if issued else None,coverage=issued/c['n'] if c['n'] else 0)

def predictions(rows,key,settings,method=None,always=False):
    result=[]
    for r in rows:
        p,d=decide(r['raw'][key],**settings,always=always)
        result.append(dict(seed=r['seed'],target_id=r['target_id'],group=r['group'],truth=r['truth'],condition=r['condition'],method=method or key,prediction=p,decision=d,score=r['raw'][key]['score'],margin=r['raw'][key]['margin'],cloud_subset=r['cloud']))
    return result

def tune(rows,key,fs=False,margin=True):
    best=None
    for tau in (range(-4,25,2) if fs else np.arange(.5,.801,.05)):
        for gamma in ([0,1,2,4] if fs else [0,.04,.08,.12] if margin else [-1]):
            s={'tau':round(float(tau),3),'gamma':gamma};m=metrics(predictions(rows,key,s))
            feasible=m['fpr']<=.05 and m['wrong_rate']<=.05
            rank=(int(feasible),m['recall'] if feasible else -(m['fpr']+m['wrong_rate']),m['precision'] or 0,m['recall'],s['tau'],gamma)
            if best is None or rank>best[0]:best=(rank,s,m)
    return best[1],best[2]

def policy(t,name,level=None):
    r=dict(t);age=t['age'];prefix=str(t['zip_code'])[:3]+'*'
    if name in ('age_band','combined'):r['age']=f'{age//10*10}-{age//10*10+9}'
    if name in ('postal_prefix','combined'):r['zip_code']=prefix
    if name in ('medical_suppression','combined'):r['medical_flag']=None
    if name in ('occupation_suppression','combined'):r['occupation']=None
    if name=='k5':
        width,pref,occ,gender=level
        r['age']=None if width==100 else f'{age//width*width}-{min(age//width*width+width-1,120)}'
        r['zip_code']=None if pref==0 else str(t['zip_code'])[:pref]+'*'
        if not occ:r['occupation']=None
        if not gender:r['gender']=None
    r['condition']=name;r['target_id']=t['group']+'-'+name
    return r

def k_stats(records):
    qi=('age','zip_code','occupation','gender');counts=Counter(tuple(r.get(f) for f in qi) for r in records)
    return min(counts.values()),sum(v==1 for v in counts.values())/len(records)

def k_level(base):
    ladder=[(10,3,1,1),(20,3,0,1),(20,1,0,1),(40,1,0,1),(40,0,0,1),(100,0,0,1),(100,0,0,0)]
    for level in ladder:
        if k_stats([policy(t,'k5',level) for t in base])[0]>=5:return level
    raise AssertionError('global suppression must yield k >= 5')

def utility(base,released):
    changes=supp=loss=0
    for a,b in zip(base,released):
        for f in FIELDS:
            v=b.get(f);changes+=v!=a[f];supp+=v is None
            if v is None:loss+=1
            elif f=='age' and isinstance(v,str):
                low,high=map(int,v.split('-'));loss+=(high-low)/67
            elif f=='zip_code' and str(v).endswith('*'):loss+=(6-len(str(v)[:-1]))/6
    # Prespecified marginal query utility; suppression is a separate category.
    errors=[]
    for f in ['age','occupation']:
        def category(v):
            if v is None:return 'suppressed'
            if f=='age':
                if isinstance(v,str) and '-' in v:
                    low,high=map(int,v.split('-'))
                    if low//10!=high//10:return 'unresolved_decade'
                    return str(low//10)
                return str(int(v)//10)
            return str(v)
        x=Counter(category(r[f]) for r in base);y=Counter(category(r[f]) for r in released)
        errors.append(sum(abs(x[k]-y[k]) for k in x.keys()|y.keys())/(2*len(base)))
    k,single=k_stats(released)
    return dict(min_k=k,singleton_fraction=single,changed_fraction=changes/(5*len(base)),suppression_fraction=supp/(5*len(base)),normalized_loss=loss/(5*len(base)),marginal_tv=sum(errors)/2)

def write_csv(path,rows):
    if not rows:return
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def run_local(data):
    seed=data['seed'];folder=OUT/str(seed);folder.mkdir(parents=True,exist_ok=True)
    m=Matcher(data['population']);m.train_fs(seed)
    val=m.raw(data['splits']['validation']);test=m.raw(data['splits']['test'])
    for row in val+test:row['seed']=seed
    configs={};best=None
    for k in [4,8,16]:
        for cap in [1,3]:
            key=f'k{k}_c{cap}';s,mm=tune(val,key)
            rank=(int(mm['fpr']<=.05 and mm['wrong_rate']<=.05),mm['recall'],mm['precision'] or 0,-k,-cap)
            if best is None or rank>best[0]:best=(rank,key,s)
    key=best[1];s=best[2];configs['local']={'key':key,**s}
    fs,_=tune(val,'fs',fs=True);configs['fs']=fs
    no,_=tune(val,key,margin=False);configs['no_margin']=no
    rows=[]
    for name,kk,ss,always in [('local',key,s,False),('fs','fs',fs,False),('exact','exact',{'tau':.5,'gamma':0},False),('top1',key,s,True),('no_margin',key,no,False)]:
        rows+=predictions(test,kk,ss,name,always)
    base=[r for r in data['splits']['test'] if r['condition']=='clean'];lev=k_level(base);configs['k5_level']=lev
    cleanval=[r for r in val if r['condition']=='clean'];clean_s,_=tune(cleanval,key);configs['mitigation']=clean_s
    mit=[];utils=[];rawmit=[]
    for name in ['original','age_band','postal_prefix','medical_suppression','occupation_suppression','combined','k5']:
        released=[policy(t,name,lev) for t in base];raw=m.raw(released,cap_values=(int(key.split('_c')[1]),),k_values=(int(key.split('_')[0][1:]),))
        for r in raw:r['seed']=seed
        pred=predictions(raw,key,clean_s,'local');mit+=pred;rawmit+=raw
        utils.append(dict(seed=seed,policy=name,**utility(base,released)))
    sensitivity=[]
    for tau in np.arange(.5,.801,.025):
        sensitivity.append(dict(seed=seed,tau=round(float(tau),3),**metrics(predictions(test,key,dict(tau=float(tau),gamma=s['gamma'])))))
    dump(folder/'configuration.json',configs);dump(folder/'raw_validation.json',val);dump(folder/'raw_test.json',test);dump(folder/'raw_mitigations.json',rawmit)
    write_csv(folder/'predictions.csv',rows);write_csv(folder/'mitigation_predictions.csv',mit);write_csv(folder/'utility.csv',utils);write_csv(folder/'sensitivity.csv',sensitivity)
    return m,configs,rows,mit,utils

class Cloud:
    def __init__(self,settings):
        from openai import OpenAI
        self.settings=settings;self.client=OpenAI(api_key=settings.gemini_api_key,base_url=settings.gemini_base_url,max_retries=0,timeout=30)
        self.usage=[];self.log=OUT/'cloud_calls.jsonl'
        self.call_lock=threading.Lock();self.next_chat=0.0

    def embed(self,texts):
        cache=OUT/'embedding_cache';cache.mkdir(exist_ok=True)
        result=[None]*len(texts);jobs=[]
        for start in range(0,len(texts),64):
            batch=texts[start:start+64];digest=hashlib.sha256((self.settings.gemini_embedding_model+json.dumps(batch)).encode()).hexdigest();p=cache/(digest+'.npy')
            if p.exists():result[start:start+len(batch)]=list(np.load(p))
            else:jobs.append((start,batch,p))
        def work(job):
            start,batch,p=job;t=time.perf_counter()
            for attempt in range(4):
                try:
                    response=self.client.embeddings.create(model=self.settings.gemini_embedding_model,input=batch,encoding_format='float')
                    vec=np.asarray([r.embedding for r in response.data],dtype=np.float32)
                    vec/=np.maximum(np.linalg.norm(vec,axis=1,keepdims=True),1e-12)
                    np.save(p,vec)
                    return start,vec,dict(type='embedding',n=len(batch),tokens=getattr(response.usage,'total_tokens',None),seconds=time.perf_counter()-t)
                except Exception as exc:
                    print(f'Embedding batch {start} attempt {attempt+1}: {type(exc).__name__} {str(exc)[:180]}',flush=True)
                    if attempt==3:raise
                    time.sleep(2**attempt)
        pool=ThreadPoolExecutor(max_workers=4)
        futures=[pool.submit(work,x) for x in jobs]
        try:
            for future in as_completed(futures):
                start,vec,usage=future.result();result[start:start+len(vec)]=list(vec);self.usage.append(usage)
                with self.log.open('a',encoding='utf-8') as f:f.write(json.dumps(usage)+'\n')
                print(f'Embedding complete batch {start}; {len(self.usage)} new calls this run',flush=True)
        except Exception:
            for f in futures:f.cancel()
            pool.shutdown(wait=False,cancel_futures=True)
            raise
        else:pool.shutdown()
        return np.asarray(result,dtype=np.float32)

    def assess(self,t,candidates):
        cache=OUT/'chat_cache';cache.mkdir(exist_ok=True)
        payload={'target':{f:t.get(f) for f in FIELDS},'candidates':[{"id":r['id'],**{f:r[f] for f in FIELDS}} for r in candidates]}
        prompt=('Assess one synthetic identity linkage. Return JSON only: candidate_id (one supplied ID or null), decision (match, ambiguous, insufficient_evidence), confidence (0..1), evidence (list of short field comparisons), rationale (short). '
                'Return insufficient_evidence unless evidence is strong; ties are ambiguous. Missing fields are absent evidence. Age ranges and postal prefixes are compatible with contained values. Occupation paraphrases may be semantically compatible, but do not invent facts. '+json.dumps(payload))
        digest=hashlib.sha256((self.settings.gemini_model+prompt).encode()).hexdigest();p=cache/(digest+'.json')
        if p.exists():
            cached=json.loads(p.read_text(encoding='utf-8'))
            if 'error' not in cached:return cached
        started=time.perf_counter();last=None
        for attempt in range(3):
            try:
                # This project has a 15-request/minute free-tier chat quota.
                with self.call_lock:
                    time.sleep(max(0,self.next_chat-time.monotonic()))
                    self.next_chat=time.monotonic()+4.3
                resp=self.client.chat.completions.create(model=self.settings.gemini_model,temperature=0,max_tokens=400,response_format={'type':'json_object'},messages=[{'role':'system','content':'Return one JSON object. Assess only authorized synthetic records. Retrieval is a lead, not proof.'},{'role':'user','content':prompt}])
                raw=resp.choices[0].message.content or '{}';assessment=GeminiRAG._parse_assessment(raw)
                valid=assessment.rationale!='Model response was not valid structured output.' and (assessment.candidate_id is None or assessment.candidate_id in {r['id'] for r in candidates}) and not(assessment.decision=='match' and assessment.candidate_id is None)
                result=dict(valid=valid,assessment=assessment.model_dump(),raw=raw,input_tokens=getattr(resp.usage,'prompt_tokens',None),output_tokens=getattr(resp.usage,'completion_tokens',None),seconds=time.perf_counter()-started,attempts=attempt+1)
                break
            except Exception as exc:
                last=type(exc).__name__+': '+str(exc)[:300]
                if attempt<2:
                    retry=re.search(r'retry in ([0-9.]+)s',str(exc))
                    time.sleep(min(59,float(retry.group(1))+2) if retry else 2**attempt)
        else:result=dict(valid=False,error=last,seconds=time.perf_counter()-started,input_tokens=None,output_tokens=None,attempts=3)
        dump(p,result)
        return result

def cloud_run(data,m,config,cloud):
    seed=data['seed'];folder=OUT/str(seed);key=config['local']['key'];k=int(key.split('_')[0][1:]);cap=int(key.split('_c')[1])
    m.semantic=cloud.embed([text(r) for r in data['population']]);allraw={}
    for split in ['validation','test']:
        targets=[t for t in data['splits'][split] if t['cloud']]
        vectors=cloud.embed([text(t) for t in targets]);raw=m.raw(targets,cap_values=(cap,),k_values=(k,),vectors=vectors)
        def one(pair):
            t,r=pair;ids=r['raw'][key]['candidates'];candidates=[m.byid[x] for x in ids];response=cloud.assess(t,candidates)
            cr=dict(r['raw'][key]);cr['valid']=response['valid'];a=response.get('assessment',{})
            selected=a.get('candidate_id');cr['candidate']=selected;cr['llm_decision']=a.get('decision','insufficient_evidence')
            if selected in ids:
                ii=np.array([int(np.flatnonzero(m.ids==x)[0]) for x in ids]);ss=m.score(t,ii,cap);pos=ids.index(selected)
                cr['score']=float(ss[pos]);cr['margin']=float(ss[pos]-max(np.delete(ss,pos),default=0))
            else:cr.update(score=0.,margin=0.)
            r['seed']=seed;r['raw']['llm']=cr;r['cloud_response']=response
            return r
        done=[]
        with ThreadPoolExecutor(max_workers=6) as pool:
            for future in as_completed([pool.submit(one,pair) for pair in zip(targets,raw)]):
                done.append(future.result())
                if len(done)%20==0:print(f'cloud seed {seed} {split}: {len(done)}/{len(raw)}',flush=True)
        allraw[split]=sorted(done,key=lambda r:r['target_id']);dump(folder/f'cloud_raw_{split}.json',allraw[split])
    sc,_=tune(allraw['validation'],key);lc,_=tune(allraw['validation'],'llm')
    dump(folder/'cloud_configuration.json',dict(semantic=sc,llm=lc,k=k,cap=cap,model=cloud.settings.gemini_model,embedding=cloud.settings.gemini_embedding_model))
    pred=predictions(allraw['test'],key,sc,'semantic')+predictions(allraw['test'],'llm',lc,'llm')
    write_csv(folder/'cloud_predictions.csv',pred)
    return pred

def aggregate():
    records=defaultdict(list)
    for seed in SEEDS:
        folder=OUT/str(seed)
        for file in ['predictions','mitigation_predictions','utility','sensitivity','cloud_predictions']:
            p=folder/(file+'.csv')
            if p.exists():
                with p.open(encoding='utf-8') as f:records[file]+=list(csv.DictReader(f))
    summary=[]
    for file in ['predictions','mitigation_predictions','cloud_predictions']:
        rows=records[file];groups=defaultdict(list)
        for r in rows:
            r['truth']=r['truth'] or None;r['prediction']=r['prediction'] or None
            groups[(r['seed'],r['method'],'all' if file!='mitigation_predictions' else r['condition'])].append(r)
            if file!='mitigation_predictions':groups[(r['seed'],r['method'],r['condition'])].append(r)
        for (seed,method,condition),rr in groups.items():summary.append(dict(dataset=file,seed=int(seed),method=method,condition=condition,**metrics(rr)))
    dump(OUT/'summary.json',summary)
    for file,rr in records.items():write_csv(OUT/(file+'.csv'),rr)
    return summary

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cloud',action='store_true');parser.add_argument('--seeds',nargs='+',type=int,default=SEEDS);args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    source={str(p.relative_to(ROOT.parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'protocol.md',ROOT.parent/'app/linkage.py',ROOT.parent/'app/rag.py']}
    dump(OUT/'manifest.json',dict(python=sys.version,platform=platform.platform(),seeds=args.seeds,source_sha256=source,cloud_requested=args.cloud,started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),population_size=10000))
    cloud=Cloud(Settings()) if args.cloud else None
    for seed in args.seeds:
        folder=OUT/str(seed);dataset=folder/'dataset.json'
        data=json.loads(dataset.read_text()) if dataset.exists() else generate(seed)
        dump(dataset,data);print(f'Seed {seed}: dataset ready',flush=True)
        if not (folder/'predictions.csv').exists():m,config,*_=run_local(data)
        else:m=Matcher(data['population']);m.train_fs(seed);config=json.loads((folder/'configuration.json').read_text())
        print(f'Seed {seed}: local complete {config}',flush=True)
        aggregate()
        if cloud is not None and not (folder/'cloud_predictions.csv').exists():
            cloud_run(data,m,config,cloud);aggregate();print(f'Seed {seed}: cloud complete',flush=True)
    aggregate();print('Evaluation complete',flush=True)

if __name__=='__main__':main()
