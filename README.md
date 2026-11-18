# BTC race bot v1 — btc-race-24h-20261118-1444

Shallow-dip recovery swing, long only, Python 3.13 stdlib + vendored SDK.

- Entry: close >= 1.5% below the highest close of the last 240 bars, all cash.
- Exit: +1.0% vs the entry-decision close, or -2.0% trailing stop vs the
  peak since entry. 60-bar cooldown after an exit.
- No new entries after 1,200 bars seen (a position opened late cannot reach
  its target before the replay flattens at the last close).
- Measured on the frozen dev window with an exact replay of the official
  engine: net PnL +$15.17, 2 round trips, max drawdown 0.60%, +$13.55 at
  2x fees. Estimated dev rank ~7-8.

See the module docstring in `main.py` for the full measurement notes and
the honest caveat (the edge is two round trips on one 24h window).
