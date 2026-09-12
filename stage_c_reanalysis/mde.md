# Stage-C minimum detectable effects

MDE is the two-sided 5%-alpha, 80%-power normal-approximation planning threshold, computed as `(z0.975 + z0.80) × SD(P1 family rates) / sqrt(G)`. Seeds are averaged within episodes and episodes within scenario families. This uses Stage C's observed between-family P1 variance; it is a sensitivity diagnostic, not a claim that the small-G normal approximation is reliable.

| Correct action | Episodes | Family clusters (G) | P1 success | MDE | Status |
|---|---:|---:|---:|---:|---|
| abandon | 49 | 4 | 100.0% | not estimable | not_estimable_saturated_baseline |
| adapt | 55 | 8 | 89.7% | 37.3 points | fragile_fewer_than_10_clusters |
| escalate | 24 | 2 | 22.2% | 57.5 points | fragile_fewer_than_10_clusters |

The abandon baseline is saturated at 100%, so its observed variance is zero and an empirical MDE cannot be estimated. With only four abandon and two escalate family clusters, exact two-sided family sign-randomization cannot reach p < 0.05 regardless of effect size. No action stratum can support a 10-point-effect claim.
