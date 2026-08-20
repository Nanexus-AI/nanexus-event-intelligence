import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import App from './App'
import { languageStorageKey } from './i18n'

test('switches languages immediately and remembers the choice', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    if (String(input).endsWith('/health')) return new Response(null, { status: 200 })
    return new Response(JSON.stringify({ items: [], total: 0, limit: 30, offset: 0 }), { status: 200 })
  })
  render(<App />)
  expect(screen.getByRole('heading', { name: '事件检查台' })).toBeInTheDocument()
  fireEvent.change(screen.getByRole('combobox', { name: '语言' }), { target: { value: 'en' } })
  expect(await screen.findByRole('heading', { name: 'Event Inspector' })).toBeInTheDocument()
  expect(localStorage.getItem(languageStorageKey)).toBe('en')
  expect(document.documentElement.lang).toBe('en')
  await waitFor(() => expect(screen.getByText('Backend online')).toBeInTheDocument())
})
