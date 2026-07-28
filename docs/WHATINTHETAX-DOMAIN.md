# whatinthetax.com rollout

`whatinthetax.com` is the public brand domain. The operator reports it
registered through **Cloudflare Registrar** on the same Cloudflare account as
the Worker (reported 2026-07-28; not independently verified in this repository).

Registration is not clearance and not publication. A registrar result is not a
trademark clearance, and attaching the domain does not change any pack's state:
every pack remains a **draft preview** under `PUBLISH.md`, and the deployment
stays `noindex` until those gates pass. The `workers.dev` address remains the
rollback path until the custom domain is stable.

## Registration posture

Because the domain is on Cloudflare Registrar, the DNS zone was created and
made active automatically on Cloudflare nameservers. The full-zone nameserver
transition described in
[Cloudflare full-zone setup](https://developers.cloudflare.com/dns/zone-setups/full-setup/setup/)
does **not** apply, and registrar DNSSEC handling is managed by Cloudflare.
Nameservers cannot be moved to another DNS provider while the domain remains on
Cloudflare Registrar.

Confirm before proceeding:

- Auto-renew is on, registrar lock is on, account MFA is enabled, and recovery
  codes are stored outside the account.
- Registrant contact details and the privacy/proxy setting are correct.
- The apex carries no pre-existing CNAME record. Cloudflare refuses a Workers
  Custom Domain on an apex that already has one.

## Blocking: deployed branch does not match current work

This is a release blocker, not a DNS problem, and it must be resolved before the
domain is attached.

- Cloudflare Workers Builds deploys from the production branch recorded in
  `docs/DEPLOY.md` (`cursor/north-dumfries-taxpayer-receipt`, also the GitHub
  default branch).
- Current development is on `codex/canada-rollout-hardening`, which is ahead of
  that branch and additionally carries a large uncommitted working tree.
- Attaching the domain in this state points the public brand hostname at a build
  that predates the current Ontario municipal directory, the FIR year history,
  and the release-pipeline hardening.

Required before cutover:

1. Commit the working tree.
2. Decide explicitly whether the hardening branch merges into the production
   branch or replaces it as the Cloudflare production branch. Update
   `docs/DEPLOY.md` so the recorded production branch, the GitHub default
   branch, and the Cloudflare Workers Builds setting all agree. A silent
   disagreement between those three is how the wrong bytes reach a public name.
3. Run the full gate in `docs/DEPLOY.md` — Python tests, regional registry
   validation, public-pack projection check, Ontario index checks, every
   non-template pack validated in `--no-write` mode, clean-tree assertion, web
   tests, production dependency audit, web build, Wrangler dry run — and require
   it green.

## Cloudflare cutover

1. Confirm the zone is active in the same Cloudflare account as the Worker.
2. Attach the apex as a
   [Workers Custom Domain](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/).
   `wrangler.jsonc` now declares:

   ```json
   "routes": [
     {
       "pattern": "whatinthetax.com",
       "custom_domain": true
     }
   ]
   ```

   Cloudflare creates the DNS record and issues the certificate. The route
   attaches only on a production deploy from the production branch; feature
   branches run `wrangler versions upload` and cannot attach it.
3. Keep `workers_dev` enabled. It is declared explicitly in `wrangler.jsonc`
   because `docs/DEPLOY.md` depends on that address as the rollback target;
   adding `routes` does not disable it, but the value is not left to a default.
4. Redirect `www.whatinthetax.com` to the apex rather than serving two canonical
   copies. `www` is not a Worker route. Create a **proxied** placeholder record
   so Cloudflare terminates the request — AAAA `100::` (RFC 6666 discard prefix)
   or A `192.0.2.0` (RFC 5737 documentation range), per Cloudflare's originless
   setup guidance — then add a 301 Redirect Rule from `www` to the apex. An
   unproxied record cannot be redirected.

## Release checks

Run these against the custom domain, not against `workers.dev`, and verify the
response rather than trusting a command's exit code.

- `X-Robots-Tag: noindex, nofollow` is present on the custom domain. This is the
  highest-consequence check on this page: a draft preview indexed under the
  brand domain is expensive to reverse. Verify before the address is shared.
- The HTML `noindex, nofollow` directive is also still present.
- Content-Security-Policy, `Referrer-Policy: no-referrer`,
  `Strict-Transport-Security`, and the frame/MIME controls from
  `web/public/_headers` all survive on the new hostname. The policy is
  host-relative (`'self'`) and needs no edit, but confirm rather than assume
  that Static Assets applied the file.
- HTTPS certificate is active and renews normally.
- Apex and `www` redirect behaviour is correct, in both directions tested.
- Every supported `?pack=` deep link loads the requested place and never
  substitutes another one.
- Place finder, Help, source links, and mobile layouts work on the custom
  domain.
- `privacy.txt` resolves at the new deployment base.
- The `workers.dev` URL remains documented and tested as rollback.
- Canonical and social/OpenGraph metadata are added only after the public
  hostname is verified, and not while packs are draft previews.

## Email and impersonation defence

- `docs/DEPLOY.md` and `PUBLISH.md` require a monitored corrections address and
  privacy address before either is advertised. Do not print an address that
  nobody is reading.
- If mail is enabled, configure SPF, DKIM, and DMARC before publishing the
  address.
- **Even if no mail is ever sent from this domain**, publish a null SPF record
  (`v=spf1 -all`) and a DMARC policy of `p=reject` at registration time. An
  unconfigured brand domain is spoofable, and a public-finance project is a
  plausible target for impersonation.

## Out of scope

Changing the Worker name, the GitHub repository name, or a Pages base path is a
separate migration and is not required for the domain cutover. The Worker name
`tax-receipt-prototype` remains the deploy identity and the `workers.dev`
hostname regardless of the brand domain.
