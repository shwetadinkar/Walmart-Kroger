# Store 100 notation probe, 1 November 2026

## What this was for

`walmart/submission/2026-10-31-provider-fields/` ships `ppm` composed from the
provider's `unit_price` and `unit`, producing strings in dollars such as
`$0.057/fl oz`. The repository discloses that Walmart renders the rate in cents
and that the composed string is therefore not the displayed notation. Until
today that disclosure rested on two page observations, both at a Sacramento
store, and `../2026-10-30-display-ab/STORE_CONTEXT_FINDING.md` forbids presenting a Sacramento
observation as store 100's.

This probe set out to observe the notation in store 100's own context.

## Result: not obtained. Third failure, new cause.

| Step | Result |
|---|---|
| Product page for Walmart item `1026071385`, UPC `094514020098` | Served |
| Displayed rate on it | `5.7 ¢/fl oz` |
| Displayed price on it | `$5.78` |
| Store context of that observation | **Sacramento, 95829. Not store 100.** |
| Setting ZIP 72712 in the product page location panel | Refused: "We're currently experiencing technical issues. Please try again in a few minutes." |
| The same change attempted by hand by the operator, in his own browser | Refused the same way. Not an automation effect. |
| `/store/100-bentonville-ar` | Served. Confirmed Store 100, 406 S Walton Blvd, Bentonville AR 72712 |
| "Make this my store" on that page | Accepted, no error shown |
| Reloading the product page immediately after | Redirected to `walmart.com/blocked`, page titled **"Robot or human?"** |

The run stopped there. The challenge was not answered, not worked around, and
was not passed to anyone else to answer. Under the standing position in
`../../../CLAUDE.md`, a route that requires defeating bot protection is an unavailable
route, and that is the finding rather than a problem to solve.

## What was established

**The cent notation is confirmed as a rendering, on a served Walmart page.**
`5.7 ¢/fl oz`, with the cent sign, for the exact product that is row one of the
615. The composed value shipped for that row is `$0.057/fl oz`. Same number,
different notation, which is what the submission already discloses.

**It is still not confirmed at store 100.** This observation is Sacramento's,
like the two before it. The disclosure in
`../../submission/2026-10-31-provider-fields/NOTE.md` and `../../../CLAUDE.md` stands
unchanged and must not be upgraded on the strength of this.

**A new and useful data point for `regular_price`.** The Sacramento page showed
`$5.78`. The provider's `final_price` for this product, written into
`regular_price` in the 31 October export, is also `5.78`. The same price at a
store roughly two thousand miles from store 100 is consistent with `final_price`
being a national online price rather than a store-specific one. That is exactly
the caveat the export already carries, and this strengthens it. One product is
not a demonstration, so it is recorded as a data point, not a conclusion.

**The store picker failure is Walmart's, and it is not caused by automation.**
Walmart's own "technical issues" message has refused the product-page location
panel on separate days and in more than one browser, and — the decisive point —
**the operator reached the same refusal by hand, in his own browser, driving it
himself as an ordinary signed-out user.** A manual refusal rules out the
explanation that the site was degrading a write endpoint for a client it
distrusted. Whatever is wrong is on Walmart's side of the request.

**The leading explanation is that store selection is unavailable to this
traffic, and it is a hypothesis, not a finding.** Everything observed fits it:
the browser is never asked which store, it is assigned Sacramento 95829 on its
own; the only call that fails is the one that would change that assignment; and
the data provider, which collects from United States infrastructure, does return
output in a store 100 / ZIP 72712 context. The work here is done from India. A
retailer limiting store selection to traffic it places in the United States
would produce exactly this pattern.

It is a hypothesis because it has not been tested, and it will not be tested
here. The test would mean presenting the request as coming from somewhere it is
not, which is the identity-and-proxy routing this repository does not do, under
any name and for any purpose. The consequence is recorded instead: a store 100
page observation is not obtainable from this location by any means this project
is willing to use, and the remaining legitimate route is the provider, whose
own collection already carries the 72712 context. That question is open on
ticket #754118.

## What this does not establish

- Nothing about store 100's displayed notation, price, or availability. No page
  was observed in store 100's context.
- Not that setting the store caused the challenge. The challenge appeared on the
  next request after "Make this my store", and this probe did not separate the
  two. Walmart's protection may equally have triggered on request volume or on
  the automation itself.
- Not whether the store was actually set. The product page never rendered again,
  so the setting was never read back.
- Not that `regular_price` is or is not store 100's price. One matching price at
  one other store is a data point about one product.

## Consequence

The store 100 notation observation remains outstanding, and the route that would
produce it now ends at a bot challenge. Options that stay inside the standing
position are: the provider supplying the rendered string directly, which was
already asked for on ticket #754118; or the client accepting the composed value
as labelled, which the submission already discloses in full. Neither requires
anything further from this route.
