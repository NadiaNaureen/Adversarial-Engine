"""Author the six-page manuscript using the retained conference paper styles."""
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import statistics
import re
from zipfile import ZipFile,ZIP_DEFLATED

from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT,WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches,Pt,RGBColor
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parent
WORK=Path(r'C:\NADIA\Sem7\adver gpt\paper_assets\revision_20261023')
REF=Path(r'C:\NADIA\Sem7\adver gpt\Adversarial_ReID_Engine_Research_Paper_6_Pages.docx')
FINAL=Path(r'C:\NADIA\Sem7\adver gpt\LLM_Privacy_Audit_With_Architecture_6_Pages.docx')
WORK.mkdir(parents=True,exist_ok=True)
D=json.loads((ROOT/'results/paper_numbers.json').read_text())
M=D['metrics'];U=D['utility']
names={'local':'Hash + verification','fs':'Fellegi–Sunter','exact':'Exact match','top1':'Always top candidate','no_margin':'No margin','hash_llm':'Hash + Gemini','full_hash_control':'Hash control','pilot_semantic':'Semantic + verification','pilot_semantic_llm':'Semantic + Gemini','pilot_hash':'Pilot hash'}

def item(method,condition='all',dataset='predictions'):
    return M[f'{dataset}|{method}|{condition}']
def pct(v):return '—' if v is None else f'{100*v:.1f}'
def ms(v):return '—' if v['mean'] is None else f"{pct(v['mean'])} ± {pct(v['sd'])}"
def stat(method,metric='recall',condition='all',dataset='predictions'):return ms(item(method,condition,dataset)[metric])

def font(size,bold=False):return ImageFont.truetype(str(Path('C:/Windows/Fonts')/('timesbd.ttf' if bold else 'times.ttf')),size)
def chart_sensitivity():
    with (ROOT/'results/sensitivity.csv').open() as f:rows=list(csv.DictReader(f))
    im=Image.new('RGB',(1800,930),'white');g=ImageDraw.Draw(im);left,right,top,bottom=180,1730,75,740
    for y in range(0,101,25):
        yy=bottom-y/100*(bottom-top);g.line((left,yy,right,yy),fill='#d9d9d9',width=2);g.text((75,yy-25),str(y),font=font(52),fill='black')
    taus=sorted({float(r['tau']) for r in rows})
    for metric,color,label in [('recall','#165e83','Correct-link recall'),('fpr','#b84d22','Absent false-link rate')]:
        pts=[]
        for tau in taus:
            vals=[float(r[metric]) for r in rows if float(r['tau'])==tau];mean=statistics.mean(vals);sd=statistics.stdev(vals)
            x=left+(tau-.5)/.3*(right-left);y=bottom-mean*(bottom-top);pts.append((x,y));g.line((x,bottom-max(0,mean-sd)*(bottom-top),x,bottom-min(1,mean+sd)*(bottom-top)),fill=color,width=5)
        g.line(pts,fill=color,width=8)
    for tau in [.5,.6,.7,.8]:g.text((left+(tau-.5)/.3*(right-left)-45,bottom+20),f'{tau:.2f}',font=font(52),fill='black')
    g.text((30,10),'%',font=font(52),fill='black');g.text((570,815),'Score threshold τ',font=font(58),fill='black')
    for x,color,label in [(160,'#165e83','Correct-link recall'),(1000,'#b84d22','Absent false links')]:g.line((x,900,x+70,900),fill=color,width=8);g.text((x+90,870),label,font=font(52),fill='black')
    p=WORK/'sensitivity.png';im.save(p);return p

def chart_workflow():
    im=Image.new('RGB',(1800,660),'white');g=ImageDraw.Draw(im)
    labels=[('Profile','fields'),('Candidate','retrieval'),('LLM','nomination'),('Field','checks'),('Link or','abstain')]
    for i,(a,b) in enumerate(labels):
        x=15+i*360;g.rounded_rectangle((x,100,x+330,340),radius=14,outline='#165e83',width=5,fill='#f2f7fa');g.text((x+165,160),a,anchor='mm',font=font(60,True),fill='black')
        words=b.split();line='';lines=[]
        for w in words:
            if len(line+' '+w)>17:lines.append(line);line=w
            else:line=(line+' '+w).strip()
        lines.append(line)
        for j,line in enumerate(lines):g.text((x+165,245+45*j),line,anchor='mm',font=font(60),fill='black')
        if i<4:g.line((x+330,210,x+360,210),fill='#333333',width=5);g.polygon([(x+355,200),(x+365,210),(x+355,220)],fill='#333333')
    g.line((1650,380,1650,500,180,500,180,380),fill='#b84d22',width=6)
    g.polygon([(170,390),(180,375),(190,390)],fill='#b84d22')
    g.text((900,560),'Transform release and re-audit against the same index',anchor='mm',font=font(60),fill='black')
    p=WORK/'workflow.png';im.save(p);return p

