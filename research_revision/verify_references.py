"""Retrieve publisher-deposited metadata without credentials."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path
import urllib.request

DOIS={1:'10.1016/j.knosys.2024.112945',2:'10.1007/s10618-024-01066-3',3:'10.1007/s10207-024-00944-7',4:'10.1007/s10994-025-06799-w',5:'10.1007/s10994-025-06835-9',7:'10.1145/1217299.1217302',8:'10.1109/ICDE.2007.367856',9:'10.1007/11787006_1',14:'10.1109/MITP.2025.3634142',15:'10.1145/3719027.3765139',18:'10.1038/s41467-019-10933-3',22:'10.1080/01621459.1969.10501049'}

def main():
    result={}
    def fetch(item):
        number,doi=item
        try:
            req=urllib.request.Request('https://api.crossref.org/works/'+doi,headers={'User-Agent':'ResearchPaperBibliographyAudit/1.0'})
            with urllib.request.urlopen(req,timeout=30) as response:m=json.load(response)['message']
            return number,{k:m.get(k) for k in ['DOI','title','author','container-title','volume','issue','page','article-number','published','publisher','URL','type']}
        except Exception as e:return number,{'error':str(e),'DOI':doi}
    with ThreadPoolExecutor(max_workers=3) as p:
        for f in as_completed([p.submit(fetch,x) for x in DOIS.items()]):
            n,r=f.result();result[n]=r;print(n,r.get('title',r.get('error')),flush=True)
    Path(__file__).with_name('reference_metadata.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')

if __name__=='__main__':main()
