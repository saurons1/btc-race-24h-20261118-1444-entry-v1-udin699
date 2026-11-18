"""BTC race bot v1: shallow-dip recovery swing, long only.

The idea, measured on this race's frozen 24h dev window (1,440 one-minute
cbBTC bars, 2026-11-18 14:44 UTC back to 2026-11-17 14:44 UTC):

- The window is a slow -2.81% grind down ($65,083 -> $63,261, total range
  only 324 bps). It barely mean-reverts: from the 240-bar low the median
  recovery over the next 240 bars is 6 bps and the best is 95 bps, so no
  deep-dip filter can work here. The previous race's v2 bot (buy 260 bps
  below the 405-bar high) scores -$0.83 on this window — one trade, fails
  the dev gate. A shallower, shorter filter is needed.
- The window holds exactly two clean +1% recoveries. This bot buys each
  one: entry when the close sits at least 1.5% below the highest close of
  the last 240 bars (about 4 hours), spending all cash.
- Exit by selling the whole position when the close is 1.0% above the
  close the entry was decided on, or 2.0% below the highest close seen
  since entry (trailing stop). A 60-bar cooldown after an exit stops the
  bot re-entering at the top right after banking a recovery.
- No new entries once 1,200 bars have been seen (240 bars = 4 hours before
  the window ends). The two winning exits on the dev window took 161 and
  351 bars to reach their target, so a position opened with less than 240
  bars left cannot reach +1% before the replay flattens everything at the
  last close — on the dev window that one late entry alone cost -$3.43.

Measured with an exact replay of the official engine (fee 4 bps, slippage
2 bps, constant-product impact vs bar open depth, fill at next bar's open,
flatten at last close): net PnL +$15.17, 2 round trips, max drawdown 0.60%,
fees $1.61, +$13.55 at 2x fees. The neighbourhood is a plateau, not a
spike: N180-300 / dip 150 / TP 100 all score $14.78-15.17 on the same two
trades. Estimated dev rank ~7-8 (rank 7 $15.90, rank 8 $14.40).

Honest caveat: the edge is two round trips on one 24h window. The second
half of the dev window produces no entry at all (no signal, not a loss),
and the race window is unseen — every entry here is a lottery ticket with
a mechanism, not a proven edge. RSI, fast-drop capitulation, and
short-horizon dip variants were all tested on this window and score worse.
"""

import os
import sys
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

# --- Tuned on the dev window (see module docstring). All thresholds are
# compared in exact integer arithmetic, so the same bars always give the
# same orders: no floats anywhere in the decision path.
LOOKBACK = 240        # bars for the dip reference (highest close, ~4 hours)
DIP_BPS = 150         # buy when close is at least 1.5% below that high
TP_BPS = 100          # sell when close is 1.0% above the entry-decision close
TRAIL_BPS = 200       # sell when close is 2.0% below the peak close since entry
COOLDOWN = 60         # bars to wait after an exit order before the next entry
ENTRY_CUTOFF = 1200   # bars seen after which no NEW entry is opened
MIN_NOTIONAL = 1_000_000  # smallest buy the replay accepts, in quote units ($1)
MAX_SLIPPAGE_BPS = 200

closes = []
# Decreasing deque of indices into closes: its front always holds the index
# of the highest close of the last LOOKBACK bars, maintained in O(1) per bar.
hi_dq = deque()
last_exit_seq = -10**9
peak = None          # highest close since entry; None while flat
entry_close = None   # close the entry was decided on; None while flat


def on_batch(state, batch):
    global last_exit_seq, peak, entry_close
    symbol = state.hello["symbols"][0]["symbol"]
    bar = None
    for b in batch["bars"]:
        if b["symbol"] == symbol:
            bar = b
            break
    if bar is None:
        return []
    close = int(bar["c"])
    closes.append(close)
    idx = len(closes) - 1
    while hi_dq and closes[hi_dq[-1]] <= close:
        hi_dq.pop()
    hi_dq.append(idx)
    while hi_dq and hi_dq[0] <= idx - LOOKBACK:
        hi_dq.popleft()

    if state.warming_up:
        return []

    held = state.positions.get(symbol)
    if held is not None:
        if peak is None or close > peak:
            peak = close
        take_profit = close * 10_000 >= entry_close * (10_000 + TP_BPS)
        trailing_stop = close * 10_000 <= peak * (10_000 - TRAIL_BPS)
        if take_profit or trailing_stop:
            last_exit_seq = state.seq
            peak = None
            entry_close = None
            return [{"side": "sell", "symbol": symbol, "qty": held.qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []

    # Flat: only a fresh entry can fire. The cutoff counts bars seen, so an
    # entry decided on bar index i is blocked exactly when i >= ENTRY_CUTOFF.
    if len(closes) < LOOKBACK:
        return []
    if len(closes) > ENTRY_CUTOFF:
        return []
    if state.seq - last_exit_seq < COOLDOWN:
        return []
    high = closes[hi_dq[0]]
    if close * 10_000 > high * (10_000 - DIP_BPS):
        return []
    entry_close = close
    amount = state.cash
    room = state.weight_room(symbol)
    if room < amount:
        amount = room
    if amount < MIN_NOTIONAL:
        # Too little cash left for a fill the replay accepts: never send a
        # buy the engine would reject outright (below_min_notional).
        entry_close = None
        return []
    return [{"side": "buy", "symbol": symbol, "notional_quote_units": amount,
             "max_slippage_bps": MAX_SLIPPAGE_BPS}]


makefun_bars.run(on_batch)
