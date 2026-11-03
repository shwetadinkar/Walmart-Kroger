# What observing the schedule does not establish

**It did not run on Azure.** No Azure Container Apps job was created, no Azure
cron fired, and nothing ran in the client's subscription. The only Azure
execution evidence in this project remains the three-execution pilot of 28
October, which was manually driven, at West Loop, on a five-product selection
of the single term `milk`.

**The cadence observed is not the deployed cadence.** The deployed schedule is
twice weekly and the observation ran every few seconds. That compression is why
the two claims are reported separately: the firing *times* are checked by
computing them from the deployed expression, and the *unattended repetition* is
observed in real time at a cadence nobody has to wait a week for. Neither
result stands in for the other.

**The data is replayed.** Only the Kroger HTTP client is stubbed, so the
collector, schema, retention reconciliation and storage are all real, but the
products are invented. Nothing here is evidence about this store's assortment
or any figure in the delivered dataset.

**It says nothing about the client's environment.** His Azure subscription, his
storage account, his secrets and his network are untested, and the brief asks
for operation there.

**One week of real operation is still unobserved.** Even on the real schedule,
this would need a week to show two firings. Nothing here shortens that; it
shows the expression is right and that repetition needs no operator.
