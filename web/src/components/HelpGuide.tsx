/**
 * Resident + municipal-staff help guide.
 * Illustrations intentionally deferred — placeholders mark where screenshots will go.
 */

const SECTIONS = [
  { id: 'what-this-is', title: 'What this is' },
  { id: 'how-to-read', title: 'How to read it in 60 seconds' },
  { id: 'labels', title: 'Labels: FACT, DERIVED, GAP…' },
  { id: 'how-total', title: 'How the total is built' },
  { id: 'tiers', title: 'One-tier vs two-tier bills' },
  { id: 'pro-rata', title: 'Department line items (pro-rata)' },
  { id: 'at-a-glance', title: 'At a glance & evidence state' },
  { id: 'findings-gaps', title: 'Watch, findings, and gaps' },
  { id: 'citations', title: 'Citations and “Cite OK”' },
  { id: 'special-levies', title: 'Special levies' },
  { id: 'for-staff', title: 'For clerks and councillors' },
  { id: 'not-this', title: 'What this is not' },
  { id: 'faq', title: 'FAQ' },
] as const

function IllustrationSlot({ caption }: { caption: string }) {
  return (
    <figure className="help-illustration-slot">
      <div className="help-illustration-frame" aria-hidden="true">
        <span>Illustration coming</span>
      </div>
      <figcaption>{caption}</figcaption>
    </figure>
  )
}