def chart_noise():
    conditions=['clean','age_noise','missing','changed','combined_noise','paraphrase'];labels=['Clean','Age ±1','Missing occ.','Changed occ.','Combined','Paraphrase']
    im=Image.new('RGB',(1800,1020),'white');g=ImageDraw.Draw(im);left=380;right=1700
    for i,(condition,label) in enumerate(zip(conditions,labels)):
        y=90+i*135;g.text((15,y+20),label,font=font(60),fill='black')
        for offset,method,color in [(0,'local','#165e83'),(45,'fs','#b84d22')]:
            v=item(method,condition)['recall'];x=left+v['mean']*(right-left);g.rectangle((left,y+offset,x,y+offset+32),fill=color)
            sd=v['sd']*(right-left);g.line((max(left,x-sd),y+offset+16,min(right,x+sd),y+offset+16),fill='black',width=3)
    for v in [0,25,50,75,100]:x=left+v/100*(right-left);g.text((x-30,905),str(v),font=font(52),fill='black')
    g.text((590,965),'Correct-link recall (%)',font=font(54),fill='black')
    p=WORK/'noise.png';im.save(p);return p

doc=Document(REF)
for el in list(doc._element.body):doc._element.body.remove(el)
section=deepcopy(Document(REF).sections[0]._sectPr);doc._element.body.append(section)

def columns(section,n):
    cols=section._sectPr.find(qn('w:cols'))
    if cols is None:cols=OxmlElement('w:cols');section._sectPr.append(cols)
    for c in list(cols):cols.remove(c)
    cols.set(qn('w:num'),str(n));cols.set(qn('w:space'),'360');cols.set(qn('w:equalWidth'),'1')
    section.top_margin=Inches(.75);section.bottom_margin=Inches(1);section.left_margin=Inches(.63);section.right_margin=Inches(.63)
    for el in list(section._sectPr):
        if el.tag in [qn('w:headerReference'),qn('w:footerReference')]:section._sectPr.remove(el)

columns(doc.sections[0],1)

def p(text,style='Body Text',size=None,bold=False,center=False):
    pp=doc.add_paragraph(style=style);pp.paragraph_format.widow_control=True
    pp.paragraph_format.space_after=Pt(4);pp.paragraph_format.space_before=Pt(0)
    pp.paragraph_format.line_spacing=1.0
    if style=='Body Text':pp.paragraph_format.first_line_indent=Inches(.15);pp.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY
    if center:pp.alignment=WD_ALIGN_PARAGRAPH.CENTER;pp.paragraph_format.first_line_indent=Pt(0)
    r=pp.add_run(text);r.font.name='Times New Roman';r.font.size=Pt(size or (8 if style in ['references','figure caption','table copy'] else 10));r.font.color.rgb=RGBColor(0,0,0);r.bold=bold
    num=pp._p.get_or_add_pPr().get_or_add_numPr();num.get_or_add_numId().val=0
    return pp

next_page=False
def heading(text,sub=False):
    global next_page
    pp=p(text,'Heading 2' if sub else 'Heading 1',10)
    pp.paragraph_format.keep_with_next=True;pp.paragraph_format.space_before=Pt(6);pp.paragraph_format.space_after=Pt(4)
    pp.alignment=WD_ALIGN_PARAGRAPH.LEFT if sub else WD_ALIGN_PARAGRAPH.CENTER
    if next_page:pp.paragraph_format.page_break_before=True;next_page=False
    for r in pp.runs:r.italic=sub
    return pp

def page():
    global next_page
    s=doc.add_section(WD_SECTION_START.CONTINUOUS);columns(s,2);next_page=True

def table(caption,headers,rows,widths=None):
    pp=p(caption,'table head',8,center=True);pp.paragraph_format.keep_with_next=True;pp.paragraph_format.space_before=Pt(5)
    t=doc.add_table(rows=1,cols=len(headers));t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
    widths=widths or [3.38/len(headers)]*len(headers)
    for c,w in zip(t.columns,widths):c.width=Inches(w)
    pr=t._tbl.tblPr
    borders=OxmlElement('w:tblBorders')
    for side in ['top','bottom','left','right','insideH','insideV']:
        x=OxmlElement('w:'+side);x.set(qn('w:val'),'single');x.set(qn('w:sz'),'4');x.set(qn('w:color'),'D9D9D9');borders.append(x)
    pr.append(borders)
    for i,vals in enumerate([headers]+rows):
        row=t.rows[0] if i==0 else t.add_row()
        if i==0:row._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
        row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
        for j,(cell,value) in enumerate(zip(row.cells,vals)):
            cell.width=Inches(widths[j]);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tc=cell._tc.get_or_add_tcPr();mar=OxmlElement('w:tcMar')
            for side,amount in [('top',55),('bottom',55),('left',45),('right',45)]:x=OxmlElement('w:'+side);x.set(qn('w:w'),str(amount));x.set(qn('w:type'),'dxa');mar.append(x)
            tc.append(mar)
            if i==0 or i%2==0:
                shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'E7EFF4' if i==0 else 'F6F6F6');tc.append(shade)
            pp=cell.paragraphs[0];pp.style=doc.styles['table copy'];pp.paragraph_format.space_after=Pt(0);pp.paragraph_format.space_before=Pt(0);pp.paragraph_format.line_spacing=1.0
            pp.paragraph_format.keep_with_next=i<len(rows)
            pp.alignment=WD_ALIGN_PARAGRAPH.LEFT if j==0 else WD_ALIGN_PARAGRAPH.CENTER
            r=pp.add_run(str(value));r.font.name='Times New Roman';r.font.size=Pt(8);r.bold=i==0;r.font.color.rgb=RGBColor(0,0,0)
    p('',size=2).paragraph_format.space_after=Pt(0)
    return t

