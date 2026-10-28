import sys,json,csv,statistics
from pathlib import Path
sys.path.insert(0,str(Path.cwd()));sys.path.insert(0,str(Path.cwd()/'second_review_work'))
import evaluate_expanded as e
OUT=Path.cwd()/'second_review_work'/'results'
POLICIES=['original','age_band','postal_prefix','medical_suppression','occupation_suppression','combined','k5']
for seed in e.SEEDS:
 folder=OUT/str(seed)
 if not (folder/'configuration.json').exists():
  print('Await main evaluation seed',seed,flush=True)
  import time
  while not (folder/'configuration.json').exists():time.sleep(2)
 data=json.loads((folder/'dataset.json').read_text());cfg=json.loads((folder/'configuration.json').read_text())
 key=cfg['local']['key'];cap=int(key.split('_c')[1]);k=int(key.split('_')[0][1:])
 m=e.Matcher(data['population']);m.train_fs(seed)
 vbase=[r for r in data['splits']['validation'] if r['condition']=='clean']
 tbase=[r for r in data['splits']['test'] if r['condition']=='clean']
 rawtest=json.loads((folder/'raw_mitigations.json').read_text())
 rows=[];settings={}
 for name in POLICIES:
  val=m.raw([e.policy(t,name,cfg['k5_level']) for t in vbase],cap_values=(cap,),k_values=(k,))
  test=[r for r in rawtest if r['condition']==name]
  for r in val:r['seed']=seed
  # Permit a lowered threshold after suppression; select solely on transformed validation.
  best=None
  for tau in [round(i/20,2) for i in range(21)]+[1.000001]:
   for gamma in [0,.04,.08,.12]:
    s=dict(tau=tau,gamma=gamma);mm=e.metrics(e.predictions(val,key,s));feas=mm['fpr']<=.05 and mm['wrong_rate']<=.05
    rank=(int(feas),mm['recall'] if feas else -(mm['fpr']+mm['wrong_rate']),mm['precision'] or 0,mm['recall'],tau,gamma)
    if best is None or rank>best[0]:best=(rank,s)
  fs,_=e.tune(val,'fs',fs=True);settings[name]={'adaptive_local':best[1],'adaptive_fs':fs}
  rows+=e.predictions(test,key,best[1],'adaptive_local')+e.predictions(test,'fs',fs,'adaptive_fs')
 e.write_csv(folder/'adaptive_predictions.csv',rows);e.dump(folder/'adaptive_configuration.json',settings)
 # Descriptive test curves: retain the validation-selected margin, sweep every observed score.
 raw=json.loads((folder/'raw_test.json').read_text());curve=[];matched=[]
 for method,kk in [('local',key),('fs','fs')]:
  gamma=cfg[method]['gamma'];scores=sorted({r['raw'][kk]['score'] for r in raw},reverse=True)
  for tau in [max(scores)+1]+scores:
   mm=e.metrics(e.predictions(raw,kk,dict(tau=tau,gamma=gamma)))
   curve.append(dict(seed=seed,method=method,tau=tau,**mm))
  for budget in [.02,.05]:
   candidates=[r for r in curve if r['method']==method and r['fpr']<=budget]
   best=max(candidates,key=lambda r:(r['recall'],-r['fpr'],r['tau']))
   matched.append(dict(seed=seed,method=method,budget=budget,**{k:best[k] for k in ['recall','fpr','tau']}))
 e.write_csv(folder/'comparison_curve.csv',[{k:r.get(k,0) for k in ['seed','method','tau','recall','fpr','correct','wrong_present','false_absent','present','absent']} for r in curve]);e.write_csv(folder/'matched_fpr.csv',matched)
 print('Adaptive and matched-FPR complete',seed,flush=True)
print('All supplementary checks complete',flush=True)

