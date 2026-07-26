import { describe, expect, it } from 'vitest'
import { normalizeSupportUrl, supportOptionsFor } from './SupportCard'

describe('normalizeSupportUrl', () => {
  it('accepts a trimmed HTTPS payment URL', () => {
    expect(normalizeSupportUrl('  https://buy.stripe.com/example  ')).toBe(
      'https://buy.stripe.com/example',
    )
  })

  it.each([
    undefined,
    null,
    '',
    '   ',
    'http://example.com/support',
    'https://example.com/support',
    'javascript:alert(1)',
    'https://user:password@example.com/support',
    'https://buy.stripe.com/test_example',
    'https://buy.stripe.com/example#checkout',
    'not a URL',
  ])('rejects an unsafe or missing value: %s', (value) => {
    expect(normalizeSupportUrl(value)).toBeNull()
  })
})

describe('supportOptionsFor', () => {
  it('returns no actions when payment links are not configured', () => {
    expect(supportOptionsFor()).toEqual([])
  })

  it('returns only the configured contribution action', () => {
    expect(
      supportOptionsFor('https://buy.stripe.com/once_example'),
    ).toEqual([
      {
        label: 'Contribute once',
        url: 'https://buy.stripe.com/once_example',
        className: 'button button-primary',
      },
    ])
  })

  it('returns both actions when both live links are configured', () => {
    expect(
      supportOptionsFor(
        'https://buy.stripe.com/once_example',
        'https://buy.stripe.com/monthly_example',
      ),
    ).toHaveLength(2)
  })
})