def figure(path,caption):
    pp=doc.add_paragraph();pp.alignment=WD_ALIGN_PARAGRAPH.CENTER;pp.paragraph_format.space_after=Pt(0);pp.paragraph_format.keep_with_next=True
    pp.add_run().add_picture(str(path),width=Inches(3.38));p(caption,'figure caption',8)

title='LLM Assisted Record Linkage Auditing for Tabular Privacy Assessment'
p(title,'paper title',24,center=True)
p('J Nadia Naureen     Anjum Sana     Jai Vinita','Author',11,center=True)
p('Department of Computer Science and Engineering\nVellore Institute of Technology, Chennai, India','Author',10,center=True)
p('nadianaureen@vit.ac.in     anjum.sana2023@vit.ac.in\nCorrespondence: jaivinita.l@vit.ac.in','Author',9,center=True)
s=doc.add_section(WD_SECTION_START.CONTINUOUS);columns(s,2)

# PAGE 1: problem, contribution and related work.
abstract_cloud=''
if 'cloud_predictions|hash_llm|all' in M:
    abstract_cloud=' On the matched full-index cloud subset, Gemini and its local control both attain '+pct(item('hash_llm',dataset='cloud_predictions')['recall']['mean'])+'% recall, with absent false-link rates of '+pct(item('hash_llm',dataset='cloud_predictions')['fpr']['mean'])+'% and '+pct(item('full_hash_control',dataset='cloud_predictions')['fpr']['mean'])+'%, respectively.'
p('Abstract—Removing direct identifiers does not prevent linkage through demographic attributes. We present an LLM-assisted audit engine that retrieves auxiliary candidates, requests a constrained Gemini assessment, verifies field evidence, and either links a record or abstains. The same index supports repeated audits after generalization and suppression. We evaluate five synthetic populations of 10,000 identities using disjoint validation and test identities, six target conditions, and exact-match and Fellegi–Sunter baselines. Across 1,800 test variants, local retrieval and verification achieve '+stat('local')+'% correct-link recall and '+stat('local','fpr')+'% absent-target false links. The probabilistic baseline has lower false-link rates.'+abstract_cloud+' A separately scoped semantic pilot finds no retrieval advantage on these structured profiles. Mitigation is evaluated jointly with release equivalence classes and information loss. The results identify limits caused by literal verification, retrieval errors, and sparse validation samples.','Abstract',9,bold=True)
p('Keywords—Privacy risk assessment, record linkage audit, large language models, semantic retrieval, abstention, anonymization.','Keywords',9)
heading('I. Introduction')
p('Removing names from microdata leaves combinations of age, location, occupation, and gender that may link to external identities. An audit therefore needs both a plausible auxiliary index and a rule for deciding when evidence is inadequate. External-data linking is relevant to quasi-identifier selection [3], and re-identification success depends on available background information [18].')
p('We study an open-set task: the true identity may be absent from the candidate index. A useful auditor must distinguish successful disclosure from wrong attribution. It must also repeat the same attack after protection changes, because generalization can increase the number of compatible candidates. A failed attack is evidence about one attacker configuration, not proof that a release is anonymous.')
p('The intended use is authorized assessment before release, with controlled access to auxiliary data and reports. NIST guidance [20] and ICO guidance [21] motivate contextual risk assessment and review; the engine does not issue a legal compliance certificate.')
p('Our contribution is the integration and evaluation of candidate retrieval, constrained LLM nomination, deterministic verification, explicit abstention, and mitigation re-auditing. We do not claim that three-way decisions are new: uncertain linkage already appears in classical linkage theory [22]. We measure component behavior and provide complete target-level outcome accounting instead of treating a heuristic score as an identification probability.')
heading('II. Related Work')
p('TRIA [2] evaluates text disclosure using a learned identity classifier; PETRE [1] uses risk-oriented explanations to guide further masking. These motivate empirical attacks, but their text datasets and trained models differ from our structured candidate-index task. We therefore use task-matched linkage baselines rather than importing cross-study accuracy or speed claims.')
p('Recent LLM studies examine weak contextual cues [10], online identity linking [11], agentic re-identification defenses [12], and text-anonymization benchmarks [13]. Our experiment instead restricts the LLM to supplied synthetic candidates. It does not test web search, unrestricted identity discovery, or those papers’ attack settings.')
p('Tabular defenses include generalization and suppression [6], diversity and distributional constraints [7], [8], and differential privacy [9]. PrivateSMOTE [4], SafeGen [5], and SDkA [14] transform or synthesize releases; our engine audits the remaining linkage evidence. Synthetic data can retain disclosure signals [19], while local-recoding attacks reveal additional privacy risks [15]. These methods are complementary research context, not an empirical leaderboard.')

