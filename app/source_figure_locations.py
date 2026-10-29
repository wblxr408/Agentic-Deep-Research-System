"""Select original PDF pages by literal captions, not by model image claims.

The caller must separately check current owner/task/evidence and stored assets.
This only locates whole original pages; it does not assert figure segmentation.
"""
from __future__ import annotations

import re
from uuid import UUID


def select_source_pages(reading, evidence, *, max_pages=8, per_output=2):
    max_pages=min(8,max(1,max_pages)) if type(max_pages) is int else 8
    per_output=min(2,max(1,per_output)) if type(per_output) is int else 2
    result={'pages':[],'pending':[]}
    if not isinstance(reading,dict) or not isinstance(reading.get('cards'),list):return result
    if not isinstance(evidence,list):return result
    sources={row['evidence_id']:row for row in evidence if isinstance(row,dict) and isinstance(row.get('evidence_id'),str)}
    selected={};by_output={}

    def pending(output_id,reason):
        if len(result['pending'])<512:result['pending'].append({'output_id':output_id,'reason':reason})

    if len(reading['cards'])>20:pending(None,'card_limit')
    for card in reading['cards'][:20]:
        if not isinstance(card,dict):pending(None,'invalid_card');continue
        output_id=card.get('output_id');title=card.get('title');refs=card.get('figure_references')
        if not isinstance(output_id,str) or not 1<=len(output_id)<=160 or not isinstance(title,str):
            pending(None,'invalid_output_identity');continue
        if not isinstance(refs,list):pending(output_id,'invalid_references');continue
        if len(refs)>20:pending(output_id,'reference_limit')
        for reference in refs[:20]:
            if not isinstance(reference,dict):pending(output_id,'invalid_reference');continue
            proof=reference.get('proof');label=reference.get('label')
            if not isinstance(proof,dict) or not isinstance(label,str) or not 2<=len(label)<=120:
                pending(output_id,'invalid_reference');continue
            if not isinstance(proof.get('evidence_id'),str):pending(output_id,'invalid_evidence_identity');continue
            source=sources.get(proof['evidence_id'])
            meta=(source.get('acquisition') or {}) if source else {}
            if not isinstance(meta,dict):pending(output_id,'invalid_source_metadata');continue
            asset=meta.get('source_asset') or {}
            if (not source or meta.get('format')!='pdf' or meta.get('coverage')=='discovery_only'
                    or not isinstance(asset,dict) or asset.get('status')!='retained' or asset.get('format')!='pdf'):
                pending(output_id,'original_pdf_not_retained');continue
            try:asset_id=str(UUID(asset['asset_id']))
            except (ValueError,TypeError,KeyError,AttributeError):pending(output_id,'invalid_asset_identity');continue
            content=source.get('content');start,end=proof.get('start'),proof.get('end');quote=proof.get('quote')
            if (not isinstance(content,str) or not isinstance(quote,str) or not 3<=len(quote)<=2400
                    or type(start) is not int or type(end) is not int or not 0<=start<end<=len(content)
                    or content[start:end]!=quote):
                pending(output_id,'source_proof_changed');continue
            label_match=re.fullmatch(r'(Figure|Fig\.?|Table|图|表)\s*(\d+(?:\.\d+)?)(\([a-z]\))?',label.strip(),re.I)
            if not label_match:pending(output_id,'unsupported_label');continue
            kind,number,panel=label_match.groups()
            kind_pattern=r'(?:Figure|Fig\.?)' if kind.casefold().startswith('fig') else re.escape(kind)
            pattern=r'^\s*'+kind_pattern+r'\s*'+re.escape(number)+r'(?!\d|\.\d)'+re.escape(panel or '')+r'\s*[:：.．]'
            # A prose mention on some other page is not a caption location.
            if not re.match(pattern,quote,re.I) or content[content.rfind('\n',0,start)+1:start].strip():
                pending(output_id,'not_a_literal_caption');continue
            page_rows=meta.get('pages')
            if not isinstance(page_rows,list):pending(output_id,'page_metadata_unavailable');continue
            pages=[page for page in page_rows[:80] if isinstance(page,dict)
                and type(page.get('number')) is int and 1<=page['number']<=80
                and type(page.get('start')) is int and type(page.get('end')) is int
                and 0<=page['start']<=start<end<=page['end']<=len(content)]
            if len(pages)!=1:pending(output_id,'page_not_unambiguous');continue
            page=pages[0]['number'];supplied=reference.get('page')
            if supplied is not None and (type(supplied) is not int or supplied!=page):
                pending(output_id,'requested_page_conflicts');continue
            key=(asset_id,page);used=by_output.setdefault(output_id,set())
            if key not in used and len(used)>=per_output:pending(output_id,'output_page_limit');continue
            if key not in selected:
                if len(selected)>=max_pages:pending(output_id,'total_page_limit');continue
                row={'asset_id':asset_id,'page':page,'source_url':str(source.get('source_url') or '')[:2048],
                    'evidence_ids':[],'output_ids':[],'titles':[],'captions':[],'proofs':[],
                    'presentation':'original_pdf_page_not_segmented_figure'}
                selected[key]=row;result['pages'].append(row)
            used.add(key);row=selected[key]
            for field,value in (('evidence_ids',proof['evidence_id']),('output_ids',output_id),('titles',title[:300])):
                if value not in row[field]:row[field].append(value)
            if len(row['captions'])<12 and quote not in row['captions']:row['captions'].append(quote)
            located={key:proof[key] for key in ('evidence_id','start','end','quote')}
            if len(row['proofs'])<12 and located not in row['proofs']:row['proofs'].append(located)
    return result
