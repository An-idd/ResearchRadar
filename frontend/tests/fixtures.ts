import type { FeedItem, Job, PaperDetail, Topic } from '../src/api'

export const topics: Topic[] = [
  { slug: 'agent', name: 'LLM Agents', description: '研究自主决策、工具调用与任务执行。', parent: null },
  { slug: 'agent-memory', name: 'Agent Memory', description: '理解智能体如何保存和调用经验。', parent: 'agent' },
]
export const paper = {
  id: '11111111-1111-4111-8111-111111111111', canonical_id: 'arxiv:2609.00001',
  arxiv_id: '2609.00001', doi: null, title: 'Learning to Remember: Adaptive Memory for Language Agents',
  abstract: 'We introduce a learned memory policy. Evaluation finds improved retrieval on our benchmark.',
  authors: ['Alex Chen', 'Sam Lee'], published_at: '2026-09-10T08:00:00Z',
  paper_url: 'https://arxiv.org/abs/2609.00001', pdf_url: 'https://arxiv.org/pdf/2609.00001', venue: null,
}
export const priorId = '22222222-2222-4222-8222-222222222222'
export const quote = 'We introduce a learned memory policy.'
const evidence = { paper_id: paper.id, chunk_id: 'abstract', quote }
export const job: Job = { id: '33333333-3333-4333-8333-333333333333', paper_id: paper.id, status: 'queued', error: null, attempts: 0, updated_at: '2026-09-11T08:00:00Z' }
export const detail: PaperDetail = {
  paper, topics: ['agent', 'agent-memory'], metrics: [],
  sources: [{ source: 'arxiv', source_id: paper.arxiv_id, raw: {}, observed_at: '2026-09-11T08:00:00Z' }],
  summary: {
    one_sentence: '通过学习记忆策略，让智能体更好地调用过往经验。',
    what_changed: '从固定规则检索转向学习驱动的记忆调用。',
    problem: '智能体需要在任务中选择相关记忆。', why_problem_matters: null,
    previous_approaches: [], previous_limitations: [], method: null, key_innovations: [],
    experiment_setup: null, key_results: [], limitations: [], why_it_matters: null, engineering_takeaways: [], confidence: .7,
    evidence: ['one_sentence', 'what_changed', 'problem'].map(field => ({ ...evidence, field })),
  },
  comparison: {
    prior_state: '前作使用固定记忆。', current_change: '本篇学习记忆策略。', major_difference: '记忆选择方式改变。',
    inherited_ideas: [], new_ideas: [], tradeoffs: [], importance: .6,
    evidence: [
      { field: 'prior_state', paper_id: priorId, chunk_id: 'abstract', quote: 'We use a fixed memory policy.' },
      { ...evidence, field: 'current_change' }, { ...evidence, field: 'major_difference' },
    ],
  },
  comparison_status: 'ready',
  generation: {
    provider: 'fake', model: 'fixture', prompt_version: 'paper_summary:v1', input_hash: 'fixture',
    scope: 'abstract-only', created_at: '2026-09-11T08:00:00Z', usage: { input_tokens: null, output_tokens: null, cost_usd: null },
    source_texts: [{ paper_id: paper.id, title: paper.title, published_at: paper.published_at, scope: 'abstract-only', chunks: [{ id: 'abstract', section: 'abstract', page: null, start: 0, end: paper.abstract.length, text: paper.abstract }] }],
    comparison_sources: [],
  },
  job: null,
}
detail.generation!.comparison_sources = [
  ...detail.generation!.source_texts,
  { paper_id: priorId, title: 'Fixed Memory for Language Agents', published_at: '2026-09-01T00:00:00Z', scope: 'full-text', chunks: [{ id: 'abstract', section: 'Method', page: 3, start: 0, end: 27, text: 'We use a fixed memory policy.' }] },
]
export const feedItem: FeedItem = {
  paper, topics: ['agent', 'agent-memory'], metrics: { hf_upvotes: 0, citation_count: null },
  score: .88, explanation: { value: .88, signals: { relevance: .9, freshness: .85, citation_count: null }, available_weights: { relevance: .6, freshness: .4 } },
  summary: { one_sentence: detail.summary!.one_sentence, what_changed: detail.summary!.what_changed, scope: 'abstract-only', generated_at: '2026-09-11T08:00:00Z' },
}