# PAGE 2: restored architecture with operational explanation and algorithm.
page();columns(doc.sections[-1],1);heading('III. System and Verification Method')
pp=doc.add_paragraph();pp.alignment=WD_ALIGN_PARAGRAPH.CENTER
pp.paragraph_format.space_after=Pt(0);pp.paragraph_format.keep_with_next=True
pp.add_run().add_picture(str(ROOT/'assets/architecture.png'),width=Inches(5.95))
p('Fig. 1. Application architecture and optional mitigation re-audit loop. The seven stages are explained below. Utility preservation is evaluated empirically; it is not guaranteed by anonymization.','figure caption',8)
s=doc.add_section(WD_SECTION_START.CONTINUOUS);columns(s,2)
heading('A. Architecture and data flow',True)
p('Figure 1 shows the implemented LLM-assisted application. (1) The web interface and FastAPI backend accept uploaded or synthetic records and trigger audits. (2) Narrative construction serializes observed attributes and embeds target and auxiliary profiles. (3) ChromaDB retrieves cosine top-k candidates. (4) Gemini receives the target and retrieved evidence and returns a constrained JSON nomination. This inference-time retrieval architecture [16], [17] uses the LLM as an assessment component within the actual project.')
p('(5) Deterministic validation rejects invented IDs and checks field agreement before applying score and margin thresholds. (6) JSON reports retain retrieved evidence, flags, scores, and decisions. (7) The optional anonymization module creates five variants and sends each back through the same audit index. Evaluated policies use age bands, postal prefixes, medical or occupation suppression, and their combination; the separate global k baseline is experimental. Generic masking examples in the diagram describe possible sensitive fields, not additional benchmark variables. Utility is measured alongside linkage outcomes.')
heading('B. Verified evidence and decision',True)
p('The attacker knows age, postal code, occupation, gender, and medical flag; IDs never enter retrieval features. Medical knowledge is a strong assumption: this is identity linkage, not diagnosis inference. Release k excludes medical flag. Local embeddings hash tokens and bigrams into 256 dimensions; cloud runs use gemini-embedding-001 and gemini-3.5-flash-lite at temperature zero [23]. The harness uses exact cosine search rather than the application’s approximate index.')
p('For observed field f and value v, let n(f,v) count compatible index values and N be index size. Weight w(f)=1+min{c, ln[(N+1)/(n(f,v)+1)]}. Let U and V sum weights for agreement and contradiction, and m count observed fields. Evidence S=max{0,(U−V)/(U+V)}√(m/5), or zero without usable evidence. Age intervals and postal prefixes permit compatible values; occupation paraphrases remain literal mismatches. Scores are rounded to six decimals; IDs break ties.')
p('A proposal must exceed threshold τ and its strongest retrieved competitor by margin γ. Gemini abstention is respected; invalid JSON, out-of-set IDs, and provider failures issue no identity. Model confidence is not verified evidence. The application’s separate margin diagnostic min{1,max(0,Δ)/0.08} does not multiply S. Scores are heuristic support, not identification probabilities. Experimental cloud errors never trigger a local fallback.')
p('Algorithm 1. Verified audit and mitigation re-audit','table head',9,center=True)
for line in [
'Input: release T, fixed index A, k, frozen τ and γ.',
'1. For each original or transformed record t in T:',
'2.   C ← top-k cosine retrieval of observed fields.',
'3.   q ← Gemini(C,t), or best local verified candidate.',
'4.   If invalid q, error, or model abstention: save status; continue.',
'5.   Compute S(q) and Δ ← S(q) − max other S(c).',
'6.   If S(q) ≥ τ and Δ > γ: issue MATCH(q).',
'7.   Else: issue AMBIGUOUS if S(q) ≥ τ; otherwise INSUFFICIENT.',
'8.   Save evidence and decision; keep truth outside model inputs.']:
    pp=p(line,'Body Text',8);pp.paragraph_format.first_line_indent=Pt(0);pp.paragraph_format.space_after=Pt(1);pp.alignment=WD_ALIGN_PARAGRAPH.LEFT

