import sys,json
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
sys.path.insert(0,str(Path.cwd()/'second_review_work'))
import evaluate_expanded as e
# Matcher's implementation is unchanged; only local cohort sizes and output folder differ.
e.ROOT=Path.cwd()/'research_revision'
for seed in e.SEEDS:
 folder=e.OUT/str(seed)
 if (folder/'predictions.csv').exists():continue
 data=e.generate(seed);e.dump(folder/'dataset.json',data)
 print('Starting seed',seed,flush=True)
 e.run_local(data)
 print('Completed seed',seed,flush=True)
e.aggregate()
