from __future__ import annotations


def test_chunk_text_uses_overlap():
    from app.api.documents import _chunk_text

    chunks = _chunk_text("a" * 950, chunk_size=400, overlap=80)

    assert len(chunks) == 3
    assert chunks[0][-80:] == chunks[1][:80]


def test_json_extraction_flattens_nested_content():
    from app.api.documents import _extract_plain_text

    text = _extract_plain_text(
        "sample.json",
        "json",
        b'{"title":"Doc","items":[{"body":"A"},{"body":"B"}]}',
    )

    assert "title: Doc" in text
    assert "body: A" in text
    assert "body: B" in text


def test_supported_extensions_include_requested_formats():
    from app.api.documents import ALLOWED_EXTENSIONS

    assert {"json", "md", "docx", "pdf", "txt"}.issubset(ALLOWED_EXTENSIONS)
