import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

interface SkillItem {
  id: string
  name: string
  slug: string
  description: string
  version: number
  enabled: boolean
  priority: number
  trigger_patterns: string[]
  allowed_tools: string[]
  tags: string[]
  keywords: string[]
  domain: string | null
  updated_at: string
}

interface SkillDetail extends SkillItem {
  markdown_content: string | null
  prompt: string
  constraints: string
  overview: string
}

async function readErrorMessage(res: Response, fallback: string) {
  const text = await res.text()
  try {
    const data = JSON.parse(text) as { detail?: string }
    return data.detail || fallback
  } catch {
    return text || fallback
  }
}

function SkillManager() {
  const queryClient = useQueryClient()
  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null)
  const [draftMarkdown, setDraftMarkdown] = useState('')
  const [newMarkdown, setNewMarkdown] = useState(`---
name: Example Skill
slug: example-skill
description: Example skill description
version: 1
enabled: true
priority: 100
trigger_patterns:
  - "example"
allowed_tools:
  - search
agent_hints:
  planner: Focus on example-specific planning.
---

# Overview
Describe what this skill is for.

# Prompt
Add domain-specific prompt instructions here.

# Constraints
Add explicit tool or reasoning constraints here.
`)
  const [uploadFile, setUploadFile] = useState<File | null>(null)

  const { data, isLoading } = useQuery<{ items: SkillItem[] }>({
    queryKey: ['skills'],
    queryFn: async () => {
      const res = await fetch('/api/v1/skills')
      if (!res.ok) throw new Error('Failed to fetch skills')
      return res.json()
    },
  })

  const selectedSkill = useMemo(
    () => data?.items.find(item => item.id === selectedSkillId) || null,
    [data, selectedSkillId],
  )

  const { data: selectedSkillDetail } = useQuery<SkillDetail>({
    queryKey: ['skill-detail', selectedSkillId],
    queryFn: async () => {
      const res = await fetch(`/api/v1/skills/${selectedSkillId}`)
      if (!res.ok) throw new Error('Failed to fetch skill detail')
      return res.json()
    },
    enabled: !!selectedSkillId,
  })

  const createMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch('/api/v1/skills', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ markdown_content: newMarkdown }),
      })
      if (!res.ok) throw new Error(await readErrorMessage(res, 'Failed to create skill'))
      return res.json()
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['skills'] })
    },
  })

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!selectedSkillId) throw new Error('No skill selected')
      const markdown = draftMarkdown || selectedSkillDetail?.markdown_content || ''
      if (!markdown) throw new Error('Skill 内容为空')
      const res = await fetch(`/api/v1/skills/${selectedSkillId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ markdown_content: markdown }),
      })
      if (!res.ok) throw new Error(await readErrorMessage(res, 'Failed to update skill'))
      return res.json()
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['skills'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (skillId: string) => {
      const res = await fetch(`/api/v1/skills/${skillId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error(await readErrorMessage(res, 'Failed to delete skill'))
      return res.json()
    },
    onSuccess: async () => {
      setSelectedSkillId(null)
      setDraftMarkdown('')
      await queryClient.invalidateQueries({ queryKey: ['skills'] })
    },
  })

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!uploadFile) throw new Error('请选择 skill 文件')
      const formData = new FormData()
      formData.append('file', uploadFile)
      const res = await fetch('/api/v1/skills/upload', {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) throw new Error(await readErrorMessage(res, 'Failed to upload skill'))
      return res.json()
    },
    onSuccess: async () => {
      setUploadFile(null)
      await queryClient.invalidateQueries({ queryKey: ['skills'] })
    },
  })

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-6 gap-4">
        <div>
          <h2 className="text-2xl font-bold text-xmgray-900">Skill 体系管理</h2>
          <p className="text-sm text-xmgray-500">上传或编辑 Markdown skill，后端会自动热更新运行时 registry。</p>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-6">
          <div className="card p-6">
            <h3 className="font-semibold mb-4">新增 Skill</h3>
            <textarea
              className="input-xm min-h-72 font-mono text-sm"
              value={newMarkdown}
              onChange={e => setNewMarkdown(e.target.value)}
            />
            <div className="mt-4 flex gap-3">
              <button className="btn-primary" onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>
                保存 Skill
              </button>
            </div>
          </div>

          <div className="card p-6">
            <h3 className="font-semibold mb-4">上传 Skill 文件</h3>
            <input
              type="file"
              className="input-xm"
              accept=".md"
              onChange={e => setUploadFile(e.target.files?.[0] || null)}
            />
            <div className="mt-4">
              <button className="btn-primary" onClick={() => uploadMutation.mutate()} disabled={uploadMutation.isPending || !uploadFile}>
                上传 .md
              </button>
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <div className="card p-0 overflow-hidden">
            <div className="px-5 py-4 border-b border-xmgray-100 flex items-center justify-between">
              <h3 className="font-medium">已加载 Skill</h3>
              <span className="text-xs text-xmgray-400">{isLoading ? '加载中...' : `${data?.items.length || 0} 项`}</span>
            </div>
            <div className="max-h-[320px] overflow-y-auto p-4 space-y-2">
              {data?.items.map(skill => (
                <button
                    key={skill.id}
                    type="button"
                    onClick={() => {
                      setSelectedSkillId(skill.id)
                      setDraftMarkdown('')
                    }}
                  className={`w-full text-left rounded-xl border p-4 transition-colors ${
                    selectedSkillId === skill.id ? 'border-xm-400 bg-xm-50' : 'border-xmgray-100 hover:border-xmgray-200'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium text-xmgray-800">{skill.name}</div>
                      <div className="text-xs text-xmgray-400 mt-1">
                        {skill.slug} · v{skill.version} · priority {skill.priority}
                      </div>
                      <p className="mt-2 text-sm text-xmgray-500">{skill.description}</p>
                    </div>
                    <span className={`tag text-[11px] ${skill.enabled ? '' : 'opacity-60'}`}>
                      {skill.enabled ? 'enabled' : 'disabled'}
                    </span>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {skill.allowed_tools.map(tool => (
                      <span key={tool} className="tag text-[11px]">{tool}</span>
                    ))}
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="card p-6">
            <h3 className="font-semibold mb-4">编辑 Skill</h3>
            {selectedSkill ? (
              <>
                <div className="mb-3 flex flex-wrap gap-2">
                  {selectedSkill.trigger_patterns.map(pattern => (
                    <span key={pattern} className="tag text-[11px]">{pattern}</span>
                  ))}
                  {selectedSkill.tags.map(tag => (
                    <span key={tag} className="tag-orange text-[11px]">{tag}</span>
                  ))}
                </div>
                {selectedSkillDetail && (
                  <div className="mb-3 text-xs text-xmgray-400">
                    {selectedSkill.domain ? `domain: ${selectedSkill.domain}` : 'domain: global'}
                  </div>
                )}
                <textarea
                  className="input-xm min-h-72 font-mono text-sm"
                  value={draftMarkdown || selectedSkillDetail?.markdown_content || ''}
                  onChange={e => setDraftMarkdown(e.target.value)}
                />
                <div className="mt-4 flex gap-3">
                  <button className="btn-primary" onClick={() => updateMutation.mutate()} disabled={updateMutation.isPending}>
                    保存修改
                  </button>
                  <button className="btn-secondary text-red-600" onClick={() => deleteMutation.mutate(selectedSkill.id)} disabled={deleteMutation.isPending}>
                    删除
                  </button>
                </div>
              </>
            ) : (
              <p className="text-sm text-xmgray-400">请选择一个 skill 进行编辑。</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default SkillManager