export default function HelpGuide({
  onBack,
  simpleLanguage = false,
}: {
  onBack: () => void
  simpleLanguage?: boolean
}) {
  return (
    <div className="help-page">
      <header className="help-hero">
        <p className="help-kicker">Help &amp; glossary</p>
        <h1>How to read a Taxpayer Receipt</h1>
        {simpleLanguage ? (
          <p className="help-eli5-note" role="status">
            <strong>Simple language</strong> is on for the receipt page — labels and short
            explanations there use plainer words. This glossary still uses the full terms
            (FACT, DERIVED, GAP) so you can match them to the badges.
          </p>
        ) : null}
        <p className="help-lede">
          This page answers the questions residents, clerks, and councillors usually ask —
          what the labels mean, where the dollars come from, and what we refuse to invent.
          Screenshots will be added once the UI is finalized.
        </p>
        <div className="help-hero-actions">
          <button type="button" className="cta" onClick={onBack}>
            ← Back to receipt
          </button>
          <a className="cta cta-ghost help-toc-jump" href="#help-toc">
            Jump to contents
          </a>
        </div>
      </header>

      <div className="help-layout">
        <nav className="help-toc" id="help-toc" aria-label="Help contents">
          <p className="help-toc-title">On this page</p>
          <ol>
            {SECTIONS.map((section, index) => (
              <li key={section.id}>
                <a href={`#${section.id}`}>
                  <span className="help-toc-num">{String(index + 1).padStart(2, '0')}</span>
                  {section.title}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <article className="help-article">
          <section id="what-this-is" className="help-section">
            <h2>What this is</h2>
            <p>
              A <strong>Taxpayer Receipt</strong> shows, for one published assessment value, how a
              residential property-tax bill is built: which body levies which rate, how large each
              slice is in dollars, and — where the municipality publishes enough detail — how the
              <em>local</em> portion could be attributed across departments.
            </p>
            <p>
              Every number is supposed to resolve to a <strong>published municipal or provincial
              document</strong> (budget, by-law, tax-rate schedule) or to an explicit formula over
              those numbers. If we cannot prove a figure, we mark a <strong>gap</strong> instead of
              guessing.
            </p>
            <p>
              The tool is <strong>not affiliated</strong> with any municipality. It is an independent
              reading aid. It is <strong>not tax advice</strong> and not your official tax bill —
              compare against the notice you receive from your municipality.
            </p>
            <IllustrationSlot caption="Hero of the receipt — total bill and at-a-glance summary." />
          </section>

          <section id="how-to-read" className="help-section">
            <h2>How to read it in 60 seconds</h2>
            <ol className="help-steps">
              <li>
                <strong>Confirm the place and assessment.</strong> The headline states the
                municipality (or County) and the assessment used (e.g. median or rural average).
              </li>
              <li>
                <strong>Read the total.</strong> That is rate × assessment for every component on
                the combined bill (municipal, any special levy, education, and upper-tier Region
                where applicable).
              </li>
              <li>
                <strong>Scan “Of this bill.”</strong> The share bar answers who controls how much of
                the total — often surprising for two-tier areas where the Region is the largest
                slice.
              </li>
              <li>
                <strong>Scan “Where the local dollar goes.”</strong> Top department lines are a
                model over the local levy (see pro-rata below), not a second official bill.
              </li>
              <li>
                <strong>Check Evidence state.</strong> Watch / Gaps / Cite tell you how complete
                our proof is — not whether the budget is “good” or “bad.”
              </li>
              <li>
                <strong>Click a source link.</strong> The intended action is: take one figure, open
                the municipality’s document at the cited page, and confirm or refute it.
              </li>
            </ol>
          </section>

          <section id="labels" className="help-section">
            <h2>Labels: FACT, DERIVED, GAP, JUDGMENT, ROUNDING</h2>
            <p>
              These labels are the product. They tell you what kind of claim you are looking at.
              They are <em>not</em> grades of the municipality’s spending.
            </p>

            <dl className="help-glossary">
              <div>
                <dt>FACT</dt>
                <dd>
                  A number or rate taken from a published source, with a citation (document + page
                  when the source is a PDF). Example: “2026 RT Residential municipal tax rate
                  0.0107859” from the County tax-rate schedule. If you disagree with a FACT, the
                  disagreement is with our transcription or the source page — not with an opinion.
                </dd>
              </div>
              <div>
                <dt>DERIVED</dt>
                <dd>
                  A number we <strong>calculated</strong> from FACTS (or other DERIVED values) using
                  an explicit formula. Example: municipal tax = assessment × municipal rate; or a
                  department’s household share = (department net levy ÷ total net levy) × municipal
                  portion of the bill. DERIVED is still accountable: you can recompute it. It is
                  <em>not</em> a figure the municipality printed on your household notice unless the
                  source says so.
                </dd>
              </div>
              <div>
                <dt>GAP</dt>
                <dd>
                  Something we looked for and could not support with published evidence. We list
                  what is missing and what would close it. We do <strong>not</strong> invent dollars
                  to fill the hole. A GAP is an honest unfinished edge, not a finding of wrongdoing.
                </dd>
              </div>
              <div>
                <dt>JUDGMENT</dt>
                <dd>
                  An interpretive finding (for example, that two capital projects may overlap in
                  narrative). Judgments cite facts and may point at gaps, but{' '}
                  <strong>bill impact in dollars stays null</strong> until a formula is approved.
                  That rule exists so a narrative concern cannot silently become a fake line on your
                  receipt.
                </dd>
              </div>
              <div>
                <dt>ROUNDING</dt>
                <dd>
                  A reconciling cent (or two) so modeled lines sum to a published control total.
                  Shown explicitly so we never hide a math plug inside a service line.
                </dd>
              </div>
            </dl>
            <IllustrationSlot caption="Receipt line with DERIVED badge and source link." />
          </section>

          <section id="how-total" className="help-section">
            <h2>How the total is built</h2>
            <p>
              For a stated assessment (CVA), each taxing body applies a <strong>rate</strong> from
              the adopted tax-rate schedule:
            </p>
            <p className="help-formula">
              component dollars = assessment × rate
            </p>
            <p>
              Components are added to form the combined residential total. Education rates are set
              provincially; the local municipality usually <em>collects</em> education tax but does
              not set that rate.
            </p>
            <p>
              Important: some budget books illustrate “tax impact” that <strong>excludes
              education</strong> (County of Brant’s median illustration is an example). This receipt
              shows the full residential total including education when the tax-rate schedule
              includes it, and calls out the difference.
            </p>
          </section>

          <section id="tiers" className="help-section">
            <h2>One-tier vs two-tier bills</h2>
            <p>
              Ontario municipalities are not all structured the same way. This tool supports both:
            </p>
            <ul>
              <li>
                <strong>Two-tier (example: North Dumfries).</strong> You pay a lower-tier Township
                portion, an upper-tier Region portion (Region of Waterloo), and education. The
                Region often dominates the bill.
              </li>
              <li>
                <strong>Single-tier (example: County of Brant / Paris).</strong> There is no separate
                Region column. Services such as OPP policing appear inside the County levy. Paris
                is billed as County of Brant — there is no separate “Town of Paris” tax pack here.
              </li>
            </ul>
            <p>
              If the Region bucket shows as a gap on a single-tier pack, that is intentional: we
              refuse to invent an upper-tier column that does not exist.
            </p>
          </section>

          <section id="pro-rata" className="help-section">
            <h2>Department line items (pro-rata)</h2>
            <p>
              Municipalities publish department <strong>net levy requirements</strong> (or similar)
              for the corporation as a whole. They almost never publish “your household’s share of
              Corporate Services.”
            </p>
            <p>
              When we show department lines on the receipt, we use a transparent model:
            </p>
            <p className="help-formula">
              household line = municipal bill portion × (department net requirement ÷ allocation base)
            </p>
            <p>
              The allocation base is declared in the pack (for Brant, it equals the approved net
              levy). Those lines are labeled <strong>DERIVED</strong>. They help you see relative
              scale; they are not an official household schedule. The footnote in “At a glance”
              repeats this on purpose.
            </p>
            <p>
              <strong>Disclosure sublines</strong> (for example “of which Legal Services” or “of
              which OPP”) are already included in a parent line. They are shown for curiosity and
              are <strong>not added again</strong> to any total.
            </p>
          </section>

          <section id="at-a-glance" className="help-section">
            <h2>At a glance &amp; evidence state</h2>
            <p>The hero summary has three jobs:</p>
            <ul>
              <li>
                <strong>Of this bill</strong> — who levies what share of the combined total (from
                published rates).
              </li>
              <li>
                <strong>Where the local dollar goes</strong> — the three largest positive department
                lines in the local portion (pro-rata model).
              </li>
              <li>
                <strong>Evidence state</strong> — how complete our proof is right now:
                <ul>
                  <li>
                    <strong>Watch</strong> — published findings that need an explanation (not a
                    verdict of waste).
                  </li>
                  <li>
                    <strong>Gaps</strong> — missing evidence we refused to invent.
                  </li>
                  <li>
                    <strong>Cite OK / Cite fails</strong> — result of the automated citation audit
                    (do cited pages support the claims?).
                  </li>
                </ul>
              </li>
            </ul>
            <p>
              Evidence state is deliberately <strong>not</strong> a letter grade of the budget. A
              pack can be Cite OK with several Gaps; that means our math is sourced and our
              unfinished work is listed.
            </p>
            <IllustrationSlot caption="At a glance strip: share bar, top destinations, evidence chips." />
          </section>

          <section id="findings-gaps" className="help-section">
            <h2>Watch, findings, and gaps</h2>
            <p>
              <strong>Findings</strong> are rare and hand-written. They highlight something that
              deserves a public explanation (capital overlap, legal-expense stacking, peer fairness
              checks, and so on). They cite facts; they do not invent a dollar impact on your bill.
            </p>
            <p>
              <strong>“Flagged” means this line needs an explanation. It does not mean the money
              was wasted.</strong>
            </p>
            <p>
              <strong>Gaps</strong> are unfinished evidence — for example “peer FIR fairness check
              not yet run for Brant.” Closing a gap usually means acquiring a document or completing
              a hand analysis, then promoting the result to FACT/DERIVED or a finding.
            </p>
          </section>

          <section id="citations" className="help-section">
            <h2>Citations and “Cite OK”</h2>
            <p>
              Where possible, each FACT points at a public PDF with a page number. A separate
              citation audit checks whether the cited page actually contains the claimed excerpt or
              numbers.
            </p>
            <ul>
              <li>
                <strong>Cite OK</strong> — no hard failures (wrong page / not found / bad page
                number) in the current audit.
              </li>
              <li>
                <strong>Cite fails</strong> — treat affected figures with caution until fixed.
              </li>
            </ul>
            <p>
              Weaker match tiers (for example “numbers only”) can still appear in internal audits;
              they mean the digits are on the page but the wording is not a perfect quote. The UI
              may withhold deep page links when a match is too weak.
            </p>
          </section>

          <section id="special-levies" className="help-section">
            <h2>Special levies</h2>
            <ul>
              <li>
                <strong>Ayr Special Area Rate (North Dumfries).</strong> Urban Ayr properties may
                pay an additional area rate on top of the rural combined total. The receipt shows
                the rural total by default and documents the Ayr variant separately.
              </li>
              <li>
                <strong>Hospital special levy (County of Brant).</strong> A dedicated rate column on
                the County tax schedule, shown as its own bill component — not buried inside a
                department line.
              </li>
            </ul>
          </section>

          <section id="for-staff" className="help-section">
            <h2>For clerks and councillors</h2>
            <p>If you work for a covered municipality:</p>
            <ul>
              <li>
                Corrections are welcome. The success condition for this project is a resident asking
                a specific sourced question — or a clerk publicly correcting one of our numbers.
              </li>
              <li>
                Right-of-reply applies to findings. Dollar impacts on findings stay null until a
                formula is approved.
              </li>
              <li>
                Pack status (draft / sealed preview / published) describes our release process, not
                your budget’s legality.
              </li>
              <li>
                Primary sources remain your published budgets and by-laws. This site is a lens, not a
                substitute for the corporate record.
              </li>
            </ul>
          </section>

          <section id="not-this" className="help-section">
            <h2>What this is not</h2>
            <ul>
              <li>Not your official tax bill or a payment portal.</li>
              <li>Not tax, legal, or investment advice.</li>
              <li>Not affiliated with the Township, County, Region, or Province.</li>
              <li>
                Not a ranking, score, or “value for money” leaderboard of municipalities (those are
                out of scope by design).
              </li>
              <li>
                Not an address or roll-number lookup — you use the assessment already printed on
                your bill or the published average/median the pack documents.
              </li>
            </ul>
          </section>

          <section id="faq" className="help-section">
            <h2>FAQ</h2>
            <div className="help-faq">
              <details>
                <summary>Why doesn’t my bill match the dollar amount on screen?</summary>
                <p>
                  This receipt uses a published average or median assessment for illustration. Your
                  notice uses your property’s assessed value and any area rates that apply to you.
                  Multiply the same rates by your assessment for a closer estimate — still not an
                  official bill.
                </p>
              </details>
              <details>
                <summary>Why is education on my municipal receipt?</summary>
                <p>
                  Education property tax is collected with the municipal bill in Ontario. The rate
                  is set provincially. Showing it keeps the “total you pay” honest.
                </p>
              </details>
              <details>
                <summary>Why is the Region so large in North Dumfries?</summary>
                <p>
                  In two-tier areas, upper-tier services (police, transit, housing, waste, and more)
                  are levied by the Region. The Township only controls its own rate column.
                </p>
              </details>
              <details>
                <summary>Why do Paris and Brant share one pack?</summary>
                <p>
                  Paris is an urban centre inside the County of Brant. Property tax for Paris is
                  billed by the County (single-tier). Searching “Paris” should resolve to Brant
                  County, not a separate lower-tier town pack.
                </p>
              </details>
              <details>
                <summary>Is DERIVED less trustworthy than FACT?</summary>
                <p>
                  DERIVED is trustworthy when the formula and inputs are trustworthy. It is a
                  different kind of claim: arithmetic over sources, not a quote of a printed
                  household line. Always read the note under the line.
                </p>
              </details>
              <details>
                <summary>Does “0 Watch” mean everything is fine?</summary>
                <p>
                  No. It means this pack has no published findings in the Watch list right now. Gaps
                  may still be open; Cite OK only speaks to citation hard failures.
                </p>
              </details>
              <details>
                <summary>Can I enter my address?</summary>
                <p>
                  No. Address and roll lookup raise privacy and licensing issues. Use the assessment
                  on your bill, or the pack’s documented average/median.
                </p>
              </details>
              <details>
                <summary>Who do I contact if something is wrong?</summary>
                <p>
                  For an error in our transcription or model, use the project contact once the pack
                  is Published (see the pack’s publication metadata). For questions about the
                  underlying budget, contact your municipality’s clerk or finance staff — and bring
                  the source page this receipt cites.
                </p>
              </details>
            </div>
          </section>

          <p className="help-footer-note">
            Glossary version for the multi-municipality prototype (North Dumfries + County of Brant).
            Picture callouts are placeholders until UI/UX is locked.
          </p>

          <button type="button" className="cta help-back-bottom" onClick={onBack}>
            ← Back to receipt
          </button>
        </article>
      </div>
    </div>
  )
}
