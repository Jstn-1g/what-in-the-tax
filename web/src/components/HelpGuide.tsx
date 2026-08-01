/**
 * Resident-friendly help for reading a What in the Tax? receipt.
 */

const SECTIONS = [
  { id: 'about', title: 'What this site is for' },
  { id: 'quick-start', title: 'Quick start' },
  { id: 'evidence-labels', title: 'Evidence labels' },
  { id: 'calculations', title: 'How calculations work' },
  { id: 'governing-bodies', title: 'Which governing bodies can appear' },
  { id: 'sources-corrections', title: 'Sources and corrections' },
  { id: 'technical', title: 'How it works, technically' },
  { id: 'contributing', title: 'Contributing and credits' },
  { id: 'faq', title: 'FAQ' },
] as const

// Attribution links render as plain names until the exact URLs are supplied;
// a wrong personal link would be worse than a missing one.
const BUILDER_LINKS: { eversko: string | null; linkedin: string | null } = {
  eversko: null,
  linkedin: null,
}

function BuilderLink({
  href,
  children,
}: {
  href: string | null
  children: string
}) {
  if (!href) return <strong>{children}</strong>
  return (
    <a href={href} target="_blank" rel="noreferrer">
      {children}
      <span className="visually-hidden"> (opens in a new tab)</span>
    </a>
  )
}

