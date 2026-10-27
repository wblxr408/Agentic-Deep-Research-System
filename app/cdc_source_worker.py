"""One bounded source-DB operation; credentials arrive only on stdin."""
from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import sys

MAX_EVENT_BYTES=256*1024
MAX_BATCH=20


def _address(endpoint):
    networks=[ipaddress.ip_network(item,strict=False) for item in endpoint['allowed_networks']]
    results=socket.getaddrinfo(endpoint['host'],endpoint['port'],type=socket.SOCK_STREAM)
    addresses=list(dict.fromkeys(item[4][0] for item in results))
    if not addresses or any(not any(ipaddress.ip_address(address) in network for network in networks) for address in addresses):
        raise ValueError('cdc_endpoint_address_not_authorized')
    return addresses[0]


def _connection(endpoint,credentials):
    import psycopg2
    address=_address(endpoint)
    # If the installed libpq does not understand sslcertmode, fail closed;
    # never retry with the host's default client certificate or password file.
    return psycopg2.connect(host=endpoint['host'],hostaddr=address,port=endpoint['port'],dbname=endpoint['database'],
        user=credentials['username'],password=credentials['password'],sslmode='verify-full',
        sslrootcert=endpoint['ca_path'],sslcertmode='disable',gssencmode='disable',passfile=os.devnull,
        connect_timeout=8,options='-c statement_timeout=10000 -c lock_timeout=3000')


def _read(conn,endpoint,consumer_id,excluded,check_ids):
    from psycopg2 import sql
    schema=sql.Identifier(endpoint['schema'])
    with conn.cursor() as cursor:
        query=sql.SQL('''SELECT e.event_id::text,LEFT(e.document_key,201),e.revision,LEFT(e.operation,20),
            CASE WHEN octet_length(e.title)<=800 THEN e.title ELSE NULL END,
            CASE WHEN octet_length(e.content)<={limit} THEN e.content ELSE NULL END,
            octet_length(e.title),octet_length(e.content),e.is_snapshot,e.snapshot_id::text,e.created_at
            FROM {schema}.events e WHERE NOT EXISTS (SELECT 1 FROM {schema}.acknowledgments a
                WHERE a.consumer_id=%s::uuid AND a.event_id=e.event_id)
            AND NOT (e.event_id=ANY(%s::uuid[])) ORDER BY e.created_at,e.event_id LIMIT {batch}''').format(
                schema=schema,limit=sql.Literal(MAX_EVENT_BYTES),batch=sql.Literal(MAX_BATCH))
        cursor.execute(query,(consumer_id,excluded))
        rows=cursor.fetchall()
        snapshot_query=sql.SQL('''SELECT s.snapshot_id::text,s.row_count,
            (SELECT COUNT(*) FROM {schema}.events e WHERE e.snapshot_id=s.snapshot_id),
            (SELECT COUNT(*) FROM {schema}.events e WHERE e.snapshot_id=s.snapshot_id
                AND NOT EXISTS(SELECT 1 FROM {schema}.acknowledgments a WHERE a.consumer_id=%s::uuid AND a.event_id=e.event_id))
            FROM {schema}.snapshots s ORDER BY s.created_at DESC,s.snapshot_id DESC LIMIT 1''').format(schema=schema)
        cursor.execute(snapshot_query,(consumer_id,));snapshot=cursor.fetchone()
        ack_query=sql.SQL('''SELECT event_id::text FROM {schema}.acknowledgments
            WHERE consumer_id=%s::uuid AND event_id=ANY(%s::uuid[])''').format(schema=schema)
        cursor.execute(ack_query,(consumer_id,check_ids));confirmed=[row[0] for row in cursor.fetchall()]
    return {'events':[{'event_id':row[0],'document_key':row[1],'revision':row[2],'operation':row[3],
        'title':row[4],'content':row[5],'title_bytes':row[6],'content_bytes':row[7],
        'is_snapshot':row[8],'snapshot_id':row[9],'created_at':row[10].isoformat()} for row in rows],
        'snapshot':{'id':snapshot[0],'rows':snapshot[1],'events':snapshot[2],'pending':snapshot[3]} if snapshot else None,
        'confirmed_acks':confirmed}


def _ack(conn,endpoint,consumer_id,event_ids):
    from psycopg2 import sql
    if len(event_ids)>MAX_BATCH:raise ValueError('cdc_ack_batch_limit')
    query=sql.SQL('''INSERT INTO {schema}.acknowledgments(consumer_id,event_id) VALUES(%s::uuid,%s::uuid)
        ON CONFLICT(consumer_id,event_id) DO NOTHING''').format(schema=sql.Identifier(endpoint['schema']))
    with conn.cursor() as cursor:
        for event_id in event_ids:cursor.execute(query,(consumer_id,event_id))
    conn.commit()
    return {'acknowledged':len(event_ids)}


def main(request):
    endpoint=request['endpoint'];credentials=request['credentials'];consumer=request['consumer_id']
    if not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}',endpoint['schema']):raise ValueError('cdc_schema_invalid')
    if request['operation'] not in {'read','ack'}:raise ValueError('cdc_operation_invalid')
    with _connection(endpoint,credentials) as conn:
        return _read(conn,endpoint,consumer,request.get('exclude',[]),request.get('check_ids',[])) if request['operation']=='read' else _ack(conn,endpoint,consumer,request['event_ids'])


if __name__=='__main__':
    # Do not copy provider errors or credentials to stdout/stderr.
    try:
        request=json.load(sys.stdin)
        result=main(request)
        print(json.dumps({'ok':True,'result':result},ensure_ascii=True))
    except Exception as error:
        code=str(getattr(error,'pgcode','') or '')
        message=str(error).casefold()
        category=(str(error) if isinstance(error,ValueError) and str(error).startswith('cdc_')
            else 'cdc_authentication_rejected' if code.startswith('28') or 'password authentication failed' in message or 'no pg_hba.conf entry' in message
            else 'cdc_source_permission_denied' if code=='42501'
            else 'cdc_source_schema_missing' if code in {'42P01','3F000','42703'}
            else 'cdc_source_busy' if code in {'53300','55P03','40001','40P01','57P03'}
            else 'cdc_source_timeout' if code=='57014' or 'timeout expired' in message
            else 'cdc_libpq_capability_unavailable' if 'sslcertmode' in message and 'invalid connection option' in message
            else 'cdc_tls_validation_failed' if 'certificate' in message or 'ssl error' in message
            else 'cdc_source_connection_or_query_failed')
        print(json.dumps({'ok':False,'error':category},ensure_ascii=True))
        sys.exit(1)
