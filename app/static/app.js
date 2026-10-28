let demoData;
const $=id=>document.getElementById(id), api=async(path,body)=>{const r=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},body:body&&JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.detail||'Request failed');return d};
const upload=async(kind,id)=>{const file=$(id).files[0];if(!file)throw Error('Choose a file first.');const form=new FormData();form.append('file',file);const r=await fetch(`/api/upload/${kind}`,{method:'POST',body:form});const d=await r.json();if(!r.ok)throw Error(d.detail||'Upload failed');return d};
async function checkHealth(attempt = 0) {
  try {
    const response = await fetch('/api/health', {cache: 'no-store', signal: AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error('Server health check failed');
    const h = await response.json();
    $('status').textContent = h.rag_mode === 'local'
      ? 'Local mode active - Gemini is not used. Set RAG_MODE=gemini and restart to use it.'
      : h.gemini_configured
        ? `Gemini configured - ${h.chat_model}`
        : 'Server connected, but GEMINI_API_KEY is missing. Check .env and restart the server.';
  } catch {
    $('status').textContent = attempt < 5
      ? 'Cannot reach the project server yet. Retrying connection...'
      : 'Cannot reach the project server. Start Uvicorn, open http://127.0.0.1:8000 and refresh. This does not mean your Gemini key is missing.';
    if (attempt < 5) setTimeout(() => checkHealth(attempt + 1), 3000);
  }
}
checkHealth();
$('demo').onclick=async()=>{demoData=await api('/api/demo/load',{});$('arsenal').textContent=JSON.stringify(demoData.arsenal_records,null,2);$('targets').textContent=JSON.stringify(demoData.target_records,null,2);$('data').classList.remove('hidden');$('index').disabled=false;};
$('generate').onclick=async()=>{try{demoData=await api('/api/synthetic/generate',{record_count:Number($('recordCount').value),planted_match_rate:Number($('matchRate').value),seed:Number($('seed').value)});$('arsenal').textContent=JSON.stringify(demoData.arsenal_records,null,2);$('targets').textContent=JSON.stringify(demoData.target_records,null,2);$('data').classList.remove('hidden');$('index').disabled=false;$('audit').disabled=true;$('status').textContent=`Generated ${demoData.summary.record_count} records Â· ${demoData.summary.planted_matches} planted links Â· seed ${demoData.summary.seed}`;}catch(e){alert(e.message)}};
$('uploadArsenal').onclick=async()=>{try{const d=await upload('arsenal','arsenalFile');demoData={...(demoData||{}),...d};$('arsenal').textContent=JSON.stringify(d.arsenal_records,null,2);$('data').classList.remove('hidden');$('index').disabled=false;$('status').textContent=`Loaded ${d.arsenal_records.length} Arsenal records`;}catch(e){alert(e.message)}};
$('uploadTargets').onclick=async()=>{try{const d=await upload('targets','targetFile');demoData={...(demoData||{}),...d};$('targets').textContent=JSON.stringify(d.target_records,null,2);$('data').classList.remove('hidden');$('audit').disabled=false;$('status').textContent=`Loaded ${d.target_records.length} target records`;}catch(e){alert(e.message)}};
$('index').onclick=async()=>{const button=$('index');try{button.disabled=true;button.textContent='Indexing Arsenalâ€¦';$('status').textContent='Creating embeddings with Gemini and saving the local vector indexâ€¦';const r=await api('/api/index',{arsenal_records:demoData.arsenal_records});$('status').textContent=`Arsenal indexed: ${r.indexed_records} persistent vectors`; $('audit').disabled=false}catch(e){$('status').textContent=`Indexing failed: ${e.message}`;alert(e.message)}finally{button.disabled=false;button.textContent='2. Index Arsenal'}};

const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const percent=value=>(value*100).toFixed(1)+' / 100';
let activeReport;
$('audit').onclick=async()=>{try{
  $('audit').disabled=true;$('audit').textContent='Assessing…';
  const r=await api('/api/audit',{target_records:demoData.target_records,top_k:4});activeReport=r;
  $('results').classList.remove('hidden');
  $('reportMeta').textContent=`Report ${r.report_id} · ${new Date(r.created_at).toLocaleString()}`;
  $('cards').innerHTML=r.records.map((x,i)=>`<article class="card"><span class="tier">${escapeHtml(x.decision || x.risk_tier)}</span><strong>${escapeHtml(x.target_id)}</strong><div class="risk">${percent(x.risk_score)}</div><p><b>Assessment:</b> ${escapeHtml(x.assessment.predicted_identity)}</p><p>Source ${escapeHtml(x.assessment_mode)} · heuristic evidence ${x.assessment.confidence} · margin ${x.candidate_margin ?? "legacy"} · ${x.tokens_spent} tokens · ${x.latency_seconds ?? "?"}s</p><p>Score is not an identification probability. Abstention does not establish anonymity.</p><p class="evidence">${x.assessment.evidence.map(e=>'• '+escapeHtml(e)).join('<br>')||escapeHtml(x.assessment.rationale)}</p><button class="anonymize" data-record="${i}">Find anonymization options</button><p class="evidence" role="status"></p></article>`).join('');
}catch(e){alert(e.message)}finally{$('audit').disabled=false;$('audit').textContent='3. Run RAG audit'}};

function downloadJson(value,name){
  const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function showComparison(data){
  let panel=$('anonymizationResults');
  if(!panel){panel=document.createElement('section');panel.id='anonymizationResults';$('results').after(panel);}
  panel.innerHTML=`<h2>Anonymization options · ${escapeHtml(data.target_id)}</h2><p>${escapeHtml(data.method)}</p><div class="comparison-summary"><b>Re-tested baseline: ${percent(data.baseline.risk_score)}</b><span>Original audit: ${percent(data.original_audit_score)} · source: ${escapeHtml(data.baseline.assessment_mode)}</span></div><p class="evidence">The current baseline may differ from the original because model responses or the index can change. Each option is tested independently from the original record.</p><div class="options-grid">${data.recommendations.map((p,i)=>`<article class="card option"><h3>${escapeHtml(p.title)}</h3><p class="delta">${p.comparable?`${percent(data.baseline.risk_score)} → ${percent(p.result.risk_score)}`:'Comparison unavailable'}</p><p><b>${p.comparable?(p.reduction_points>0?`${p.reduction_points.toFixed(1)} score points lower`:p.reduction_points<0?`${Math.abs(p.reduction_points).toFixed(1)} score points higher`:'No score change'):escapeHtml(p.status)}</b></p><p>${escapeHtml(p.why)}</p><table><thead><tr><th>Field</th><th>Original</th><th>Released</th></tr></thead><tbody>${p.changes.map(c=>`<tr><td>${escapeHtml(c.field.replaceAll('_',' '))}</td><td>${escapeHtml(c.before)}</td><td>${c.after===null?'Suppressed':escapeHtml(c.after)}</td></tr>`).join('')}</tbody></table><p><b>Information lost:</b> ${escapeHtml(p.utility_tradeoff)}</p>${p.result?`<details><summary>Re-audit evidence · ${escapeHtml(p.result.assessment_mode)}</summary><p>${escapeHtml(p.result.assessment.predicted_identity)}</p><p>${escapeHtml(p.result.assessment.rationale)}</p><ul>${p.result.assessment.evidence.map(e=>`<li>${escapeHtml(e)}</li>`).join('')}</ul></details>`:''}<details><summary>Released record preview</summary><pre>${escapeHtml(JSON.stringify(p.preview,null,2))}</pre></details><button data-download="${i}">Download transformed record</button></article>`).join('')}</div><p class="evidence">${escapeHtml(data.limitations)}</p><p>Research: ${data.sources.map(s=>`<a href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(s.title)}</a>`).join(' · ')}</p><button id="downloadComparison">Download comparison report</button>`;
  panel.querySelectorAll('[data-download]').forEach(button=>button.onclick=()=>downloadJson(data.recommendations[Number(button.dataset.download)].preview,'transformed-record.json'));
  $('downloadComparison').onclick=()=>downloadJson(data,'anonymization-comparison.json');
  panel.scrollIntoView({behavior:'smooth',block:'start'});
}
$('cards').addEventListener('click',async event=>{
  const button=event.target.closest('[data-record]');if(!button)return;
  const status=button.nextElementSibling;
  document.querySelectorAll('.anonymize').forEach(b=>b.disabled=true);
  button.textContent='Testing five options…';status.textContent='Re-auditing the original and five transformed copies. Gemini mode makes six embedding and six assessment requests; this may take a few minutes.';
  try{const result=await api('/api/anonymize',{report_id:activeReport.report_id,record_index:Number(button.dataset.record)});showComparison(result);status.textContent='Comparison saved. Original target data is unchanged.';}
  catch(e){status.textContent=e.message;}
  finally{document.querySelectorAll('.anonymize').forEach(b=>b.disabled=false);button.textContent='Find anonymization options';}
});
