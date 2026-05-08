# QQQ Day Trade Agent Design

## Goal

Add a new Python agent at `scripts/qqq_dt_agent.py` that monitors only `QQQ`, detects the backtest buy signal from `scripts/backtest/backtest_qqq.py`, enters a paper trade when the signal appears, and exits based on fixed intraday risk rules. Add a matching GitHub Actions workflow at `.github/workflows/day_trade_agent.yml` that follows the existing sniper-step pattern used by `.github/workflows/trading_agent.yml` but runs `scripts/qqq_dt_agent.py`.

## Scope

In scope:
- Single-symbol monitoring for `QQQ` only
- Reuse of the backtest buy-signal formula
- Entry and exit logic for one intraday position at a time
- Market-close safety exit
- A new GitHub Actions workflow mirroring the existing trade job structure
- Targeted automated tests for the new agent logic and workflow-adjacent config surface

Out of scope:
- Multi-symbol watchlists
- AI/news filtering
- Changes to the existing `trading_agent.py` strategy
- Backtest refactoring beyond small helper reuse if needed

## Approach Options

### Option 1: Reuse `trading_agent.py` directly and branch behavior with flags

Pros:
- Minimal number of files
- Reuses existing Alpaca bootstrap and scheduling patterns

Cons:
- Mixes two different strategies into one runtime path
- Increases risk of regressions in the existing trading agent
- Makes tests and workflow behavior harder to isolate

### Option 2: Create a separate `qqq_dt_agent.py` that borrows small shared patterns

Pros:
- Clean separation between the existing low-float sniper logic and the new QQQ day-trade logic
- Easier to test and operate independently
- Lowest risk to current production behavior

Cons:
- Some duplication of bootstrap/runtime logic unless helpers are extracted carefully

### Option 3: Extract a shared framework module first, then build both agents on top

Pros:
- Best long-term structure if multiple strategies are expected
- Reduces duplication across agents

Cons:
- Higher upfront scope
- Unnecessary for the requested change unless a second follow-up strategy is imminent

## Recommendation

Use Option 2. Create `scripts/qqq_dt_agent.py` as a dedicated agent and reuse only the stable runtime/config conventions already present in `scripts/trading_agent.py` and `scripts/trading_agent_env.py`. This keeps the new day-trade strategy isolated while preserving the same GitHub Actions operational model.

## Runtime Design

### Market data and schedule

- Monitor only `QQQ`
- Use Alpaca minute bars and resample to 5-minute candles, matching the backtest signal basis
- Poll on a loop similar to `trading_agent.py`
- Restrict operation to an intraday execution window appropriate for the new day-trade workflow
- Maintain a single in-memory position state for `QQQ`

### Buy signal

The buy signal should match the backtest logic from `scripts/backtest/backtest_qqq.py`:
- `MACDh_12_26_9` is rising while still negative
- `close < BBM_20_2.0_2.0`
- `J` turns up from below `25`
- `RSI_14 < 45`
- current volume is greater than prior candle volume

### Position handling

Only one QQQ position may be active at a time.

On entry:
- submit a market buy order
- store entry price, quantity, and entry timestamp/bar index

On each subsequent loop while in position:
- compute unrealized return from entry
- compute elapsed holding time
- evaluate exits in priority order

## Exit Rules

### Take profit

- If unrealized return reaches or exceeds `20%` within 60 minutes of entry, exit immediately

### Stop loss

- If unrealized return reaches or falls below `-0.2%`, exit immediately

### Forced exit

Exit immediately if either of these happens before other conditions trigger:
- holding time reaches 60 minutes / 12 five-minute bars
- current time is within 5 minutes of market close

## Error Handling

- Fail fast with a clear error if Alpaca credentials are missing
- If no bars are returned, continue polling rather than crashing
- If indicator columns cannot be computed because the frame is too short, skip until enough data exists
- Log order submission failures and continue safely without corrupting in-memory position state

## Workflow Design

Create `.github/workflows/day_trade_agent.yml` with:
- same `schedule` and `workflow_dispatch` pattern as the existing trading workflow unless a narrower execution window is needed during implementation
- dependency installation via `backend/requirements.txt`
- secret validation step for `FMP_API_KEY`, `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`
- `Run Sniper Agent`-style step that sets env vars and runs `python -u scripts/qqq_dt_agent.py`

The workflow should stay isolated from `trading_agent.yml` rather than modifying the existing workflow.

## Testing Strategy

Add focused unit tests for:
- signal generation from a prepared DataFrame
- exit decisions for `20%` take profit, `-0.2%` stop loss, 60-minute timeout, and near-close forced exit
- bootstrap/config behavior when Alpaca env vars are missing

Prefer small pure helpers in `qqq_dt_agent.py` so signal and exit logic can be tested without hitting Alpaca.

## Open Decisions Resolved

- Monitor only `QQQ`
- Do not monitor `SPY`
- Use a dedicated new workflow file
- Keep implementation separate from `trading_agent.py`

## Implementation Notes

- Reuse `load_runtime_config()` if practical, but avoid introducing unrelated dependencies on FMP data if the new agent does not need them at runtime
- Preserve existing repo style and logging tone
- Keep the first implementation minimal and strategy-specific