# PAGE 3: reproducible experimental protocol.
page();heading('IV. Experimental Protocol')
heading('A. Populations and identity-disjoint targets',True)
p('We generate independent populations with seeds 11, 22, 33, 44, and 55; each index contains 10,000 synthetic identities. Occupation is sampled from 12 categories, postal code from eight prefixes with 30 suffixes each, and gender from three categories. Age is a clipped occupation-dependent Gaussian over ages 18–85; medical prevalence depends on age. Observable profile collisions are retained rather than rejected. The generator models controlled dependencies and is not a demographic population estimator.')
p('Each seed has 20 present and 20 absent validation identities and 30 present and 30 absent test identities. Present targets copy a sampled candidate before corruption. Absent identities are sampled independently; accidental attribute collisions with indexed people are retained. All six variants of an identity stay in one split. Thus 200 validation identities produce 1,200 variants and 300 test identities produce 1,800 variants across seeds. Clean copies are a sanity check, not a robustness result.')
table('TABLE I. TARGET CONDITIONS', ['Condition','Change from the base identity'],[
('Clean','Unchanged observed fields'),('Age noise','Age changed by −1 or +1'),('Missing','Occupation removed'),('Changed','Occupation replaced with another category'),('Combined noise','Age ±1, occupation missing, postal code resampled'),('Paraphrase','Occupation replaced by a fixed semantic equivalent')],[.85,2.53])
heading('B. Baselines and operating-point selection',True)
p('Exact matching scans the full index and issues an identity only for a unique match with all five fields observed. Fellegi–Sunter (FS) [22] sums log m/u likelihood ratios, assuming conditional independence of comparison fields. Age comparison distinguishes exact and ±1 agreement; postal comparison distinguishes full and prefix agreement. Missing values have a separate level. Add-one-smoothed m and u distributions use 1,200 independently generated paired training examples per seed, with no validation or test entities. FS scores the full index, whereas the engine verifies only retrieved candidates. This is a documented FS implementation, not an execution of Splink or recordlinkage.')
p('For retrieval verification, validation searches k ∈ {4, 8, 16}, cap c ∈ {1, 3}, τ ∈ {0.50, 0.55, …, 0.80}, and γ ∈ {0, 0.04, 0.08, 0.12}. We seek maximum correct-link recall subject to validation absent FPR and present wrong-link rate each ≤5%; ties favor precision and stricter thresholds, then smaller k and cap. Infeasible settings minimize error before recall. FS thresholds range from −4 to 24 by two and margins from {0, 1, 2, 4}. Test labels never select an operating point.')
p('The always-top baseline disables abstention. A second ablation disables only the margin while retuning the score threshold on validation data. Across seeds, validation selects k = 4 and cap c = 1; τ is 0.60 or 0.80 and γ = 0.12. These settings replace the formerly unexplained fixed constants. Sensitivity curves describe fixed test sweeps and do not reselect settings.')
heading('C. Outcomes and cloud experiment scope',True)
p('We retain correct present links C, wrong present links W, present abstentions P_A, absent false links F, and absent abstentions A_A. Recall is C/(C+W+P_A); absent FPR is F/(F+A_A); precision is C/(C+W+F). Coverage is (C+W+F)/n. Ambiguous, insufficient, and error statuses remain distinct in predictions. Every count is checked against n. Tables report mean ± sample SD across five populations; correlated variants are not treated as independent replications.')
p('Cloud targets are fixed before prediction: the first two present and two absent base identities per split and seed, all six conditions. This yields 24 validation and 24 test variants per seed, with only four independent base identities per split. Full-index LLM nomination uses the same hash-retrieved candidates as its control. A separately labelled semantic pilot uses a smaller candidate index. Provider quotas required this scope reduction; it does not support large-index semantic scalability claims. The benchmark prompt is standardized and not byte-identical to the dashboard prompt.')
heading('D. Reproducibility and validation',True)
p('The accompanying research package stores each generated auxiliary population, target identities, split membership, corruption condition, retrieved IDs, scores, selected identity, decision, and raw cloud response. Prediction exports retain one row per target, method, and policy. Aggregation derives counts and figures from these rows; it never copies rounded percentages from an earlier manuscript. Source hashes and model configuration identify the evaluated code. Prompts exclude truth labels, target group labels, and synthetic names.')
p('Six evaluation checks validate identity-disjoint splits, deterministic generation, score equivalence with the application at cap three, complete precision denominators, failure handling, minimum k, and utility handling of coarse intervals. Nineteen existing retrieval and anonymization checks also pass. The new runner is isolated from the production candidate collection. Re-running model calls is not expected to reproduce identical prose or latency; cached outputs preserve the evidence underlying this report.')

# PAGE 4: new empirical results, with all arithmetic derived from prediction exports.
page();heading('V. Linkage Results and Component Ablations')
table('TABLE II. MAIN TEST RESULTS OVER FIVE POPULATIONS (%)',['Method','Recall','Absent FPR','Precision'],[(names[x],stat(x),stat(x,'fpr'),stat(x,'precision')) for x in ['exact','fs','local','no_margin','top1']],[1.02,.78,.78,.80])
p('Table II pools conditions within each seed before summarizing between-seed variation. Local verification increases recall relative to exact matching, but FS has a lower absent false-link rate and higher precision. This is a trade-off, not evidence that the proposed engine is uniformly superior. The always-top rule links every absent identity to somebody and therefore has 100% absent FPR by construction.')
table('TABLE III. COMPLETE OUTCOME COUNTS ON 1,800 VARIANTS',['Method','C','W','P_A','F','A_A'],[(names[x],*[item(x)['totals'][k] for k in ['correct','wrong_present','present_abstain','false_absent','absent_abstain']]) for x in ['exact','fs','local','no_margin','top1']],[1.05,.43,.43,.49,.43,.55])
p('Each row has 900 present and 900 absent variants. For local verification, 276 correct links, 27 wrong present links, and 49 absent false links produce 352 issued identities; pooled precision is 276/352 = 78.4%. Table II instead averages seed-level precision, giving 78.6%. Reporting both definitions prevents a mean-of-ratios discrepancy from appearing to be a counting error. The historical 40-target summary is superseded, not used to reconstruct missing predictions.')
figure(chart_noise(),'Fig. 2. Correct-link recall by condition for local verification (blue) and FS (orange). Whiskers show seed SD; each condition has 150 present and 150 absent variants.')
p('Clean-copy accuracy does not predict performance under corruption. Missing or changed occupation reduces available support, and semantic paraphrases can be retrieved but rejected by literal verification. The detailed condition results and raw candidate lists distinguish retrieval failures from verification failures. Margin abstention reduces wrong-present and absent false links compared with the no-margin ablation, with a small recall change.')
figure(chart_sensitivity(),'Fig. 3. Test sensitivity for the local verifier, with each seed’s validation-selected margin held fixed. Whiskers are seed SD; curves do not select the reported operating point.')
heading('A. Live LLM assessment on the full index',True)
cloudkey='cloud_predictions|hash_llm|all'
if cloudkey in M:
    cloud=item('hash_llm',dataset='cloud_predictions');control=item('full_hash_control',dataset='cloud_predictions');op=D['operational']['full_hash']
    table('TABLE IV. MATCHED FULL-INDEX CLOUD SUBSET (%)',['Method','Recall','Absent FPR','Precision'],[(names[x],stat(x,dataset='cloud_predictions'),stat(x,'fpr',dataset='cloud_predictions'),stat(x,'precision',dataset='cloud_predictions')) for x in ['full_hash_control','hash_llm']],[1.02,.78,.78,.80])
    p(f"On {cloud['totals']['n']} test variants from {cloud['seeds']} populations, Gemini and its matched control both achieve {pct(cloud['recall']['mean'])}% recall; absent FPR is {pct(cloud['fpr']['mean'])}% versus {pct(control['fpr']['mean'])}%. They share full-index candidates and validation identities. All {op['valid']}/{op['n']} final validation/test calls are valid. Quota-limited attempts were retried, never credited as model abstentions. These results involve only 20 base test identities and do not establish statistical significance.")
    if op.get('paid_tier_text_cost_estimate_per_assessment') is not None:
        p(f"Completed assessments average {op['mean_tokens']:.1f} reported tokens and {op['mean_seconds']:.1f} s including scheduler waiting. At published standard paid rates of $0.30/M input and $2.50/M output tokens [23], the mean text-token charge would be ${op['paid_tier_text_cost_estimate_per_assessment']:.6f} per assessment. This estimate excludes embeddings, unavailable retry usage, and other unreported charges; actual billing was not measured.")
