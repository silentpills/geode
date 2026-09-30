# S-score values and earthquake masks

`com.S-score` exports earthquake masks and can report values for stations in a text
file. Each station row contains its name, latitude, and longitude in decimal
degrees, separated by whitespace or commas. Extra columns, blank lines, and
comments beginning with `#` are ignored. Latitude must be between -90 and 90;
longitude must be between -180 and 180. Invalid rows are reported and skipped.

```text
# station latitude longitude
net.aaaa -34.60 -58.38
net.bbbb,-33.45,-70.67
```

```bash
pixi run --locked python -m com.S-score us20003k7a -scores stations.txt -post
```

The command uses the configured earthquake database and writes the event's KMZ
as usual. `-scores` prints both coseismic and postseismic classifications and
values; `-post` controls inclusion of the postseismic mask in the KMZ.

The output identifies the score level, quantity, and units before its table.
`c_mask` and `p_mask` are the existing classifications (0 or 1). `c_value` and
`p_value` are sampled at the nearest point in their respective mask grids:

| Focal mechanism | Quantity | Units | Meaning |
| --- | --- | --- | --- |
| Unavailable (level 1) | `isotropic_s_score` | dimensionless | `0.5261 × magnitude − log10(distance_km) − 1.1478`; postseismic adds `log10(1.5)` |
| Available (level 2) | `rescaled_okada_mean_margin` | m | Mean modeled displacement magnitude over the nodal planes, minus the 0.001 m mask threshold |

The level 1 formula uses kilometres. Its positive region extends to the
coseismic radius; the postseismic radius is 1.5 times larger. At zero distance
the logarithmic score is positive infinity. Grid sampling means reported values
can differ slightly from evaluating the formula at the exact station location.

Level 2 values describe the Okada field on the **rescaled mask grid**. They are
not physical displacement predictions at the station, and they are not
dimensionless level 1 scores. The postseismic field uses spatial scaling of 1.5;
it is not a separate physical postseismic displacement model.

Use the mask columns for classification. A level 2 mask includes a point if any
nodal plane reaches the threshold, while its numerical margin uses the mean of
the planes. A negative mean margin can therefore accompany a mask of 1. The
existing classification rules and ETM scientific defaults are unchanged.

In Python, `Score.score_values(lat, lon)` returns
`(c_mask, p_mask, c_value, p_value)`. Read `score_level`, `score_quantity`, and
`score_units` on the object to interpret the values. `Score.score(lat, lon)`
continues to return the original two classifications. Scalar coordinates yield
one-element arrays; coordinate arrays yield one result per pair.
