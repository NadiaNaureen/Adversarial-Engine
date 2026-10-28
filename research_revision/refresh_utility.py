"""Recompute utility from saved releases without rerunning or changing attacks."""
import json
from research_revision.evaluate import OUT,SEEDS,policy,k_level,utility,write_csv,aggregate
for seed in SEEDS:
    folder=OUT/str(seed);data=json.loads((folder/'dataset.json').read_text());base=[t for t in data['splits']['test'] if t['condition']=='clean'];level=k_level(base)
    rows=[]
    for name in ['original','age_band','postal_prefix','medical_suppression','occupation_suppression','combined','k5']:
        release=[policy(t,name,level) for t in base]
        rows.append(dict(seed=seed,policy=name,**utility(base,release)))
    write_csv(folder/'utility.csv',rows)
aggregate()