else:p('Live cloud component results are still being collected. This authoring build is not the final manuscript.')

# PAGE 5: semantic representation pilot and mitigation accounting.
page();heading('VI. Semantic Retrieval and Mitigation Trade-offs')
heading('A. Controlled semantic component pilot',True)
pilotkey='cloud_predictions|pilot_semantic|all'
if pilotkey in M:
    table('TABLE V. CONTROLLED SEMANTIC PILOT (%)',['Method','Recall','Absent FPR','Precision'],[(names[x],stat(x,dataset='cloud_predictions'),stat(x,'fpr',dataset='cloud_predictions'),stat(x,'precision',dataset='cloud_predictions')) for x in ['pilot_hash','pilot_semantic','pilot_semantic_llm']],[1.02,.78,.78,.80])
    ph=item('pilot_hash',dataset='cloud_predictions');ps=item('pilot_semantic',dataset='cloud_predictions');pl=item('pilot_semantic_llm',dataset='cloud_predictions')
    p('Each pilot index contains 150 candidates: all 50 validation/test present identities plus 100 random distractors. It is deliberately enriched for target presence. Hash and semantic retrieval both achieve '+pct(ps['recall']['mean'])+'% recall; semantic retrieval plus Gemini achieves '+pct(pl['recall']['mean'])+'% recall and '+pct(pl['fpr']['mean'])+'% absent FPR. Thus this pilot does not demonstrate a semantic advantage. Only within-Table V comparisons use matched candidate pools; comparison with Table II would confound index size. The verifier still treats occupation paraphrases literally.')
else:p('The semantic retrieval pilot is subject to a separate embedding quota. Its results must be added only after completed calls and matched controls are available.')
heading('B. Mitigation and release utility',True)
p('We transform the 60 clean test records per seed and re-audit them against the unchanged index using clean-validation thresholds. Policies are ten-year age bands, three-digit postal prefixes, medical suppression, occupation suppression, their combination, and a dataset-level k=5 policy. A predefined global generalization ladder broadens age and postal values and suppresses categorical QIs until every released equivalence class has at least five rows. This is a simple baseline, not a utility-optimal anonymizer.')
table('TABLE VI. LOCAL MITIGATION RESULTS AND INFORMATION LOSS',['Policy','Recall %','FPR %','Loss','Min k'],[(label,stat('local',condition=policy,dataset='mitigation_predictions'),stat('local','fpr',condition=policy,dataset='mitigation_predictions'),f"{U[policy]['normalized_loss']['mean']:.3f}",str(int(U[policy]['min_k']['min']))) for policy,label in [('original','Original'),('age_band','Age bands'),('postal_prefix','Postal prefix'),('medical_suppression','Medical removed'),('occupation_suppression','Occupation removed'),('combined','Combined'),('k5','Global k≥5')]],[.88,.76,.74,.50,.50])
p('Loss averages five field penalties: zero for retained exact values, one for suppression, age interval width/67, and removed postal digits/6. The combined policy changes 80% of cells and suppresses 40%; its normalized loss is 0.527, yet minimum demographic k remains one in every seed. The k-targeted policy reaches minimum k between 14 and 60, with substantially greater information loss. These are properties of the released cohort, not the auxiliary population.')
p('Utility is also checked through age-decade and occupation marginal queries. An age interval spanning multiple decades is unresolved, rather than assigned an invented exact decade. Mean total-variation error is zero for age banding, 0.50 for combined mitigation, and '+f"{U['k5']['marginal_tv']['mean']:.2f}"+' for the global k policy. This narrow workload does not measure downstream predictive utility. Low linkage recall obtained by erasing most information is not an unqualified practical success.')
table('TABLE VII. MITIGATION OUTCOMES ON 300 CLEAN RECORDS',['Policy','C','W','P_A','F','A_A'],[(label,*[item('local',policy,'mitigation_predictions')['totals'][k] for k in ['correct','wrong_present','present_abstain','false_absent','absent_abstain']]) for policy,label in [('original','Original'),('age_band','Age bands'),('postal_prefix','Postal prefix'),('medical_suppression','Medical removed'),('occupation_suppression','Occupation removed'),('combined','Combined'),('k5','Global k≥5')]],[1.05,.43,.43,.49,.43,.55])
p('Each policy has 150 present and 150 absent identities across five seeds. Table VII counts every issued wrong identity and every withheld identity. Precision is undefined when no identity is issued. Ambiguity and insufficiency remain separate in the evidence package. Lower recall with rising false attribution is not sufficient evidence of improved protection.')

