"""Package reproducibility evidence without credentials or unrelated app data."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import hashlib
import json
ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parent
OUT=Path(r'C:\NADIA\Sem7\adver gpt\Paper_Reproducibility_Package.zip')
files=[]
for p in ROOT.rglob('*'):
    if not p.is_file():continue
    rel=p.relative_to(ROOT)
    if any(x in rel.parts for x in ['__pycache__','test_tmp','embedding_cache']):continue
    if p.suffix.lower() not in ['.py','.md','.json','.jsonl','.csv','.npy','.ps1']:continue
    files.append((p,'research_revision/'+rel.as_posix()))
for p in (PROJECT/'app').glob('*.py'):files.append((p,'app/'+p.name))
for name in ['requirements.txt','requirements-research.txt','.env.example']:
    p=PROJECT/name
    if p.exists():files.append((p,name))
manifest={name:hashlib.sha256(p.read_bytes()).hexdigest() for p,name in files}
with ZipFile(OUT,'w',ZIP_DEFLATED,compresslevel=6) as z:
    for p,name in files:z.write(p,name)
    z.writestr('PACKAGE_SHA256.json',json.dumps(manifest,indent=2))
    z.writestr('START_HERE.txt','Read research_revision/README.md and Paper_Revision_Response.md. The archive excludes credentials, the production candidate index, and unrelated application reports. Partial abandoned large-semantic embeddings are excluded. Pilot embeddings and completed raw model responses are included.\n')
    response=OUT.with_name('Paper_Revision_Response.md')
    if response.exists():z.write(response,response.name)
print(OUT)
print('files',len(files),'bytes',OUT.stat().st_size)
