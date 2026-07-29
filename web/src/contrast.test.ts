/**
 * WCAG contrast over the declared colour tokens, in both colour schemes.
 *
 * axe cannot do this: it needs layout and computed colours, and the suite runs
 * in jsdom, which has neither. So the pairs are declared here instead - which is
 * the honest trade. A machine cannot tell which foreground lands on which
 * background across 2,700 lines of CSS, but a human can say, and then the ratios
 * are arithmetic and never need to be eyeballed again.
 *
 * Every pair below is one that occurs in the rendered UI. Adding a colour to
 * styles.css does not add it here; that is deliberate, because a check that
 * invents its own pairs would pass on combinations nobody ever sees.
 *
 * Thresholds are WCAG 2.1 AA: 4.5:1 for body text, 3:1 for large text
 * (>=18.66px bold or >=24px) and for the non-text things 1.4.11 actually covers
 * - UI component boundaries and graphics you need in order to read the content.
 * Decorative rules and dividers are not in that set and are not listed. Calling
 * a hairline between table rows a failure would bury the real ones.
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// Read the file, not a bundled copy of it. Vite's ?raw went through the CSS
// pipeline and arrived without the media block, which would have made this
// check quietly examine something other than what ships.
const CSS = readFileSync(fileURLToPath(new URL('./styles.css', import.meta.url)), 'utf8')

type Scheme = 'light' | 'dark'

function tokensFor(scheme: Scheme): Map<string, string> {
  const rootBody = CSS.slice(CSS.indexOf(':root'), CSS.indexOf('}'))
  const tokens = new Map<string, string>()
  for (const [, name, value] of rootBody.matchAll(/--([a-z-]+):\s*(#[0-9a-fA-F]{3,6})\s*;/g)) {
    tokens.set(name, value)
  }
  if (scheme === 'dark') {
    const start = CSS.indexOf(":root[data-theme='dark']")
    if (start === -1) throw new Error("no :root[data-theme='dark'] block in styles.css")
    const block = CSS.slice(start, CSS.indexOf('\n}', start))
    for (const [, name, value] of block.matchAll(/--([a-z-]+):\s*(#[0-9a-fA-F]{3,6})\s*;/g)) {
      tokens.set(name, value)
    }
  }
  return tokens
}

function channel(value: number): number {
  const c = value / 255
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

export function luminance(hex: string): number {
  const raw = hex.replace('#', '')
  const full = raw.length === 3 ? [...raw].map((c) => c + c).join('') : raw
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16))
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

export function contrastRatio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

type Kind = 'text' | 'large-text' | 'non-text'
const MINIMUM: Record<Kind, number> = { text: 4.5, 'large-text': 3, 'non-text': 3 }

type Pair = { fg: string; bg: string; kind: Kind; where: string }

const PAIRS: Pair[] = [
  // Body copy and headings.
  { fg: 'ink', bg: 'page', kind: 'text', where: 'body copy on the page' },
  { fg: 'ink', bg: 'surface', kind: 'text', where: 'copy on panels' },
  { fg: 'ink', bg: 'mint', kind: 'text', where: 'copy on the evidence tint' },
  { fg: 'ink', bg: 'note', kind: 'text', where: 'copy on the paper note' },
  { fg: 'ink', bg: 'teal-soft', kind: 'text', where: 'copy on the education tint' },
  { fg: 'ink-soft', bg: 'page', kind: 'text', where: 'secondary copy' },
  { fg: 'ink-soft', bg: 'surface', kind: 'text', where: 'secondary copy on panels' },
  { fg: 'ink-soft', bg: 'mint', kind: 'text', where: 'secondary copy on the tint' },
  { fg: 'ink-soft', bg: 'note', kind: 'text', where: 'secondary copy on the note' },
  { fg: 'ink-soft', bg: 'amber-soft', kind: 'text', where: 'secondary copy on a caution' },
  { fg: 'ink-faint', bg: 'page', kind: 'text', where: 'captions and slc codes' },
  { fg: 'ink-faint', bg: 'surface', kind: 'text', where: 'captions on panels' },
  { fg: 'placeholder', bg: 'page', kind: 'text', where: 'the place-finder placeholder' },

  // Links, emphasis and status colours carrying meaning as text.
  { fg: 'green', bg: 'page', kind: 'text', where: 'links and municipal emphasis' },
  { fg: 'green', bg: 'surface', kind: 'text', where: 'links on panels' },
  { fg: 'green', bg: 'mint', kind: 'text', where: 'links on the tint' },
  { fg: 'green', bg: 'note', kind: 'text', where: 'links on the note' },
  { fg: 'green-dark', bg: 'page', kind: 'text', where: 'headings' },
  { fg: 'green-dark', bg: 'mint', kind: 'text', where: 'headings on the tint' },
  { fg: 'amber', bg: 'page', kind: 'text', where: 'caution text' },
  { fg: 'amber', bg: 'amber-soft', kind: 'text', where: 'caution text on its own tint' },
  { fg: 'amber', bg: 'note', kind: 'text', where: 'caution text on the note' },
  { fg: 'flag-ink', bg: 'amber-soft', kind: 'text', where: 'the flagged badge' },
  { fg: 'red', bg: 'page', kind: 'text', where: 'failure text' },
  { fg: 'red', bg: 'red-soft', kind: 'text', where: 'failure text on its own tint' },
  { fg: 'accent', bg: 'page', kind: 'text', where: 'the accent rule and marks' },
  { fg: 'ink', bg: 'evidence-surface', kind: 'text', where: 'the evidence summary' },
  { fg: 'ink-soft', bg: 'evidence-surface', kind: 'text', where: 'evidence summary detail' },

  // Reversed out of a filled surface.
  { fg: 'on-fill', bg: 'green', kind: 'text', where: 'primary buttons' },
  { fg: 'on-fill', bg: 'green-dark', kind: 'text', where: 'the site header' },
  { fg: 'on-fill', bg: 'accent', kind: 'text', where: 'the accent badge' },
  { fg: 'on-fill', bg: 'ink', kind: 'text', where: 'inverted panels' },
  { fg: 'on-fill', bg: 'amber', kind: 'text', where: 'a filled caution' },

  // 1.4.11: things you must be able to see to operate or to read a figure.
  { fg: 'focus', bg: 'page', kind: 'non-text', where: 'the focus ring' },
  { fg: 'focus', bg: 'surface', kind: 'non-text', where: 'the focus ring on panels' },
  { fg: 'green', bg: 'page', kind: 'non-text', where: 'the municipal bar segment' },
  { fg: 'teal', bg: 'page', kind: 'non-text', where: 'the upper-tier bar segment' },
  { fg: 'tone-special', bg: 'page', kind: 'non-text', where: 'the special-area bar segment' },
  // Missed on the first pass and caught by looking at the render: the education
  // segment was reusing the tint token and came out at 1.24:1. A declared pair
  // list only covers what someone thought to declare, which is the trade this
  // check makes; the answer is to keep looking at the page, not to stop declaring.
  { fg: 'tone-education', bg: 'page', kind: 'non-text', where: 'the education bar segment' },
  // The flagged badge's outline is not listed. 1.4.11 covers what is needed to
  // identify a component or its state, and this badge says its state in words
  // - "Evidence missing" - in text that clears 4.5:1. The border is decoration
  // around an already-legible label, and darkening it to 3:1 would mean
  // redesigning the badge to satisfy a rule it is not under.
]

describe.each<Scheme>(['light', 'dark'])('%s scheme', (scheme) => {
  const tokens = tokensFor(scheme)

  it('defines every token the pairs name', () => {
    const missing = [...new Set(PAIRS.flatMap((p) => [p.fg, p.bg]))]
      .filter((name) => !tokens.has(name))
      .sort()
    expect(missing).toEqual([])
  })

  it('meets WCAG 2.1 AA on every declared pair', () => {
    const failures = PAIRS.flatMap((pair) => {
      const ratio = contrastRatio(tokens.get(pair.fg)!, tokens.get(pair.bg)!)
      const floor = MINIMUM[pair.kind]
      return ratio >= floor
        ? []
        : [
            `${pair.fg} on ${pair.bg} (${pair.where}) is ${ratio.toFixed(2)}:1, ` +
              `below the ${floor}:1 needed for ${pair.kind}`,
          ]
    })
    expect(failures).toEqual([])
  })
})

describe('the checker itself', () => {
  it('computes the ratios WCAG defines', () => {
    // Black on white is the definitional maximum; a colour against itself is 1.
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 5)
    expect(contrastRatio('#075b43', '#075b43')).toBeCloseTo(1, 5)
    // A published reference value, so the transfer curve is not just internally
    // consistent: #767676 on white is the canonical 4.54:1 AA boundary grey.
    expect(contrastRatio('#767676', '#ffffff')).toBeCloseTo(4.54, 2)
  })

  it('rejects a pair that fails', () => {
    expect(contrastRatio('#999999', '#ffffff')).toBeLessThan(4.5)
  })
})
