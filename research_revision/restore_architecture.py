from pathlib import Path
p=Path(__file__).with_name('build_paper.py')
s=p.read_text(encoding='utf-8')
a=s.index("# PAGE 2:")
b=s.index("# PAGE 3:",a)
s=s[:a]+'''# PAGE 2: restored architecture with operational explanation and algorithm.
page();columns(doc.sections[-1],1);heading('III. System and Verification Method')
pp=doc.add_paragraph();pp.alignment=WD_ALIGN_PARAGRAPH.CENTER
pp.paragraph_format.space_after=Pt(0);pp.paragraph_format.keep_with_next=True
pp.add_run().add_picture(str(ROOT/'assets/architecture.png'),width=Inches(6.65))
p('Fig. 1. Application architecture and optional mitigation re-audit loop. The seven stages are explained below. Utility preservation is evaluated empirically; it is not guaranteed by anonymization.','figure caption',8)
s=doc.add_section(WD_SECTION_START.CONTINUOUS);columns(s,2)
heading('A. Architecture and data flow',True)
p('Figure 1 shows the implemented LLM-assisted application. (1) The web interface and FastAPI backend accept uploaded or synthetic records and trigger audits. (2) Narrative construction serializes observed attributes and embeds target and auxiliary profiles. (3) ChromaDB retrieves cosine top-k candidates. (4) Gemini receives the target and retrieved evidence and returns a constrained JSON nomination. The LLM is therefore an assessment component within the actual project.')
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

''' + s[b:]
p.write_text(s,encoding='utf-8')
