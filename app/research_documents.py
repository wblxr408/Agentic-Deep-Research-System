"""Bounded document worker and compatibility PDF reader for retained structure."""
from __future__ import annotations

import io
import json
import os
import re
import sys
import tempfile
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from decimal import Decimal

MAX_DOCUMENT_CHARS = 160000
MAX_PDF_PAGES = 80


def scholarly_text_sections(text: str) -> list[dict]:
    """Locate substantial retained sections; a TOC alone supplies no body."""
    headings=list(re.finditer(r'(?im)^(?:\d+(?:\.\d+)*\.?\s+)?(?P<label>introduction|materials\s+and\s+methods|methods|methodology|experimental(?:\s+(?:setup|design))?|evaluation|results?(?:\s+and\s+discussion)?|discussion|conclusions?|limitations|references|引言|研究方法|实验方法|实验结果|讨论|结论|参考文献)\s*$',text))
    sections=[]
    for index,heading in enumerate(headings):
        end=headings[index+1].start() if index+1<len(headings) else len(text)
        if end-heading.end()<200 and heading['label'].casefold() not in {'references','参考文献'}:
            continue
        sections.append({'label':heading['label'],'start':heading.start(),'body_start':heading.end(),'end':end})
    return sections


def read_document(raw: bytes, *, format: str, timeout: float, max_pages: int = MAX_PDF_PAGES,
        max_chars: int = MAX_DOCUMENT_CHARS, allow_ocr: bool = False, frozen_policy: dict | None = None) -> dict:
    from app.channels.execution import CommandRunner
    from app.channels.models import ChannelError
    from app.config import get_settings
    from app.document_structure import VERSION
    if format not in {'pdf','docx','txt','md','json'}:raise ChannelError('unsupported_document_format')
    if format=='pdf' and not raw.startswith(b"%PDF-"):
        raise ChannelError("invalid_pdf")
    config=get_settings().document_parsing
    frozen_policy=frozen_policy or {}
    if frozen_policy.get('schema_version') not in {None,VERSION}:raise ChannelError('document_parser_policy_version_unavailable')
    effective_timeout=max(0.01,min(config.timeout_seconds,timeout,frozen_policy.get('timeout_seconds',config.timeout_seconds)))
    options={'max_pages':max_pages,'max_chars':min(max_chars,config.max_chars,frozen_policy.get('max_chars',config.max_chars)),'allow_ocr':allow_ocr,
        'ocr_enabled':config.ocr_enabled and frozen_policy.get('ocr_enabled',True),
        'ocr_language':frozen_policy.get('ocr_language',config.ocr_language),
        'ocr_binary':config.ocr_binary,'max_ocr_pages':min(config.max_ocr_pages,frozen_policy.get('max_ocr_pages',config.max_ocr_pages)),'timeout_seconds':effective_timeout}
    with tempfile.TemporaryDirectory(prefix="adrs-document-") as directory:
        path = Path(directory) / ('input.'+format)
        path.write_bytes(raw)
        output = CommandRunner().run([sys.executable, str(Path(__file__).resolve()), str(path),format,json.dumps(options)],
            timeout=effective_timeout, max_bytes=8*1024*1024)
    payload = json.loads(output)
    if payload.get("error"):
        raise ChannelError(payload["error"])
    return payload


def read_pdf(raw: bytes, *, timeout: float) -> dict:
    return read_document(raw,format='pdf',timeout=timeout)


def _extract(path: Path, format='pdf', options=None) -> dict:
    # Direct-script workers need the confirmed project root for app imports.
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
    from app.document_structure import parse_text,parse_docx,VERSION
    from app.document_pdf import parse_pdf
    options=options or {};raw=path.read_bytes();limit=int(options.get('max_chars',MAX_DOCUMENT_CHARS))
    if format=='pdf':result=parse_pdf(raw,max_chars=limit,max_pages=int(options.get('max_pages',MAX_PDF_PAGES)),options=options)
    elif format=='docx':result=parse_docx(raw,max_chars=limit)
    else:result=parse_text(raw,format=format,max_chars=limit)
    result['parse_profile']={'schema_version':VERSION,'engine':result['parser_engine'],'engine_version':result.get('parser_engine_version'),'max_chars':limit,
        **{key:options.get(key) for key in ('max_pages','allow_ocr','ocr_enabled','ocr_language','max_ocr_pages','timeout_seconds')}}
    return result


if __name__ == "__main__":
    # Parser warnings must not corrupt the bounded JSON channel or leak document
    # content through diagnostics merged by the existing command runner.
    with open(os.devnull, "w") as sink, redirect_stdout(sink), redirect_stderr(sink):
        try:
            payload = _extract(Path(sys.argv[1]),sys.argv[2] if len(sys.argv)>2 else 'pdf',json.loads(sys.argv[3]) if len(sys.argv)>3 else None)
        except ImportError:
            payload = {"error": "document_dependency_missing"}
        except (ValueError,KeyError,zipfile.BadZipFile) as error:
            known={'invalid_docx_signature','docx_expansion_limit','docx_xml_limit','invalid_docx_body',
                'invalid_docx_table_span','encrypted_pdf','invalid_pdf_signature'}
            payload = {"error": str(error) if str(error) in known else 'invalid_document_structure'}
        except Exception:
            payload = {"error": "document_parse_failed"}
    def json_number(value):
        if isinstance(value,Decimal):return float(value)
        raise TypeError('unsupported_parser_output_type')
    print(json.dumps(payload, ensure_ascii=True,default=json_number))
