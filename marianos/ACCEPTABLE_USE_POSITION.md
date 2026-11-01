# The Kroger public-tier acceptable-use position

1 November 2026.

## Why this file exists

`marianos_collector/kroger.py` states that nothing reached through the public tier
is publishable here, and sets `publication_eligible: false` on every record it
produces. The 26,166-record Vernon Hills dataset of 31 October was collected
entirely through that tier.

The code and the delivered dataset therefore disagree. This file records the
disagreement rather than resolving it, because resolving it is not ours to do.

## What the policy says, and whose words these are

As held in this repository, Kroger's *Acceptable Use of Public APIs* carries two
prohibitions that bear on this work:

1. Systematically gathering response data to create a database.
2. Comparing products and prices among other retailers.

**Those are our paraphrase. They are not quoted policy, and nobody in this
repository has the quoted policy.** On 1 November 2026 the live text could not be
re-read from this environment:

| Attempt | Result |
|---|---|
| `developer.kroger.com/documentation/public/other/acceptable-use` | Not on this environment's fetch allowlist. Nothing retrieved. |
| `developer-ce.kroger.com/documentation/public/getting-started/acceptable-use?beta=true` | `robots_disallowed` at the site. Nothing retrieved. |

An unrelated public project records the same two prohibitions, in the same
paraphrased form, and reached the same conclusion that retaining the data and
comparing across retailers is not permitted. It also could not quote the text,
because the page requires sign-in
(`github.com/luiscarlosht/IntelligenceOS-Arbitrage` pull request 24, read 1
November 2026). That is independent corroboration that this reading is the
ordinary one and not an invention of this repository. It is not the text.

The consequence is a limit on this whole file: **no decision taken here may rest
on the exact wording, because the exact wording has not been read.** Anyone
relying on this must open the page while signed in to a Kroger developer account
and check it. That includes the possibility that the reading is stricter than the
policy actually requires.

## What was actually done

| Fact | Value |
|---|---|
| Records | 26,166, at Vernon Hills `53100502`, 31 October 2026 |
| Route | Public Products API only, `filter.term`, no partner endpoint touched |
| Raw responses retained | 998 captures, 384,805,738 bytes, hashed and kept in the package |
| Schema | The same 22 fields as the Walmart collector, for the same client |
| Intended operating pattern | Unattended, twice weekly, retained and accumulated |

## Which part engages which prohibition

The distinction below is real and worth stating precisely, because the two
prohibitions do not bite equally on everything that has been done.

| What | Prohibition 1, database | Prohibition 2, cross-retailer |
|---|---|---|
| The single 31 October demonstration run, retained as evidence | Arguable. Response data was gathered and is retained, hashed, as 998 captures. Whether one run is *systematic* gathering *to create a database* is the part that is arguable, not whether data was retained. | Not engaged by the run itself. |
| Unattended twice-weekly collection, accumulating over time | Squarely engaged. This is the pattern those words describe, and it is what the brief asks for. | — |
| Running beside the Walmart collector on one shared schema for one client | — | Engaged, depending on what the client does with the two datasets. That is his use of them, not ours. |

Two things follow. The demonstration is the weaker case against; the scheduled
production operation is the clear one. And the cross-retailer question is not
answerable from inside this repository at all, because it turns on the client's
own purpose.

**The distinction is not a permission.** Neither of us can grant one, and a weaker
case against is not a case for.

## The partner route

`marianos_collector/catalog_v2.py` exists, 26,270 bytes, restricted to the three
documented Catalog V2 paths, and has never been run against the live service.
`CATALOG_V2_RUNBOOK.md` states the position that the partner agreement is not an
administrative step in front of data that could otherwise be taken, but is what
grants the rights.

The partner request is drafted and ready, at `PARTNER_APPLICATIONS_2026-11-06.md`.
It has not been sent. Two reasons, both standing:

- The instruction not to register for anything or request entitlement is in force.
- Only the client has standing to request a commercial agreement. We do not.

Worth noting for the decision: Catalog V2 has no category filter, so a paged
sweep is exhaustive by construction once the API reports `hasMore: false`. The
partner route would therefore close the acceptable-use question, the five empty
roots and the category-completeness gap in one move. Those are currently three
separate open items with one shared cause.

## What this repository does pending a decision

- `publication_eligible` stays `false`. It is not flipped.
- The 31 October dataset stays labelled a demonstration, not a publishable
  deliverable. `reports/2026-10-31-vernon-hills-package-rerun/README.md` already
  says so and is not softened.
- No further public-tier collection is scheduled.
- Nothing is deleted. The 26,166 records and the 998 captures are kept with their
  status recorded, because an unfavourable status is a fact about the
  observation, not grounds for removing it.

## The decision, and whose it is

Three options. All three are the client's.

**A. Accept the demonstration framing.** The dataset proves the collector works at
his assigned store. The production route is treated as pending a partner
agreement. Nothing already built is lost and nothing is misrepresented.

**B. Authorise the partner request.** It costs nothing, registers nothing and buys
nothing. It reverses only the instruction about requesting entitlement. It is the
only option that produces a route which is both policy-clean and more complete
than what exists.

**C. Accept the public tier for production as his own commercial risk**, stated in
writing by him.

What will not be done without a decision: flip a restriction this repository has
already disclosed to him, on the strength of a text that could not be read.

## Not legal advice

This is a reading of a policy by the person who wrote the collector, working from
a paraphrase he could not re-verify. It is not legal advice and is not a
compliance opinion.
