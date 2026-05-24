import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

interface DocumentSource {
  id: string
  name: string
  group_name: string
  source_type: string
  file_name: string | null
  file_ext: string | null
  status: string
  original_text: string | null
  chunk_size: number
  chunk_overlap: number
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

interface DocumentChunk {
  id: string
  source_id: string | null
  source_name: string | null
  source_type: string
  chunk_index: number
  chunk_count: number
  content: string
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

type Mode = 'list' | 'create'

const supportedFormats = ['json', 'md', 'docx', 'pdf', 'txt']

async function readErrorMessage(res: Response, fallback: string) {
  const text = await res.text()
  try {
    const data = JSON.parse(text) as { detail?: string }
    return data.detail || fallback
  } catch {
    return text || fallback
  }
}

function DocumentManager() {
  const queryClient = useQueryClient()
  const [mode, setMode] = useState<Mode>('create')
  const [groupMode, setGroupMode] = useState<'all' | 'manage'>('manage')
  const [groupFilter, setGroupFilter] = useState('')
  const [name, setName] = useState('')
  const [groupName, setGroupName] = useState('')
  const [content, setContent] = useState('')
  const [chunkSize, setChunkSize] = useState(400)
  const [chunkOverlap, setChunkOverlap] = useState(80)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [editGroupName, setEditGroupName] = useState('')
  const [editStatus, setEditStatus] = useState('active')
  const [editMetadataText, setEditMetadataText] = useState('{}')

  const { data: sources, isLoading } = useQuery<{ items: DocumentSource[] }>({
    queryKey: ['document-sources', groupFilter],
    queryFn: async () => {
      const url = groupFilter ? `/api/v1/documents/sources?group_name=${encodeURIComponent(groupFilter)}` : '/api/v1/documents/sources'
      const res = await fetch(url)
      if (!res.ok) throw new Error('Failed to fetch sources')
      return res.json()
    },
  })

  const { data: chunks } = useQuery<{ items: DocumentChunk[] }>({
    queryKey: ['document-chunks', selectedSourceId, groupFilter],
    queryFn: async () => {
      const url = selectedSourceId
        ? `/api/v1/documents/chunks?source_id=${encodeURIComponent(selectedSourceId)}`
        : groupFilter
          ? `/api/v1/documents/chunks?group_name=${encodeURIComponent(groupFilter)}`
          : '/api/v1/documents/chunks'
      const res = await fetch(url)
      if (!res.ok) throw new Error('Failed to fetch chunks')
      return res.json()
    },
  })

  useEffect(() => {
    if (!selectedSourceId && sources?.items?.length) {
      const first = sources.items[0]
      setSelectedSourceId(first.id)
      setEditName(first.name)
      setEditGroupName(first.group_name)
      setEditStatus(first.status)
      setEditMetadataText(JSON.stringify(first.metadata || {}, null, 2))
    }
  }, [sources, selectedSourceId])

  const selectedSource = useMemo(
    () => sources?.items.find(item => item.id === selectedSourceId) || null,
    [sources, selectedSourceId],
  )

  useEffect(() => {
    if (selectedSource) {
      setEditName(selectedSource.name)
      setEditGroupName(selectedSource.group_name)
      setEditStatus(selectedSource.status)
      setEditMetadataText(JSON.stringify(selectedSource.metadata || {}, null, 2))
    }
  }, [selectedSource])

  const createMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        name,
        group_name: groupName,
        content,
        metadata: {},
        chunk_size: chunkSize,
        chunk_overlap: chunkOverlap,
      }
      const res = await fetch('/api/v1/documents/sources', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error(await readErrorMessage(res, 'Failed to create source'))
      return res.json()
    },
    onSuccess: async () => {
      setName('')
      setGroupName('')
      setContent('')
      setSelectedFile(null)
      await queryClient.invalidateQueries({ queryKey: ['document-sources'] })
      await queryClient.invalidateQueries({ queryKey: ['document-chunks'] })
      setMode('list')
    },
  })

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!selectedFile) throw new Error('请选择文件')
      const form = new FormData()
      form.append('file', selectedFile)
      form.append('name', name || selectedFile.name)
      form.append('group_name', groupName)
      form.append('chunk_size', String(chunkSize))
      form.append('chunk_overlap', String(chunkOverlap))
      const res = await fetch('/api/v1/documents/upload', {
        method: 'POST',
        body: form,
      })
      if (!res.ok) throw new Error(await readErrorMessage(res, 'Failed to upload source'))
      return res.json()
    },
    onSuccess: async () => {
      setName('')
      setGroupName('')
      setContent('')
      setSelectedFile(null)
      await queryClient.invalidateQueries({ queryKey: ['document-sources'] })
      await queryClient.invalidateQueries({ queryKey: ['document-chunks'] })
      setMode('list')
    },
  })

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!selectedSource) throw new Error('未选择知识源')
      const metadata = JSON.parse(editMetadataText || '{}')
      const res = await fetch(`/api/v1/documents/sources/${selectedSource.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: editName,
          group_name: editGroupName,
          status: editStatus,
          metadata,
        }),
      })
      if (!res.ok) throw new Error(await readErrorMessage(res, 'Failed to update source'))
      return res.json()
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['document-sources'] })
      await queryClient.invalidateQueries({ queryKey: ['document-chunks'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (sourceId: string) => {
      const res = await fetch(`/api/v1/documents/sources/${sourceId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error(await readErrorMessage(res, 'Failed to delete source'))
      return res.json()
    },
    onSuccess: async () => {
      setSelectedSourceId(null)
      await queryClient.invalidateQueries({ queryKey: ['document-sources'] })
      await queryClient.invalidateQueries({ queryKey: ['document-chunks'] })
    },
  })

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-xmgray-900">内部 RAG 文档源</h2>
          <p className="text-sm text-xmgray-500">支持 {supportedFormats.join(' / ')}，前端手动维护分组、上传、编辑与删除。</p>
        </div>
        <div className="flex gap-2">
          <button className={`btn-secondary ${mode === 'list' ? 'bg-xm-50' : ''}`} onClick={() => setMode('list')}>列表</button>
          <button className={`btn-primary`} onClick={() => setMode('create')}>上传 / 新增</button>
        </div>
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <input
          value={groupFilter}
          onChange={e => setGroupFilter(e.target.value)}
          placeholder="按分组筛选"
          className="input-xm max-w-xs"
        />
        <button className="btn-secondary text-sm" onClick={() => setGroupFilter('')}>清除筛选</button>
        <button className="btn-secondary text-sm" onClick={() => setGroupMode('all')}>全部组</button>
        <button className="btn-secondary text-sm" onClick={() => setGroupMode('manage')}>管理组</button>
      </div>

      {groupMode === 'manage' && (
        <div className="card p-5 mb-6">
          <h3 className="font-semibold mb-3">知识库组管理</h3>
          <div className="flex flex-wrap items-center gap-3">
            <input
              className="input-xm max-w-xs"
              value={groupName}
              onChange={e => setGroupName(e.target.value)}
              placeholder="新建 / 修改组名"
            />
            <button className="btn-primary" onClick={() => setMode('create')}>进入新增</button>
          </div>
        </div>
      )}

      {mode === 'create' && (
        <div className="grid gap-4 lg:grid-cols-2 mb-8">
          <div className="card p-6">
            <h3 className="font-semibold mb-4">新增文本源</h3>
            <div className="space-y-3">
              <input className="input-xm w-full" value={name} onChange={e => setName(e.target.value)} placeholder="名称" />
              <input className="input-xm w-full" value={groupName} onChange={e => setGroupName(e.target.value)} placeholder="分组" />
              <textarea className="input-xm w-full min-h-48" value={content} onChange={e => setContent(e.target.value)} placeholder="粘贴 JSON / MD / TXT 内容，或切换到文件上传" />
              <div className="grid grid-cols-2 gap-3">
                <input type="number" className="input-xm w-full" value={chunkSize} onChange={e => setChunkSize(Number(e.target.value))} />
                <input type="number" className="input-xm w-full" value={chunkOverlap} onChange={e => setChunkOverlap(Number(e.target.value))} />
              </div>
              <button className="btn-primary" onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>保存文本源</button>
            </div>
          </div>

          <div className="card p-6">
            <h3 className="font-semibold mb-4">上传文件</h3>
            <div className="space-y-3">
              <input className="input-xm w-full" value={name} onChange={e => setName(e.target.value)} placeholder="名称" />
              <input className="input-xm w-full" value={groupName} onChange={e => setGroupName(e.target.value)} placeholder="分组" />
              <input type="file" className="input-xm w-full" onChange={e => setSelectedFile(e.target.files?.[0] || null)} accept=".json,.md,.docx,.pdf,.txt" />
              <div className="grid grid-cols-2 gap-3">
                <input type="number" className="input-xm w-full" value={chunkSize} onChange={e => setChunkSize(Number(e.target.value))} />
                <input type="number" className="input-xm w-full" value={chunkOverlap} onChange={e => setChunkOverlap(Number(e.target.value))} />
              </div>
              <button className="btn-primary" onClick={() => uploadMutation.mutate()} disabled={uploadMutation.isPending || !selectedFile}>上传并入库</button>
            </div>
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
          <div className="card p-0 overflow-hidden">
            <div className="px-5 py-4 border-b border-xmgray-100 flex items-center justify-between">
              <h3 className="font-medium">知识源列表</h3>
              <span className="text-xs text-xmgray-400">{isLoading ? '加载中...' : `${sources?.items.length || 0} 项`}</span>
            </div>
            <div className="max-h-[620px] overflow-y-auto p-4 space-y-2">
            {sources?.items?.map(source => (
              <button
                key={source.id}
                onClick={() => setSelectedSourceId(source.id)}
                className={`w-full text-left p-4 rounded-xl border transition-colors ${selectedSourceId === source.id ? 'border-xm-400 bg-xm-50' : 'border-xmgray-100 hover:border-xmgray-200'}`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="font-medium text-xmgray-800">{source.name}</div>
                    <div className="text-xs text-xmgray-400">{source.group_name} · {source.source_type} · {source.file_ext || 'manual'}</div>
                  </div>
                  <span className="text-[11px] text-xmgray-400">{source.status}</span>
                </div>
                <div className="mt-2 flex gap-2">
                  <button className="text-xs text-xm-600" onClick={(e) => { e.stopPropagation(); setMode('create'); setSelectedSourceId(source.id) }}>修改</button>
                  <button className="text-xs text-red-500" onClick={(e) => { e.stopPropagation(); deleteMutation.mutate(source.id) }}>删除</button>
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-4">
          <div className="card p-6">
            <h3 className="font-semibold mb-4">编辑知识源</h3>
            {selectedSource ? (
              <div className="space-y-3">
                <input className="input-xm w-full" value={editName} onChange={e => setEditName(e.target.value)} />
                <input className="input-xm w-full" value={editGroupName} onChange={e => setEditGroupName(e.target.value)} />
                <select className="input-xm w-full" value={editStatus} onChange={e => setEditStatus(e.target.value)}>
                  <option value="active">active</option>
                  <option value="archived">archived</option>
                </select>
                <textarea className="input-xm w-full min-h-32 font-mono text-xs" value={editMetadataText} onChange={e => setEditMetadataText(e.target.value)} />
                <button className="btn-primary" onClick={() => updateMutation.mutate()} disabled={updateMutation.isPending}>保存修改</button>
              </div>
            ) : (
              <p className="text-sm text-xmgray-400">请选择一个知识源。</p>
            )}
          </div>

          <div className="card p-6">
            <h3 className="font-semibold mb-4">Chunks</h3>
            <div className="max-h-[320px] overflow-y-auto space-y-3">
              {chunks?.items?.map(chunk => (
                <div key={chunk.id} className="rounded-xl border border-xmgray-100 p-3">
                  <div className="flex items-center justify-between text-xs text-xmgray-400">
                    <span>{chunk.source_name || 'unknown'}</span>
                    <span>{chunk.chunk_index + 1}/{chunk.chunk_count}</span>
                  </div>
                  <p className="mt-2 text-sm text-xmgray-700 whitespace-pre-wrap line-clamp-6">{chunk.content}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default DocumentManager
