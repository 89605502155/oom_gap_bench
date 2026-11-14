# Accounting variants (M0–M5)

All variants are implemented by one controller, `oom_gap_bench.methods.Controller`. Each variant is a set of flags of `Method`.

- **M0** – original algorithm: instantaneous used memory, regression over five points, interval by the number of redistributions over five cycles.
- **M1** – an increase of the `oom_kill` counter switches the system to the unstable mode for five cycles.
- **M2** – M1 plus sample recalculation: the volume of the killed process is added to the observation, the point is censored, the lower bound of demand is held for `FLOOR_HOLD = 60` s.
- **M3** – the peak over the interval instead of the instantaneous value; a peak at the allocated volume is treated as censored.
- **M4** – M3 with a reserve based on the 0.9 quantile and an interval limit by the time to exhaust the reserve.
- **M5** – M2 with an event agent: an unscheduled point when free memory is below 256 MiB and grows faster than 20 MiB/s.

Defaults: `R = 100` MiB, `THRESH = 10` MiB, `DT_MIN = 1` s, `DT_MAX = 10` s, `WINDOW = 5`.
