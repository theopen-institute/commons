import { describe, expect, it } from 'vitest'
import { safeHref, withScheme } from './format'

/**
 * A procurement line's link is whatever a requester pasted, stored as typed
 * and later rendered as an `href` in an approver's session. What has to hold:
 * a bare host still gets its scheme, and nothing but http(s) ever comes out
 * the other end as something clickable.
 */
describe('withScheme', () => {
  it('adds https to a bare host, as copied from an address bar', () => {
    expect(withScheme('example.com/item')).toBe('https://example.com/item')
    expect(withScheme('  www.example.com ')).toBe('https://www.example.com')
  })

  it('leaves an http(s) link as it is', () => {
    expect(withScheme('http://example.com')).toBe('http://example.com')
    expect(withScheme('HTTPS://example.com/x')).toBe('HTTPS://example.com/x')
  })

  it('reads a host and port as a host, not a scheme', () => {
    expect(withScheme('localhost:8080/quote')).toBe('https://localhost:8080/quote')
    expect(withScheme('shop.example.com:8443')).toBe('https://shop.example.com:8443')
  })

  it('does not dress other schemes up as https links', () => {
    // Left as typed for the server to refuse — never turned into a passing URL.
    expect(withScheme('javascript:alert(1)')).toBe('javascript:alert(1)')
    expect(withScheme('mailto:a@example.com')).toBe('mailto:a@example.com')
  })

  it('leaves empty, relative and plainly-not-a-link text alone', () => {
    expect(withScheme('')).toBe('')
    expect(withScheme(null)).toBe('')
    expect(withScheme('/files/quote.pdf')).toBe('/files/quote.pdf')
    expect(withScheme('ask Ram for it')).toBe('ask Ram for it')
  })
})

describe('safeHref', () => {
  it('passes http and https links', () => {
    expect(safeHref('https://example.com/a')).toBe('https://example.com/a')
    expect(safeHref('http://example.com')).toBe('http://example.com')
  })

  it('refuses script and data schemes, however they are cased', () => {
    expect(safeHref('javascript:alert(1)')).toBeNull()
    expect(safeHref(' JavaScript:alert(1)')).toBeNull()
    expect(safeHref('data:text/html,<script>alert(1)</script>')).toBeNull()
  })

  it('refuses what does not parse as an absolute URL', () => {
    expect(safeHref('example.com')).toBeNull()
    expect(safeHref('/relative')).toBeNull()
    expect(safeHref('')).toBeNull()
    expect(safeHref(null)).toBeNull()
  })
})
