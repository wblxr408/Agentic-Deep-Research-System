"""Disclosure projections leave original owner-bound evidence identities intact."""
from __future__ import annotations

import logging
import re
import traceback

from app.data_governance import SECRET_PATTERN,scrub_urls,sensitive_url

VERSION='adrs-disclosure-v1'
REDACTED='[access credential redacted]'
SECRET_FIELDS={'api_key','apikey','access_token','refresh_token','client_secret','password','passwd','authorization',
    'private_key','fallback_api_key','secret','x-amz-signature','x-amz-security-token','x-goog-signature'}
NORMALIZED_SECRET_FIELDS={name.replace('-','_') for name in SECRET_FIELDS}
PRIVATE_KEY=re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?(?:-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\Z)')
ASSIGNMENT=re.compile(r'''(?ix)(["']?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client_secret|password|passwd|authorization)["']?\s*[:=]\s*)
    (["'])([^"'\r\n]+)\2''')


def redact_text(value):
    if not isinstance(value,str):return value
    value=PRIVATE_KEY.sub(REDACTED,value)
    value=SECRET_PATTERN.sub(REDACTED,scrub_urls(value))
    def assignment(match):
        sample=match[3].strip()
        if sample.startswith(('<','${','[redacted]','[access credential redacted]')) or sample.upper().startswith('YOUR_'):
            return match[0]
        return match[1]+match[2]+REDACTED+match[2]
    return ASSIGNMENT.sub(assignment,value)


def projection(value,*,depth=0):
    if depth>60:return '[disclosure nesting limit]'
    if isinstance(value,str):return redact_text(value)
    if isinstance(value,(list,tuple)):return [projection(item,depth=depth+1) for item in value]
    if not isinstance(value,dict):return value
    result={}
    for key,item in value.items():
        normalized=str(key).casefold().replace('-','_')
        if normalized in NORMALIZED_SECRET_FIELDS and isinstance(item,str) and item:
            result[key]=REDACTED
        elif normalized in {'token','signature','sig','session_token'} and isinstance(item,str) and len(item)>12:
            result[key]=REDACTED
        elif normalized in {'source_url','url'} and isinstance(item,str) and item.startswith(('https://','http://')) and sensitive_url(item):
            # Do not make a redacted capability URL appear to be a working public citation.
            result[key]=''
        else:result[key]=projection(item,depth=depth+1)
    return result


def ensure_report_disclosure(report):
    from app.llm_budget import TokenBudgetExceeded
    if redact_text(report)!=report:raise TokenBudgetExceeded('report_disclosure_requires_revision')


def report_history_projection(payload):
    safe=projection(payload)
    changed=safe.get('report')!=payload.get('report')
    if changed and safe.get('kind')=='report':
        safe['status']='saved_draft'
        safe['audit']={**(safe.get('audit') or {}),'needs_review':True,'disclosure_requires_revision':True}
    safe['disclosure']={**(safe.get('disclosure') or {}),'version':VERSION,
        'redacted':changed or bool((safe.get('disclosure') or {}).get('redacted')),
        'requires_reaudit':changed or bool((safe.get('disclosure') or {}).get('requires_reaudit'))}
    return safe


def install_log_redaction():
    previous=logging.getLogRecordFactory()
    if getattr(previous,'adrs_disclosure',False):return
    def factory(*args,**kwargs):
        record=previous(*args,**kwargs)
        try:
            if isinstance(record.msg,dict):record.msg=projection(record.msg)
            record.msg=redact_text(record.getMessage());record.args=()
            if record.exc_info:
                record.exc_text=redact_text(''.join(traceback.format_exception(*record.exc_info)))
                record.exc_info=None
            elif record.exc_text:record.exc_text=redact_text(record.exc_text)
        except (TypeError,ValueError):
            record.msg='[log formatting unavailable]';record.args=();record.exc_info=None;record.exc_text=None
        return record
    factory.adrs_disclosure=True
    logging.setLogRecordFactory(factory)


def structured_log_projection(logger,method,event):
    return projection(event)
