# Merge proof, run against the superseded 26,166 spine

The delivered 28,549 release is not in this checkout, so the corrected merge
was proved against the 26,166 set that is. The spine was rebuilt from
`out/vernon-hills-merged-rerun-2026-11-01-v2/data_22_fields_enriched.json` by
blanking `ppm`, `volume_deals_description` and `digital_deals_description`,
then the two page reads were merged onto it in order.

| stage | ppm | volume | digital |
|---|---:|---:|---:|
| as shipped, 1 Nov, old parser | 592 | 181 | 51 |
| corrected 1 Nov only | 592 | 120 | 53 |
| corrected 1 Nov + 4 Nov | **729** | **147** | **53** |

Zero conflicts at both stages. 271 of the 4 November read's 279 UPCs bound;
8 are not in the API set and contributed nothing. `ppm` is unchanged by the
deal-column fix at every stage, which is the check that the fix touched only
the two columns it was meant to.

These numbers are **not** the delivered release's numbers. They are the proof
that the chain runs and in which direction it moves. The same two commands
against the 28,549 spine produce that release's figures.
