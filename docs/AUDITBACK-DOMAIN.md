# auditback.ca rollout

`auditback.ca` is the intended public brand domain. The existing Worker name and
`workers.dev` address remain the rollback path until the custom domain is stable.

## Before registration

- Confirm current availability with [CIRA WHOIS](https://www.cira.ca/en/ca-domains/whois/).
- Complete an appropriate name and trademark clearance. A domain-registration
  result is not a trademark clearance.
- Register with auto-renew, registrar lock, account MFA, recovery codes, and the
  correct Canadian Presence Requirement category.

## Cloudflare cutover

1. Add the registered domain to the same Cloudflare account as the Worker.
2. If the registrar is external, follow
   [Cloudflare full-zone setup](https://developers.cloudflare.com/dns/zone-setups/full-setup/setup/).
   Handle registrar DNSSEC exactly as Cloudflare directs during the nameserver
   transition.
3. Keep the existing `workers.dev` deployment healthy.
4. Attach the apex as a
   [Workers Custom Domain](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/).
   After the domain is registered and active, the Wrangler configuration can add:

   ```json
   "routes": [
     {
       "pattern": "auditback.ca",
       "custom_domain": true
     }
   ]
   ```

5. Redirect `www.auditback.ca` to the apex rather than serving two canonical
   copies.

## Release checks

- HTTPS certificate is active and renews normally.
- Apex and `www` redirect behaviour is correct.
- Every supported `?pack=` deep link loads the requested place and never
  substitutes another one.
- Place finder, Help, source links, privacy notice, CSP, referrer policy, and
  mobile layouts work on the custom domain.
- `X-Robots-Tag` and the HTML `noindex, nofollow` directive remain in place
  while receipts are draft previews.
- The `workers.dev` URL remains documented and tested as rollback.
- Canonical and social metadata are added only after the public hostname is
  verified.
- Correction and privacy addresses are monitored before they are advertised.
  If email is enabled, configure SPF, DKIM, and DMARC.

Changing the Worker name, GitHub repository name, or Pages base path is a
separate migration and is not required for the domain cutover.
