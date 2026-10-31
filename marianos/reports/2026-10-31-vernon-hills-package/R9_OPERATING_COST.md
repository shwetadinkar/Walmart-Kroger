# Requirement 9: estimated monthly operating cost

An estimate from one measured run and stated assumptions. No Azure invoice or meter export
stands behind it. This collection itself cost nothing in paid services.

| Input | Value | Basis |
|---|---:|---|
| Runs per month | 8.67 | Brief: twice a week, 104 a year |
| Runtime per run | 1445.9 s | Measured, on a workstation and not on Azure |
| Requests per run | 888 | Measured |
| Allocation | 0.5 vCPU, 1 GiB | The earlier Azure job's size; not validated for a sweep this large |

Monthly usage:

| Item | Quantity | Cost |
|---|---:|---|
| Kroger API | 7,696 requests | $0 |
| Compute | 6,266 vCPU-seconds, 12,531 GiB-seconds | $0 if within the free grant |
| Raw captures, if all are kept | 2.9 GB added each month | Not priced |
| Logs | Not measured | Not priced |

The compute figures are about 3.5% of the free grant recorded in the 25 October cost
worksheet, 180,000 vCPU-seconds and 360,000 GiB-seconds a month. That grant is shared with every
other workload in the subscription, including Walmart, so the remainder is not known here.
The worksheet's earlier planning range of US$0 to US$20 a month still stands as a planning
estimate, not as measured spend. No regional storage or log price was verified, so those lines
are unresolved rather than zero.

Not in this estimate:

- Any route for displayed PPM and deal wording. None works today, so it has no price.
- Kroger Catalog V2 partner access, whose terms are unknown.
- Moving the sweep into the image, and memory for a run of this size, which was not measured.
