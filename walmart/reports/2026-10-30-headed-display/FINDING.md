# Headed browser under a virtual display: what actually changes

Measured 30 October 2026. This closes the one gap the source feasibility
document explicitly left open, and the result corrects a prediction I had put
in writing.

## What I predicted, and what happened

I wrote, twice, that I expected a headed browser to be refused the same way as
headless "because the refusal is keyed to the address and not the window."

That was wrong about the mechanism. The window does change what the transport
returns. It does not change whether product data arrives.

## The measurement

Four URLs, one navigation each, no retries, no proxy, no header or TLS
manipulation, no challenge solving. Two arms in the same run from the same
container: headless Chromium, and headed Chromium under Xvfb at 1920x1080.
Chromium 153.0.8010.12. A neutral control returned HTTP 200 in both arms every
time.

Three consecutive runs produced identical results in every cell.

| Target | Headless | Headed under Xvfb |
|---|---|---|
| Neutral control | HTTP 200 | HTTP 200 |
| Walmart category | HTTP 200, "Robot or human?" | HTTP 200, **no challenge** |
| Walmart product | HTTP 200, "Robot or human?" | HTTP 200, "Robot or human?" |
| Mariano's category | **no response**, navigation timed out | HTTP 200, **no challenge** |

So the display is a real variable. Mariano's goes from returning nothing at all
to returning an HTTP 200, and the Walmart category page stops being challenged.
Walmart product pages are challenged either way, in all three runs.

## Why this is not a route

A 200 with no challenge marker is not product data, and treating it as such
would be the same mistake as reading a field name as a result. So I fetched the
Mariano's category page again in the headed arm and looked at what it contained.

- Final URL: `https://www.marianos.com/savings/c/dairy` — redirected, not the
  category that was requested
- Title: "Mariano's"
- Body: 1,946 characters, consisting of a consent notice and site navigation
- **Product links found: 0**
- Price-like tokens: 1
- The body still reads "Loading" where products would be

The page shell arrives. The products never populate. On a separate run the
Walmart category page returned `net::ERR_ABORTED` rather than the 200 the
probe had recorded, so that particular success is not dependable either.

What the headed arm gets is further than nothing and short of anything usable.

## What this does and does not establish

**Establishes:** the headless-versus-headed difference is real and reproducible
for these targets from this address. Any future claim that "a browser is
refused from a datacenter" must say which kind of browser, because the two do
not behave alike.

**Does not establish:** that a headed crawl can collect this data. It returned
no products in the one case examined closely.

**Does not establish anything about Azure.** This ran from a cloud container at
160.79.106.132-137, not from Azure. The 30 October measurement used Azure
Container Instances at 135.237.21.80, a different provider and a different
address reputation. The Azure result could be better or worse, and the probe
and its image are written to be run there to find out.

## What follows

The honest position is unchanged in its conclusion and improved in its
accuracy. A collector cannot be built on this. The consent interstitial, the
redirect away from the requested category, the empty product list and the
still-challenged product pages are four separate obstacles, and clearing them
is the work of defeating a bot-protection system rather than reading a page.

That remains something I will not build, and this measurement does not change
it. What the measurement changes is the reason given: not "a browser is refused
from a datacenter", which is now shown to be too strong, but "a headed browser
gets a shell and no products, and getting past that is challenge defeat."

## Reproducing it

```bash
docker build -f azure/Dockerfile.headed -t headed-probe .
docker run --rm headed-probe --arm both
```

Or from a checkout with Xvfb present:

```bash
xvfb-run -a --server-args="-screen 0 1920x1080x24" \
  python tools/headed_display_probe.py --out measurement.json
```

`measurement.json` beside this file is a full record from one such run.
