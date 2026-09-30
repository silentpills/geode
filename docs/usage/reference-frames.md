# Saved plate-fixed reference frames

`FixPlate.py` estimates an Euler vector from fitted horizontal reference (HREF)
station velocities. With `-save`, it stores corrected coordinates together with
the fit that produced them. This is a provenance record for a saved stack;
GAMIT processing configuration management remains separate.

```bash
pixi run --locked python -m com.FixPlate regional \
  -include net.aaaa net.bbbb net.cccc \
  -vref net.dddd 1.2 net.eeee -0.4 \
  -save regional_fixed -save_filter net.all
```

Replace the example stations and velocities with the intended reference set.
HREF stations need fitted polynomial velocities in `etms`. VREF values are
external local-up velocities in **mm/year**, paired with each station. Quoted
rows such as `-vref 'net.dddd 1.2'`, or a file containing station/velocity rows,
are also accepted. Every requested VREF station must have a fitted velocity.
`-save_filter` limits output stations; it does not select the HREF/VREF fit.
The default saves all stations in the input stack.

For PPP, use `-ppp`. The positional stack name is ignored, and output selection
comes from raw `ppp_soln` stations:

```bash
pixi run --locked python -m com.FixPlate ignored -ppp \
  -include net.aaaa net.bbbb net.cccc \
  -save ppp_fixed -save_filter net.aaaa net.bbbb
```

PPP input must have exactly one reference-frame solution per selected
station/day. Ambiguous days are rejected. A corrected PPP stack is saved
output: the GAMIT ETM loaders reject it. Use PPP ETM loading on `ppp_soln` to
fit the original PPP series; fitting saved corrected PPP stacks is not yet
implemented.

## Stored provenance

Migration `0038_reference_frames` and processing startup share the additive
`geode/sql/reference_frames_v1.sql` migration. Fresh processing-only SQL
installation through `database/schema.sql` includes it. Existing scientific
rows, composite primary keys, and public API IDs are retained.

| Record | Meaning |
| --- | --- |
| `reference_frames.frame_name` / `engine` | Physical stack name, globally owned by GAMIT or PPP |
| `project` / `source_projects` | Dominant source project and counts of stored station-days for every project; equal counts choose the lexical first identifier. PPP uses `gpspace`. |
| `source_stack` | Original GAMIT stack name; null for raw PPP |
| `fixed_plate` | Most frequent non-null `stations.plate` among HREF stations; lexical tie-breaking; null when unknown |
| `euler_pole` | ECEF Cartesian rotation vector **[X, Y, Z] in mas/year**, not latitude/longitude/rate |
| `euler_pole_stations` | Sorted HREF station identifiers used in the fit |
| `translation_rate` | Optional three fitted VREF translation parameters in **m/year**, retaining FixPlate's existing design convention |
| `first_epoch` / `last_epoch` | Earliest and latest saved coordinate dates |
| `reference_frame_constraints` | VREF station constraints as ECEF **[vx, vy, vz] in m/year**, converted from external local-up velocity with north/east set to zero |

`gamit_projects` catalogs identifiers only. It does not infer historical
processing settings. Saved GAMIT rows retain each epoch's original `Project`,
even when a station spans several projects. PPP rows have a null `Project` and
an explicit `ppp_reference_frame` foreign key to the original PPP station/day.

## Replacement and append

Saving replaces a same-engine destination unless `-preserve` is given. Use a
different name from the input GAMIT stack. ETM calculations finish in a temporary
disk spool before a single transaction writes coordinates, frame metadata, and
constraints. A failed fit or save leaves the previous destination intact.
Frame and surviving constraint API IDs remain stable on replacement.

`-preserve` skips already saved stations and adds newly selected stations only
when the saved engine, input stack, fixed plate, Euler vector, HREF set,
translation, and VREF constraints match. It verifies retained source identities
and recomputes counts and date coverage over the whole saved stack. Legacy
stacks without fit provenance and stacks made with a different fit must be
rebuilt. This option does not add new days to an existing station.

Deleting or renaming new metadata cannot cascade into scientific rows. Every
GAMIT project mentioned by a saved frame is protected against catalog deletion
or rename, including projects that are not dominant. The existing GAMIT source
foreign key and its deletion/invalidation behavior are unchanged. Provenance
describes creation or the last successful save; subsequent source changes need
review and rebuilding. PPP source deletion is restricted while corrected rows
refer to it. This feature adds persistence and models; it does not add a web
frame-management interface.