# PAGE 6: interpretation, limitations, conclusion, and verified bibliography.
page();heading('VII. Discussion and Limitations')
origmean=statistics.mean(r['means']['original'] for r in D['evidence']);bandmean=statistics.mean(r['means']['age_band'] for r in D['evidence'])
p(f'Age banding broadens compatibility: a released age 30–39 agrees with every candidate in that interval. In this evaluation, mean best-candidate evidence rises from {origmean:.3f} to {bandmean:.3f}, while correct-link recall falls from 95.3% to 80.0%. A target age 35 and candidate age 37 disagree exactly but agree after decade banding; the other fields can then yield stronger support for multiple identities. Candidate retrieval and population weights can also change. False attribution is itself a potential harm, not automatically a beneficial privacy outcome.')
p('Combined suppression can also force abstention mechanically. With only three observed fields, the maximum coverage-damped score is √(3/5) ≈ 0.775, below the clean-validation threshold 0.80 used here. Its zero correct links therefore partly reflect the selected rule, not a guarantee that another attacker cannot link the release. Release k excludes medical flag even though that field is known in this strong attacker experiment; no sensitive-attribute guarantee follows.')
p('Synthetic populations and fixed corruption rules limit external validity. Cloud subsets contain few independent identities, model outputs may vary despite temperature zero, and daily quotas constrain semantic experiments. Exact cosine retrieval differs from the deployed approximate index. We do not infer statistical significance from correlated variants, report a measured billing cost, establish differential privacy, or claim legal compliance. Authorized real-world benchmarks, repeated model calls, broader query workloads, and approximate-index evaluation remain necessary.')
heading('VIII. Conclusion')
p('The engine combines LLM-assisted candidate assessment with verified field evidence, abstention, and repeatable mitigation audits. The expanded evaluation exposes false attribution, missing-field sensitivity, and the utility cost hidden by recall-only reporting. The useful result is an auditable workflow with measured component limits; stronger semantic verification and larger cloud studies require further evaluation before claims of superior privacy or linkage accuracy.')
heading('References')
refs=[
'B. Manzanares-Salor and D. Sánchez, “Enhancing text anonymization via re-identification risk-based explainability,” Knowledge-Based Systems, vol. 310, art. 112945, 2025, doi: 10.1016/j.knosys.2024.112945.',
'B. Manzanares-Salor, D. Sánchez, and P. Lison, “Evaluating the disclosure risk of anonymized documents via a machine learning-based re-identification attack,” Data Mining and Knowledge Discovery, vol. 38, pp. 4040–4075, 2024, doi: 10.1007/s10618-024-01066-3.',
'A. Borrero-Foncubierta, M. Rodriguez-Garcia, A. Muñoz, and J. M. Dodero, “Protecting privacy in the age of big data: exploring data linking methods for quasi-identifier selection,” International Journal of Information Security, vol. 24, art. 37, 2025, doi: 10.1007/s10207-024-00944-7.',
'T. Carvalho, N. Moniz, L. Antunes, and N. Chawla, “Differentially-private data synthetisation for efficient re-identification risk control,” Machine Learning, vol. 114, art. 164, 2025, doi: 10.1007/s10994-025-06799-w.',
'M. Cinquini, M. Marchiori Manerba, F. Mazzoni, F. Pratesi, and R. Guidotti, “SafeGen: safeguarding privacy and fairness through a genetic method,” Machine Learning, vol. 114, art. 227, 2025, doi: 10.1007/s10994-025-06835-9.',
'P. Samarati and L. Sweeney, “Protecting privacy when disclosing information: k-anonymity and its enforcement through generalization and suppression,” SRI International, Tech. Rep. SRI-CSL-98-04, 1998.',
'A. Machanavajjhala, D. Kifer, J. Gehrke, and M. Venkitasubramaniam, “l-diversity: Privacy beyond k-anonymity,” ACM Transactions on Knowledge Discovery from Data, vol. 1, no. 1, art. 3, 2007, doi: 10.1145/1217299.1217302.',
'N. Li, T. Li, and S. Venkatasubramanian, “t-Closeness: Privacy beyond k-anonymity and l-diversity,” ICDE, pp. 106–115, 2007, doi: 10.1109/ICDE.2007.367856.',
'C. Dwork, “Differential privacy,” ICALP, LNCS 4052, pp. 1–12, 2006, doi: 10.1007/11787006_1.',
'M. Ko, J. Jeong, S. S. Thakur, G. Kim, and R. Jia, “From weak cues to real identities: Evaluating inference-driven de-anonymization in LLM agents,” ICML, 2026; arXiv:2603.18382.',
'S. Lermen, D. Paleka, J. Swanson, M. Aerni, N. Carlini, and F. Tramèr, “Large-scale online deanonymization with LLMs,” USENIX Security, pp. 1947–1966, 2026.',
'Z. Li, J. Wen, and T. Li, “LLM anonymization against agentic re-identification,” arXiv:2605.30848v3, 2026.',
'N. Krčo, Z. Yao, M. Meeus, and Y.-A. de Montjoye, “RAT-Bench: A comprehensive benchmark for text anonymization,” arXiv:2602.12806, 2026.',
'A. Majeed and S. O. Hwang, “SDkA: Synthetic data integrated k-anonymity model for data sharing with improved utility,” IT Professional, vol. 28, no. 1, pp. 73–80, 2026, doi: 10.1109/MITP.2025.3634142.',
'S. Chhillar, M. K. Righi, R. E. Sutter, and E. M. Kornaropoulos, “Exposing privacy risks in anonymizing clinical data: Combinatorial refinement attacks on k-anonymity without auxiliary information,” ACM CCS, pp. 4259–4273, 2025, doi: 10.1145/3719027.3765139.',
'P. Lewis et al., “Retrieval-augmented generation for knowledge-intensive NLP tasks,” Advances in Neural Information Processing Systems, vol. 33, pp. 9459–9474, 2020.',
'Y. Gao et al., “Retrieval-augmented generation for large language models: A survey,” arXiv:2312.10997v5, 2024.',
'L. Rocher, J. M. Hendrickx, and Y.-A. de Montjoye, “Estimating the success of re-identifications in incomplete datasets using generative models,” Nature Communications, vol. 10, art. 3069, 2019, doi: 10.1038/s41467-019-10933-3.',
'T. Stadler, B. Oprisanu, and C. Troncoso, “Synthetic data—anonymisation groundhog day,” USENIX Security, pp. 1451–1468, 2022.',
'S. Garfinkel, B. Guttman, J. Near, A. Dajani, and P. Singer, “De-identifying government datasets: Techniques and governance,” NIST SP 800-188, 2023, doi: 10.6028/NIST.SP.800-188.',
'Information Commissioner’s Office, “How do we ensure anonymisation is effective?” Anonymisation guidance, accessed Oct. 23, 2026. https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-sharing/anonymisation/how-do-we-ensure-anonymisation-is-effective/',
'I. P. Fellegi and A. B. Sunter, “A theory for record linkage,” Journal of the American Statistical Association, vol. 64, no. 328, pp. 1183–1210, 1969, doi: 10.1080/01621459.1969.10501049.',
'Google, “Gemini API models, embeddings and pricing,” Google AI for Developers, accessed Oct. 23, 2026. https://ai.google.dev/gemini-api/docs/pricing',
]
order=[]
for pp in doc.paragraphs:
    for match in re.finditer(r'\[(\d+)\]',pp.text):
        number=int(match.group(1))
        if number not in order:order.append(number)
