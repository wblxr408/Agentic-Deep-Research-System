"""Bounded per-subscriber event delivery and owner/execution-aware replay."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any,AsyncGenerator
from uuid import uuid4

logger=logging.getLogger(__name__)
_UNBOUND=object()


class SSEManager:
    def __init__(self):
        self._sessions:dict[str,set[asyncio.Queue]]={}
        self._locks:dict[str,asyncio.Lock]={}
        self._events_per_session:dict[str,list[dict]]={}
        self._sequence:dict[str,int]={}
        self._max_history=500
        self._epochs:dict[str,str]={}
        self._session_creation_lock=asyncio.Lock()

    async def _ensure_session(self,session_id):
        if session_id in self._sessions:return
        async with self._session_creation_lock:
            if session_id not in self._sessions:
                self._sessions[session_id]=set();self._locks[session_id]=asyncio.Lock()
                self._events_per_session[session_id]=[];self._sequence[session_id]=0
                self._epochs[session_id]=uuid4().hex

    async def publish(self,session_id:str,event_type:str,data:dict[str,Any])->None:
        from app.execution_control import current_control
        control=current_control()
        if control and control.binding['session_id']==str(session_id):
            async with control.publication_gate(terminal=event_type in {'done','workflow_error'}) as allowed:
                if allowed:await self._publish(session_id,event_type,{**data,'execution_id':control.binding['execution_id']})
        else:await self._publish(session_id,event_type,data)

    async def _publish(self,session_id,event_type,data):
        from app.disclosure import projection
        data=projection(data)
        await self._ensure_session(session_id)
        async with self._locks[session_id]:
            sequence=self._sequence[session_id]+1;self._sequence[session_id]=sequence
            event={'type':event_type,'data':data,'sequence':sequence,'id':self._epochs[session_id]+':'+str(sequence)}
            history=self._events_per_session[session_id];history.append(event)
            if len(history)>self._max_history:history[:]=history[-self._max_history:]
            for queue in self._sessions[session_id]:
                delivery=event
                if queue.full():
                    queue.get_nowait()
                    delivery={**event,'data':{**data,'delivery_gap':True,'recovery':'reload_saved_research'}}
                queue.put_nowait(delivery)

    async def stream(self,session_id:str,*,authorize=None,execution_id=_UNBOUND,last_event_id=None)->AsyncGenerator[dict[str,Any],None]:
        async def permitted():
            if authorize is None:return True
            try:return bool(await authorize())
            except Exception:
                logger.warning('SSE authorization unavailable; closing connection');return False
        def matches(event):
            return execution_id is _UNBOUND or event['data'].get('execution_id')==execution_id
        def encoded(event):
            return {'id':event['id'],'event':event['type'],'data':json.dumps(event['data'],ensure_ascii=False)}
        if not await permitted():return
        await self._ensure_session(session_id)
        cursor=None
        if isinstance(last_event_id,str):
            epoch,separator,value=last_event_id.partition(':')
            if separator and epoch==self._epochs[session_id] and value.isdecimal() and len(value)<20:cursor=int(value)
        queue=asyncio.Queue(maxsize=100)
        async with self._locks[session_id]:
            # Register and capture replay atomically: no burst duplication/gap.
            history=list(self._events_per_session[session_id])
            self._sessions[session_id].add(queue)
        try:
            yield {'event':'connected','data':json.dumps({'session_id':session_id,
                **({'execution_id':execution_id} if execution_id is not _UNBOUND else {})})}
            if cursor is not None and history and cursor<history[0]['sequence']-1:
                yield {'event':'state_update','data':json.dumps({'delivery_gap':True,'recovery':'reload_saved_research'})}
            for event in history:
                if not await permitted():return
                if matches(event) and (cursor is None or event['sequence']>cursor):yield encoded(event)
            while session_id in self._sessions and await permitted():
                try:event=await asyncio.wait_for(queue.get(),timeout=1)
                except asyncio.TimeoutError:continue
                if not await permitted():return
                if matches(event):yield encoded(event)
        except asyncio.CancelledError:
            logger.info('SSE stream cancelled for session %s',session_id);raise
        finally:
            self._sessions.get(session_id,set()).discard(queue)

    async def begin_run(self,session_id:str)->None:
        await self._ensure_session(session_id)
        async with self._locks[session_id]:
            self._events_per_session[session_id]=[]
            for queue in self._sessions[session_id]:
                while not queue.empty():queue.get_nowait()

    def get_history(self,session_id:str)->list[dict]:
        return list(self._events_per_session.get(session_id,[]))

    def close_session(self,session_id:str)->None:
        self._sessions.pop(session_id,None);self._locks.pop(session_id,None)
        self._events_per_session.pop(session_id,None);self._sequence.pop(session_id,None)
        self._epochs.pop(session_id,None)

    async def event_generator(self,session_id:str)->AsyncGenerator[dict[str,Any],None]:
        async for event in self.stream(session_id):yield event

    async def wait_for_completion(self,session_id:str,timeout:float=300.)->list[dict]:
        events=[]
        try:
            async with asyncio.timeout(timeout):
                async for event in self.stream(session_id):
                    events.append(event)
                    if event.get('event') in {'done','workflow_error'}:break
        except TimeoutError:logger.warning('Timeout waiting for session %s',session_id)
        return events


_sse_manager:SSEManager|None=None


def get_sse_manager()->SSEManager:
    global _sse_manager
    if _sse_manager is None:_sse_manager=SSEManager()
    return _sse_manager
