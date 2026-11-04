# Attended browser attempt at a directly captured store 100 PPM, 4 November 2026

## Why this was attempted

The client's review of 4 November says plainly that **"the separate composed-PPM
export does not satisfy directly captured PPM."** He is right, and the composed
value is labelled composed everywhere it appears for that reason.

The attended browser route had just been shown to work at the other retailer, at
the assigned store, with no refusal. So the question worth settling was whether
the same route gives a *directly captured* displayed rate at Walmart store 100,
in the cents notation a shopper sees, which would answer his objection outright.

It does not. This records the attempt, because an untested claim that a route is
closed is the failure this repository has already made twice.

## What was observed

**1. The search page serves the displayed rate, in cents, with no challenge.**

`https://www.walmart.com/search?q=milk` returned 27 displayed rates in the
rendered cents form: `7.4 ¢/fl oz`, `17.2 ¢/fl oz`, `5.8 ¢/fl oz` and so on. No
bot challenge of any kind. So the field the client wants is reachable in
principle through this route, in the correct notation.

**2. The store was not store 100, and nothing from that page is used.**

The page's own payload gave `storeId: "3081"`, `postalCode: "95829"`,
`city: "Sacramento"`, `stateOrProvinceCode: "CA"`. A cookie read
`isoLoc=IN_DL_t3`, so Walmart geolocated the request to India and defaulted to a
Sacramento store.

**Those 27 rates are store 3081's and are recorded nowhere.** Not in an export,
not in a scratch file, not quoted as a Walmart figure anywhere outside this
sentence. This repository has already published one store's data under another
store's name once, and a displayed rate from the wrong store is that same
mistake with better-looking evidence.

**3. Switching to store 100 hits a bot challenge.**

`https://www.walmart.com/store/100-bentonville-ar` is the real store page, and it
does serve the right store: the title reads `... | Serving 72712 | Store 100` and
the page carries a `Make this my store` control. It also carries:

> Robot or human? Activate and hold the button to confirm that you're h...

That is a press-and-hold bot challenge, verified by reading the matched text
rather than by a keyword hit. The first check in this session flagged
`challenge: true` on a pattern that could have matched a toy robot in a store
directory, and the text was read before anything was concluded, because a route
declared closed on an unchecked match is worse than no attempt.

## The conclusion, and its exact scope

**Directly captured store 100 PPM is not obtainable through this route**, because
reaching store 100 context requires getting past a bot challenge, and defeating a
retailer's bot protection is not done here by any name. That is a standing
position, not a reading of the brief, and it is not relaxed because the value
behind it is one the client has asked for.

So the composed value from the provider's two observed fields, labelled composed
and with the cents-versus-dollars notation difference disclosed, remains the only
available form of this column. That was already the position. What changed is
that it now rests on a test at the right store on the current site, rather than
on an inherited claim.

## What this does not establish

- **It does not establish that Walmart blocks us generally.** The search page
  served fully, with no challenge, on the same machine minutes earlier. The
  challenge appeared on the store-selection path specifically.
- **It does not establish that the provider's store switch works or fails.** The
  provider reports a technical error with Walmart's store chooser on their side;
  this is our own browser meeting a challenge on that same path. Two
  observations about the same part of the site, from different clients, neither
  one evidence for the other.
- **It does not establish anything about the 615 delivered records.** No value
  was taken, and the store 100 context question on those records remains exactly
  as open as it was, awaiting the provider's answer on ticket #754118.
- **It does not establish that the rate is unobtainable by other means.** It is
  unobtainable through every route currently open to us, which is a different
  sentence.

## What was not done

No challenge was solved, by hand or otherwise. No attempt was made to have a
person press the button so that automated reading could continue past it, which
would be defeating the protection by proxy rather than respecting it. No second
path to the same store context was tried after the challenge appeared.