export default function HelpGuide({
  onBack,
  onNavigate,
  backLabel = 'Back to receipt',
  simpleLanguage = false,
}: {
  onBack: () => void
  onNavigate: (targetId: string) => void
  backLabel?: string
  simpleLanguage?: boolean
}) {
  return (
    <main id="help/main" className="help-page" tabIndex={-1}>
      <header className="help-hero">
        <p className="help-kicker">Help</p>
        <h1 id="help-heading" tabIndex={-1}>
          How to use What in the Tax?
        </h1>
        <p className="help-lede">
          What in the Tax? turns public budgets, tax-rate schedules, and by-laws
          into a plain-language example. It is independent—not a government
          service, formal financial audit, official tax bill, or tax advice.
        </p>
        {simpleLanguage ? (
          <p className="help-eli5-note" role="status">
            <strong>Plain language is on.</strong> Technical evidence labels remain visible so you
            can match this guide to the receipt.
          </p>
        ) : null}
        <div className="help-hero-actions">
          <button type="button" className="cta" onClick={onBack}>
            {backLabel}
          </button>
          <a
            className="cta cta-ghost help-toc-jump"
            href="#help/toc"
            onClick={(event) => {
              event.preventDefault()
              onNavigate('help/toc')
            }}
          >
            See help topics
          </a>
        </div>
      </header>

      <div className="help-layout">
        <nav
          className="help-toc"
          id="help/toc"
          aria-label="Help topics"
          tabIndex={-1}
        >
          <p className="help-toc-title">On this page</p>
          <ol>
            {SECTIONS.map((section, index) => (
              <li key={section.id}>
                <a
                  href={`#help/${section.id}`}
                  onClick={(event) => {
                    event.preventDefault()
                    onNavigate(`help/${section.id}`)
                  }}
                >
                  <span className="help-toc-num">{String(index + 1).padStart(2, '0')}</span>
                  {section.title}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <article className="help-article">
          <section id="help/about" className="help-section" tabIndex={-1}>
            <h2>What this site is for</h2>
            <p>
              Property taxes are most people&apos;s largest direct payment to
              government, and the answer to &ldquo;where does that money
              go?&rdquo; is spread across budget binders, by-laws, and
              financial returns that few residents have time to read. What in
              the Tax? reads those public documents and turns them into a
              receipt: where a sample tax bill for your community goes, line by
              line, with every number linked to the official record it came
              from.
            </p>
            <p>
              Three commitments shape everything here. <strong>Every number
              traces to a source</strong> &mdash; a budget, by-law, or the
              province&apos;s own Financial Information Return &mdash; and the
              link is on the page, so you never have to take our word for it.
              <strong> Missing evidence stays visible</strong> &mdash; where a
              document does not answer a question, the receipt shows a gap
              rather than an estimate. <strong>Mistakes are logged in
              public</strong> &mdash; every resolved correction report lands in
              a public log with a date, whatever the outcome.
            </p>
            <p>
              This is an independent, open-source public-information project.
              It is not a government service, not your tax bill, not a formal
              audit, and not tax advice. Everything on the site today is a
              draft preview while the project&apos;s publication checks are
              completed &mdash; the site says so on its face rather than
              implying more than the evidence supports.
            </p>
          </section>

          <section id="help/quick-start" className="help-section" tabIndex={-1}>
            <h2>Quick start</h2>
            <ol className="help-steps">
              <li>
                <strong>Confirm the place, tax year, and status.</strong> A draft or preview may
                still have open gaps. A published receipt has passed the project&apos;s release
                checks.
              </li>
              <li>
                <strong>Check the sample assessment.</strong> What in the Tax?
                does not look up an address or roll number. The amount shown is
                an example unless you calculate from your own assessed value.
              </li>
              <li>
                <strong>Read the combined total and its parts.</strong> Each part shows which public
                body levies or controls that amount.
              </li>
              <li>
                <strong>Check the evidence.</strong> Open a source link for any figure you want to
                verify and review any listed gaps before relying on the result.
              </li>
            </ol>
          </section>

          <section id="help/evidence-labels" className="help-section" tabIndex={-1}>
            <h2>Evidence labels</h2>
            <p>
              These labels describe how a claim was produced. They do not grade a government or
              imply that anyone did something wrong.
            </p>
            <dl className="help-glossary">
              <div>
                <dt>FACT</dt>
                <dd>
                  A figure copied from an identified public source. Technical details should name
                  the document and, when possible, the page or record.
                </dd>
              </div>
              <div>
                <dt>DERIVED</dt>
                <dd>
                  A result calculated from sourced inputs with a stated formula. It can be checked
                  again, but it is not necessarily a number printed on an official bill.
                </dd>
              </div>
              <div>
                <dt>GAP</dt>
                <dd>
                  Evidence is missing, incomplete, or not strong enough to support a claim. The
                  receipt leaves the value open instead of guessing.
                </dd>
              </div>
              <div>
                <dt>JUDGMENT</dt>
                <dd>
                  A clearly identified interpretation based on cited facts. A judgment does not
                  imply wrongdoing, and its bill impact stays unset unless a reviewed formula
                  supports one.
                </dd>
              </div>
            </dl>
            <p>
              A citation or source check only tests whether a claim points to supporting material.
              It does not, by itself, make a receipt complete or ready to publish.
            </p>
          </section>

          <section id="help/calculations" className="help-section" tabIndex={-1}>
            <h2>How calculations work</h2>
            <p className="help-formula">tax component = assessed value × published tax rate</p>
            <p>
              What in the Tax? adds the applicable components to show a combined
              sample total. Depending on the place, those components may include
              local, regional, education, or special levies. Rounding is shown
              rather than hidden when cents need to be reconciled.
            </p>
            <p>
              A service or department breakdown may be a proportional model over a government&apos;s
              published net requirement. Those lines are marked <strong>DERIVED</strong> and are not
              a second official bill. Values are never borrowed from another municipality to fill
              a missing local figure.
            </p>
          </section>

          <section id="help/governing-bodies" className="help-section" tabIndex={-1}>
            <h2>Which governing bodies can appear</h2>
            <p>
              Canadian property-tax systems vary. A receipt may include a municipality, township,
              city, county, regional or district government, education body, province or territory,
              or another authority with a documented levy that applies to the selected place.
            </p>
            <p>
              Some places have one local tier; others have two or more public bodies on the same
                bill. What in the Tax? follows the structure in official records.
                It does not substitute a nearby or similarly named municipality
                when the correct body or source is missing.
            </p>
          </section>

          <section id="help/sources-corrections" className="help-section" tabIndex={-1}>
            <h2>Sources and corrections</h2>
            <p>
              Sources can include adopted budgets, tax-rate schedules, by-laws, financial reports,
              and official open-data records. A source link lets you compare the receipt with the
              public record.
            </p>
            <dl className="help-glossary">
              <div>
                <dt>Draft</dt>
                <dd>Work is in progress and may contain unresolved evidence or calculation gaps.</dd>
              </div>
              <div>
                <dt>Preview</dt>
                <dd>
                  The receipt can be reviewed publicly, but it has not passed every publication
                  gate.
                </dd>
              </div>
              <div>
                <dt>Not published</dt>
                <dd>
                  This static preview does not label any receipt Published. A
                  public publisher and correction route have not been designated.
                </dd>
              </div>
            </dl>
            <p>
              Corrections and additional official evidence are welcome. A covered governing body
              has a right to reply to a finding, and a disputed point remains clearly labelled
              while it is reviewed. A gap, question, or correction request is not an allegation of
              waste, misconduct, or wrongdoing.
            </p>
            <p>
              The project is open source: every number on this site, the evidence behind it, and
              the checks that gate it live in a{' '}
              <a
                href="https://github.com/Jstn-1g/what-in-the-tax"
                target="_blank"
                rel="noreferrer"
              >
                public repository
                <span className="visually-hidden"> (opens in a new tab)</span>
              </a>
              . To report a figure that looks wrong, open a{' '}
              <a
                href="https://github.com/Jstn-1g/what-in-the-tax/issues/new?template=wrong-number.yml"
                target="_blank"
                rel="noreferrer"
              >
                correction issue
                <span className="visually-hidden"> (opens in a new tab)</span>
              </a>
              . Every resolved report is recorded in the repository&apos;s{' '}
              <a
                href="https://github.com/Jstn-1g/what-in-the-tax/blob/main/CORRECTIONS.md"
                target="_blank"
                rel="noreferrer"
              >
                public corrections log
                <span className="visually-hidden"> (opens in a new tab)</span>
              </a>
              , whatever the outcome.
            </p>
            <p>
              Contributions are welcome beyond corrections: pull requests that
              add official sources, evidence, or coverage follow{' '}
              <a
                href="https://github.com/Jstn-1g/what-in-the-tax/blob/main/CONTRIBUTING.md"
                target="_blank"
                rel="noreferrer"
              >
                the contribution guide
                <span className="visually-hidden"> (opens in a new tab)</span>
              </a>
              . Every contributed figure must trace to an official public
              source and pass the same checks as everything else here; nothing
              is published without human review.
            </p>
          </section>

          <section id="help/technical" className="help-section" tabIndex={-1}>
            <h2>How it works, technically</h2>
            <p>
              For readers who want the machinery: the site is a static page
              built from a pipeline where every step is checked and nothing
              publishes on trust.
            </p>
            <ul className="help-technical-list">
              <li>
                <strong>Sources are hash-locked.</strong> Each official input
                &mdash; Ontario&apos;s Financial Information Return bulk files,
                the municipal directory, budget and by-law PDFs &mdash; is
                recorded in a reviewed lock file carrying its exact URL,
                SHA-256 digest, byte count, and review date. If a government
                server re-publishes a file, the changed bytes are quarantined
                and every build fails until a person reviews and adopts the
                change. That gate fired during this launch when Ontario
                re-exported its FIR files overnight, and the adoption is in the
                public commit history.
              </li>
              <li>
                <strong>Builds are deterministic, with no AI at runtime.</strong>{' '}
                Receipts are generated from the locked bytes by deterministic
                parsers; the build asserts zero AI tokens were used. Continuous
                integration rebuilds every receipt from the locks and compares
                byte-for-byte, so a tampered artifact or a drifted source
                cannot ship silently.
              </li>
              <li>
                <strong>Citations are audited.</strong> For the hand-built
                receipt previews, an auditor re-locates every figure on the
                cited page of the hash-locked source extract and grades the
                match (verbatim, normalized, row-bound, and weaker tiers). The
                measured results are disclosed on each receipt as its
                source-check line; hard failures block publication.
              </li>
              <li>
                <strong>Deployment is sealed and human-approved.</strong> A
                release is a bundle whose manifest hashes every file in both
                directions. It reaches the public site only through a pipeline
                that re-verifies those hashes, requires a named human&apos;s
                recorded publication approval, and deploys through a protected
                environment a person must approve &mdash; then re-checks that
                the live site serves exactly the promoted bytes, with automatic
                rollback if it does not.
              </li>
              <li>
                <strong>Everything is inspectable.</strong> The code, the
                evidence ledgers, the lock files, the audit results, and this
                page&apos;s own history are in the public repository linked in
                the footer. If you can read a diff, you can re-run our checks.
              </li>
            </ul>
          </section>

          <section id="help/contributing" className="help-section" tabIndex={-1}>
            <h2>Contributing and credits</h2>
            <p>
              Every change here lands through a public pull request that must
              pass the same gates as everything already published. The short
              version of the process:
            </p>
            <ul className="help-technical-list">
              <li>
                <strong>Find what is needed.</strong> Three places list real
                work: the{' '}
                <a
                  href="https://github.com/Jstn-1g/what-in-the-tax/issues"
                  target="_blank"
                  rel="noreferrer"
                >
                  open issues
                  <span className="visually-hidden"> (opens in a new tab)</span>
                </a>{' '}
                (each labelled with what kind of decision or evidence it
                needs), the gaps shown on any receipt &mdash; each one is a
                missing piece of official evidence someone could contribute
                &mdash; and the per-province rollout manifests in the
                repository, which record exactly which stage every province is
                at and what evidence would advance it.
              </li>
              <li>
                <strong>Open a pull request.</strong> Fork the repository,
                make the change on a branch, and open a PR &mdash; the
                template walks through what a reviewable change must declare.{' '}
                <a
                  href="https://github.com/Jstn-1g/what-in-the-tax/blob/main/CONTRIBUTING.md"
                  target="_blank"
                  rel="noreferrer"
                >
                  CONTRIBUTING.md
                  <span className="visually-hidden"> (opens in a new tab)</span>
                </a>{' '}
                is the full guide: evidence rules first, then the mechanics.
                The golden rule: every figure must trace to an official public
                source, and missing evidence is declared as a gap, never
                estimated.
              </li>
              <li>
                <strong>Checks run, a person reviews.</strong> Continuous
                integration rebuilds every receipt from the hash-locked
                sources and refuses anything that does not reproduce; a
                maintainer reviews what machines cannot judge. Nothing merges
                on trust, including the maintainer&apos;s own changes.
              </li>
              <li>
                <strong>Built with.</strong> The site is React, TypeScript and
                Vite; the evidence pipeline is deterministic Python; checks
                run on GitHub Actions; hosting is a Cloudflare Worker serving
                static files. No database, no accounts, no analytics, and no
                AI in the data path &mdash; the build asserts zero AI tokens.
              </li>
              <li>
                <strong>Built by.</strong> Created and maintained by{' '}
                <BuilderLink href={BUILDER_LINKS.linkedin}>
                  Justin Skowyra
                </BuilderLink>{' '}
                of <BuilderLink href={BUILDER_LINKS.eversko}>Eversko</BuilderLink>,
                with AI-assisted engineering under human review &mdash; every
                published number still traces to an official source, and every
                release is approved by a named person.
              </li>
            </ul>
          </section>

          <section id="help/faq" className="help-section" tabIndex={-1}>
            <h2>FAQ</h2>
            <div className="help-faq">
              <details>
                <summary>Why does the sample differ from my tax bill?</summary>
                <p>
                  Your bill uses your property&apos;s assessed value and any area-specific charges.
                    What in the Tax? may use a published average, median, or other
                    documented example. Your official bill remains the source for
                    what you owe.
                </p>
              </details>
              <details>
                <summary>Can I enter my address or roll number?</summary>
                <p>
                    No. What in the Tax? does not provide an address or roll-number
                    lookup. Use the assessed value on your official notice if the
                    receipt offers a calculator.
                </p>
              </details>
              <details>
                <summary>Why is a governing body or amount missing?</summary>
                <p>
                    The correct official source may not yet be available or
                    verified. What in the Tax? marks that as a gap instead of
                    using another municipality&apos;s data or an unsupported
                    estimate.
                </p>
              </details>
              <details>
                <summary>Does a source check mean the receipt is ready?</summary>
                <p>
                  No. Source matching is one check. Place identity, calculation, completeness,
                  review, and release-state checks must also pass before publication.
                </p>
              </details>
              <details>
                <summary>What should I do if a figure is wrong?</summary>
                <p>
                  Note the place, tax year, line, and official source that supports the correction.
                    What in the Tax? can then review the evidence, update the
                    receipt, and preserve a clear record of the change.
                </p>
              </details>
            </div>
          </section>

          <p className="help-footer-note">
            What in the Tax? receipts are independent summaries of public
            information. Always use your official notice for payment, deadlines,
            exemptions, and account-specific questions.
          </p>

          <button type="button" className="cta help-back-bottom" onClick={onBack}>
            {backLabel}
          </button>
        </article>
      </div>
    </main>
  )
}
