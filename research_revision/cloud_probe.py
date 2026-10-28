import json
from app.config import Settings
from openai import OpenAI
from research_revision.evaluate import OUT,dump
s=Settings();c=OpenAI(api_key=s.gemini_api_key,base_url=s.gemini_base_url,max_retries=0,timeout=20)
try:
    r=c.chat.completions.create(model=s.gemini_model,messages=[{'role':'user','content':'Return one JSON object with status ok.'}],max_tokens=50)
    print('Chat available',r.choices[0].message.content)
except Exception as exc:
    body=getattr(exc,'body',{'error':type(exc).__name__});dump(OUT/'chat_quota.json',body);print(json.dumps(body,indent=2))
c.close()
