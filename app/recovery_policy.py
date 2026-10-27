"""Trusted, task-scoped repair decisions; source text cannot change limits."""
from __future__ import annotations

ROOT_RECOVERY_LIMIT = 8
PHASE_ATTEMPT_LIMIT = 10
POLICIES = {
    'connection': (3, 1, '重新建立模型连接'),
    'timeout': (2, 2, '等待后重发当前问题'),
    'server': (2, 2, '等待模型服务恢复'),
    'rate_limit': (4, 3, '降低请求频率后重试'),
    'structure': (2, 0, '补充结构纠正要求后重试'),
    'length': (2, 0, '压缩可选原文并缩短单次回答'),
    'context': (2, 0, '重新分配本次输入和输出空间'),
}
PROVIDER_KINDS = {'APIConnectionError': 'connection', 'APITimeoutError': 'timeout',
                  'InternalServerError': 'server', 'RateLimitError': 'rate_limit'}


def recovery_plan(state):
    workflow = state.get('analysis_workflow') or {}
    phase = workflow.get('active_phase')
    failures = (workflow.get('failed_attempts') or {}).get(phase) or []
    failure = failures[-1] if failures else {}
    review = state.get('review_status') or {}
    # Never treat an earlier analysis stop as the cause of a later report failure.
    reason = review.get('reason') or (workflow.get('stop_reason') if workflow.get('status') == 'paused' else None)
    if review.get('output_stage') not in (None,'analyst'): reason = None
    kind = PROVIDER_KINDS.get(failure.get('provider_error_type')) if reason == 'analysis_provider_unavailable' else {
        'analysis_output_incomplete': 'structure', 'model_output_limit': 'length',
        'insufficient_context_budget': 'context'}.get(reason)
    limit, base, action = POLICIES.get(kind, (0, 0, ''))
    total = int((state.get('session') or {}).get('automatic_recovery_attempts') or 0)
    counts = (workflow.get('recovery_counts') or {}).get(phase) or {}
    # Older checkpoints already spent their recorded retry; never reset it.
    attempts = int(counts.get(kind, 0)) if workflow.get('recovery_counts') else total
    admission = failure.get('admission') or {}
    blocked = None
    if not kind: blocked = '当前错误没有可安全执行的自动修复策略'
    elif failure.get('provider_error_code') in {'insufficient_quota','billing_hard_limit_reached','account_deactivated'}:
        blocked = '模型账号额度或账单限制需要处理，重复请求不会解除限制';limit=0
    elif failure.get('provider_error_code') == 'tls_validation_failed':
        blocked = '模型连接证书验证失败，系统不会关闭证书校验继续请求';limit=0
    elif admission.get('reason') == 'no_acquired_source_fits': blocked = '当前问题缺少可选原文，不能靠重复模型请求补出证据'
    elif total >= ROOT_RECOVERY_LIMIT: blocked = '本任务已达到自动恢复总上限'
    elif attempts >= limit: blocked = '当前问题已达到此类错误的重试上限'
    elif int((workflow.get('attempts') or {}).get(phase, 0)) >= PHASE_ATTEMPT_LIMIT:
        blocked = '当前问题已达到总尝试上限'
    elif kind == 'structure' and attempts and len(failures) >= 2 and (
            failures[-1].get('raw_response') == failures[-2].get('raw_response')):
        blocked = '结构修正后返回相同的无效响应，继续重试没有进展'
    delay = min(30, base * 2 ** attempts)
    retry_after = failure.get('retry_after_seconds')
    if kind == 'rate_limit' and isinstance(retry_after, (int, float)):
        delay = max(delay, max(0, retry_after))
        if delay > 60: blocked = '模型服务要求较长冷却，已保留检查点'
    directive = {}
    if kind == 'structure':
        directive['instruction'] = ('The previous response failed the output contract. Return one complete JSON object '
            'with a non-empty analysis_text string and an organization_data object. No fences or prose outside JSON. '
            'Correct the structure and preserve only facts supported by the supplied evidence.')
    if kind in {'length', 'context'}:
        directive.update(max_bytes=18000 // (attempts + 1), output_tokens=4096 if attempts == 0 else 2048,
            instruction='Answer only this question concisely. Keep complete JSON and literal source proofs; omit repetition.')
    return {'kind': kind, 'attempts': attempts, 'limit': limit, 'total_attempts': total,
            'total_limit': ROOT_RECOVERY_LIMIT, 'delay_seconds': delay, 'action': action,
            'directive': directive, 'blocked': blocked, 'candidate': bool(kind and not blocked)}


def report_issue_keys(audit):
    """Do not count claim IDs which can change when paragraphs are rewritten."""
    return {(row.get('status'), row.get('text') or row.get('paragraph_context'))
            for row in audit.get('claims', []) if row.get('status') != 'supported'}


def report_repair_limit(audit):
    return 3 if any(row.get('status') == 'contradicted' for row in audit.get('claims', [])) else 2
