"""Optional PostgreSQL English lexeme derivation for versioned source chunks."""
from __future__ import annotations


async def english_stem_features(conn, chunks):
    """Derive English lexemes alongside, never instead of, original lexical terms."""
    version=await conn.fetchval("SELECT current_setting('server_version')")
    rows=await conn.fetch("""SELECT p.ordinality,tsvector_to_array(to_tsvector('pg_catalog.english'::regconfig,p.body)) AS lexemes
        FROM unnest($1::text[]) WITH ORDINALITY AS p(body,ordinality) ORDER BY p.ordinality""",chunks)
    limit=1024
    vectors=[]
    for row in rows:
        lexemes=list(row['lexemes'])
        vectors.append({'lexemes':lexemes[:limit],'lexeme_count_before_limit':len(lexemes),'truncated':len(lexemes)>limit})
    return {'profile':{'kind':'postgresql_text_search_english','configuration':'pg_catalog.english',
        'server_version':version,'maximum_lexemes_per_chunk':limit},
        'coverage':{'chunk_count':len(vectors),'truncated_chunks':sum(item['truncated'] for item in vectors)},'vectors':vectors}
