import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { EvidenceList } from '../src/EvidenceList'
import { detail, priorId } from './fixtures'

describe('evidence provenance', () => {
  it('matches both paper and chunk identity and shows the correct prior page', () => {
    render(<MemoryRouter><EvidenceList evidence={detail.comparison!.evidence} sources={detail.generation!.comparison_sources} /></MemoryRouter>)
    fireEvent.click(screen.getByText('查看原文证据'))
    expect(screen.getByRole('link', { name: 'Fixed Memory for Language Agents' })).toHaveAttribute('href', `/papers/${priorId}`)
    expect(screen.getByText('Method · 第 3 页')).toBeVisible()
    expect(screen.getAllByText('摘要')).toHaveLength(2)
  })
  it('renders research content as plain text and does not invent missing source metadata', () => {
    const { container } = render(<MemoryRouter><EvidenceList evidence={[{ field: 'method', paper_id: priorId, chunk_id: 'missing', quote: '<img src=x onerror=alert(1)>' }]} sources={[]} /></MemoryRouter>)
    fireEvent.click(screen.getByText('查看原文证据'))
    expect(container.querySelector('img')).toBeNull()
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeVisible()
    expect(screen.queryByText(/第.*页/)).toBeNull()
  })
})