assert set(order)==set(range(1,len(refs)+1))
crosswalk={old:new for new,old in enumerate(order,1)}
for pp in doc.paragraphs:
    for run in pp.runs:
        if re.search(r'\[\d+\]',run.text):run.text=re.sub(r'\[(\d+)\]',lambda m:f'[{crosswalk[int(m.group(1))]}]',run.text)
refs=[refs[old-1] for old in order]
(ROOT/'citation_crosswalk.json').write_text(json.dumps({'original_to_final':crosswalk,'first_appearance_order':order},indent=2),encoding='utf-8')
for i,r in enumerate(refs,1):
    pp=p(f'[{i}] {r}','references',8);pp.paragraph_format.first_line_indent=Pt(-12);pp.paragraph_format.left_indent=Pt(12);pp.paragraph_format.space_after=Pt(3);pp.paragraph_format.keep_together=True
doc.core_properties.title=title;doc.core_properties.author='J Nadia Naureen; Anjum Sana; Jai Vinita';doc.core_properties.subject='Reproducible privacy audit and component evaluation'
doc.save(FINAL)
# Preserve the source style, numbering, and theme packages byte for byte.
with ZipFile(REF) as z:preserve={n:z.read(n) for n in z.namelist() if n in ['word/styles.xml','word/numbering.xml','word/theme/theme1.xml']}
with ZipFile(FINAL) as z:parts={n:z.read(n) for n in z.namelist()}
parts.update(preserve)
with ZipFile(FINAL,'w',ZIP_DEFLATED) as z:
    for n,v in parts.items():z.writestr(n,v)
(WORK/'manuscript_text.txt').write_text('\n'.join(p.text for p in doc.paragraphs),encoding='utf-8')
(WORK/'references.json').write_text(json.dumps(refs,indent=2,ensure_ascii=False),encoding='utf-8')
print(FINAL)
print('Body words',sum(len(p.text.split()) for p in doc.paragraphs))
print('Reference SHA256',hashlib.sha256(REF.read_bytes()).hexdigest())




