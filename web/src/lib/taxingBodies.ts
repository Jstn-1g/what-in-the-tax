/**
 * Read the bill as a list of taxing bodies.
 *
 * Roles are declared by the builder and never inferred here. That is not
 * caution for its own sake: the existing artifacts make inference impossible to
 * do honestly. The three legacy buckets and combinedAtAssessment.components are
 * different measurements - North Dumfries' region bucket is $2,543 at a $354,500
 * assessment while its region component is $3,264.83 at $455,000 - and their
 * sourceFactIds do not join, because a bucket cites an allocation fact and a
 * component cites a rate fact. The only remaining way to pair them would be to
 * match on the display label, and the receipt's own disclaimer says display
 * names are never used to guess a role.
 *
 * So a receipt that has not declared its bodies is refused rather than guessed
 * at. The error names the builder, because that is where the fix belongs.
 *
 * What this unlocks, visible in the packs already committed:
 *
 *   County of Brant is single-tier and today carries a placeholder bucket
 *   labelled "Upper-tier (n/a)" because the field is required. A shorter bill
 *   should be a shorter list.
 *
 *   Brant residents also pay a $78.04 hospital special levy. It is its own line
 *   in combinedAtAssessment, and with only three slots it is currently folded
 *   into the municipal portion, so the receipt understates what the county
 *   charges and hides a levy the reader is entitled to see.
 */

import type {
  InapplicableBody,
  TaxingBody,
  TaxingBodyRole,
  TaxpayerReceipt,
} from '../types'

export class TaxingBodyError extends Error {}

type Profile = TaxpayerReceipt['profiles']['supportedAverageHousehold']

export type Bill = {
  bodies: TaxingBody[]
  inapplicable: InapplicableBody[]
}

/** Bill order. A reader expects local money first and the province last. */
const ROLE_ORDER: TaxingBodyRole[] = ['local', 'special-area', 'upper-tier', 'education']

/** Roles that may appear at most once. Two local governments is a defect. */
const SINGULAR_ROLES: TaxingBodyRole[] = ['local', 'upper-tier', 'education']

/**
 * Check what a bill must be true of before anything renders it.
 *
 * Deliberately not "warn": a receipt whose parts do not add to its printed
 * total is the single worst thing this project could publish, and it is
 * cheaper to refuse than to explain afterwards.
 */
export function assertBillIsCoherent(bill: Bill, combinedTotalCad: number | null): void {
  const counts = new Map<TaxingBodyRole, number>()
  for (const body of bill.bodies) {
    counts.set(body.role, (counts.get(body.role) ?? 0) + 1)
  }
  for (const role of SINGULAR_ROLES) {
    const n = counts.get(role) ?? 0
    if (n > 1) {
      throw new TaxingBodyError(`A bill may name at most one ${role} body; this one names ${n}.`)
    }
  }
  if ((counts.get('local') ?? 0) === 0) {
    throw new TaxingBodyError('A bill must name the local municipality that issues it.')
  }
  const overlap = bill.inapplicable.filter((entry) =>
    bill.bodies.some((body) => body.role === entry.role),
  )
  if (overlap.length > 0) {
    throw new TaxingBodyError(
      `${overlap[0].role} is listed both as a taxing body and as not applicable.`,
    )
  }
  if (combinedTotalCad !== null) {
    const summed = bill.bodies.reduce((sum, body) => sum + body.amountCad, 0)
    // A cent of rounding across four bodies is expected; a dollar is not.
    if (Math.abs(summed - combinedTotalCad) > 0.05) {
      throw new TaxingBodyError(
        `Taxing bodies sum to ${summed.toFixed(2)} but the receipt prints ${combinedTotalCad.toFixed(2)}.`,
      )
    }
  }
}

/** The bill for a receipt, in reading order. Declared, never inferred. */
export function taxingBodiesFor(profile: Profile, jurisdictionSlug?: string): Bill {
  const declared = profile.taxingBodies
  if (!declared || declared.length === 0) {
    throw new TaxingBodyError(
      `${jurisdictionSlug ?? 'This receipt'} does not declare taxingBodies[]. ` +
        'Roles cannot be recovered from the legacy buckets: they measure something ' +
        'else, at a different assessment, and their fact ids do not join. The ' +
        'builder that produced this artifact has to emit the bodies and their roles.',
    )
  }

  const bill: Bill = {
    bodies: [...declared].sort(
      (a, b) =>
        a.order - b.order || ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role),
    ),
    inapplicable: profile.inapplicableBodies ?? [],
  }
  assertBillIsCoherent(bill, profile.combinedTotalCad ?? null)
  return bill
}

/**
 * The bill if this receipt declares one, and null if it does not.
 *
 * taxingBodiesFor() refuses an undeclared receipt, which is right for anything
 * that needs the roles: guessing them is the failure this module exists to
 * prevent. But a screen has to render the five packs whose builders have not
 * been migrated yet, and "no declaration" is a different condition from "a
 * declaration that does not hold". This returns null for the first and still
 * throws for the second, so a migrated pack can never quietly fall back to the
 * legacy path when its bill is wrong.
 */
export function declaredBillFor(profile: Profile, jurisdictionSlug?: string): Bill | null {
  if (!profile.taxingBodies || profile.taxingBodies.length === 0) return null
  return taxingBodiesFor(profile, jurisdictionSlug)
}

/** Each body's share of the bill, for the bar and the legend. */
export function billShares(bill: Bill): { body: TaxingBody; share: number }[] {
  const total = bill.bodies.reduce((sum, body) => sum + body.amountCad, 0)
  if (total <= 0) return bill.bodies.map((body) => ({ body, share: 0 }))
  return bill.bodies.map((body) => ({ body, share: body.amountCad / total }))
}
