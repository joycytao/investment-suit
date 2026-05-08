# Real Options Chain Backtest Design

## Goal

Upgrade the current intraday options strategy from proxy pricing into a real options-chain backtest for `QQQ` and `SPY`, while introducing shared modules that can later be reused by the paper-trading options runner.

The implementation must keep backtest and paper execution concerns separate, but both paths must share the same:

- underlying signal logic
- option contract selection rules
- option execution pricing semantics

## Scope

In scope:

- Real options-chain backtest for `QQQ` and `SPY`
- Shared module layer for contract selection and execution pricing
- Alpaca as the primary data source
- Intraday backtest using option bars for state progression
- Quote-aware execution approximation using `entry=ask` and `exit=bid`
- Deterministic contract selection using fixed DTE and Delta windows
- Liquidity filters using volume, open interest, and spread percent
- Focused tests for selector and execution-pricing behavior
- Minimal integration update so the existing options runner can later consume the same selector

Out of scope for this phase:

- Live options order submission
- Multi-leg strategies
- Alternative data providers unless Alpaca lacks required data for a specific call path
- Large strategy rewrites to the underlying intraday signal model
- Full workflow expansion beyond the existing options job

## Current State

The repository currently has:

- [scripts/backtest/backtest_intraday_options.py](scripts/backtest/backtest_intraday_options.py): proxy backtest using stock bars, proxy IV/HV, and Black-Scholes-style estimation
- [scripts/day_trade_options.py](scripts/day_trade_options.py): signal-mode runner with contract symbol formatting but no real option chain selection
- [backend/options_pricing.py](backend/options_pricing.py): Black-Scholes and Greeks helpers

The current limitation is not strategy logic. The limitation is the absence of a real option chain data layer and a shared contract selector used consistently by both backtest and runner code.

## Chosen Approach

Use a shared two-layer design:

1. Shared domain modules for option market data, contract selection, and execution pricing.
2. Separate orchestration layers for historical backtest and paper/live runner.

This is preferred over directly extending the existing backtest script because the contract selector must become the single source of truth for both historical evaluation and live selection.

## Architecture

### 1. Underlying Signal Engine

Responsibility:

- Produce long, short, or flat signals using underlying stock minute bars only.

Plan:

- Preserve the existing signal construction in [scripts/backtest/backtest_intraday_options.py](scripts/backtest/backtest_intraday_options.py) for the first implementation.
- Extract or wrap only what is necessary so signal generation can be reused without duplicating strategy logic.

### 2. Option Market Data Module

Proposed file:

- `backend/options_market_data.py`

Responsibility:

- Fetch Alpaca option chain snapshots at a given signal time.
- Fetch per-contract option bars after entry.
- Fetch quote data needed for conservative execution approximation.

Rules:

- Alpaca is the primary source.
- If a quote is unavailable at the exact timestamp, the module may use a short forward fill window.
- If quote data remains unavailable after the allowed fallback window, the trade is skipped.
- The module must not silently fall back to theoretical pricing for contracts that are intended to be traded from real chain data.

### 3. Option Contract Selector

Proposed file:

- `backend/options_contract_selector.py`

Responsibility:

- Convert a signal time and direction into exactly one chosen contract, or no trade.

Phase 1 selection rules:

- Symbols: `QQQ`, `SPY`
- DTE window: `1-5`
- Delta window: `0.40-0.60`
- Liquidity constraints:
  - `volume >= 100`
  - `open_interest >= 500`
  - `spread_pct <= 8%`

Tie-breaking order:

1. Delta closest to `0.50`
2. Smaller `spread_pct`
3. Larger `volume`

The selector must be deterministic so backtest and paper mode choose the same contract given the same market snapshot.

### 4. Option Execution Pricer

Proposed file:

- `backend/options_execution_pricer.py`

Responsibility:

- Translate contract state and quote data into conservative executable prices.

Phase 1 pricing semantics:

- Entry price uses `ask`
- Exit price uses `bid`

Fallback behavior:

- Use a short forward fill of recent quotes when exact timestamps do not align.
- If no acceptable quote exists, skip the trade rather than using Black-Scholes or mid-price substitution.

This keeps the first version biased toward realism rather than optimistic trade count.

### 5. Options Backtest Engine

Primary integration surface:

- [scripts/backtest/backtest_intraday_options.py](scripts/backtest/backtest_intraday_options.py)

Responsibility:

- Drive the historical simulation.

Flow:

1. Build underlying signal frame from stock minute bars.
2. At each signal timestamp, fetch the option chain snapshot.
3. Use the shared selector to choose a contract.
4. Fetch option bars and quote data for that contract.
5. Simulate fills with the shared execution pricer.
6. Apply existing option risk rules:
   - hard stop
   - partial take profit
   - full take profit
   - trend-break exit
   - force-close exit
7. Produce trade log and metrics.

Only the contract and execution source changes in phase 1. The strategy's higher-level risk logic remains intact unless real data reveals a local defect.

### 6. Paper Runner Integration

Primary integration surface:

- [scripts/day_trade_options.py](scripts/day_trade_options.py)

Responsibility:

- Continue to orchestrate runtime polling and position state.

Phase 1 change:

- Replace internal contract planning assumptions with calls into the shared selector.

Non-goal for this phase:

- Submit real options paper orders. This design prepares that integration but does not require it in this step.

## Data Flow

### Backtest Flow

`stock minute bars`
-> `underlying_signal_engine`
-> `option chain snapshot at signal time`
-> `option_contract_selector`
-> `chosen contract`
-> `option bars + quote stream`
-> `option_execution_pricer`
-> `options_backtest_engine`
-> `trades + metrics`

### Runner Flow

`stock minute bars`
-> `underlying_signal_engine`
-> `live option chain snapshot`
-> `option_contract_selector`
-> `chosen contract`
-> `runner position state / future paper order flow`

## Error Handling

- Missing Alpaca credentials: fail fast with a clear runtime error.
- Missing option chain snapshot for a signal timestamp: skip the trade.
- No contract passing DTE/Delta/liquidity filters: skip the trade.
- Missing usable quote after short forward-fill fallback: skip the trade.
- Missing option bars after a contract is selected: close the simulation path for that trade and record a skipped trade reason if needed.

Skipping is preferred over optimistic imputation.

## Testing Strategy

Add focused tests before implementation for the new shared modules.

Required behavior coverage:

1. Contract selector accepts only contracts inside `1-5 DTE` and `0.40-0.60 Delta` windows.
2. Contract selector rejects contracts that fail volume, open interest, or spread thresholds.
3. Contract selector tie-breaks by Delta closeness, then spread, then volume.
4. Execution pricer uses `ask` for entry.
5. Execution pricer uses `bid` for exit.
6. Execution pricer skips the trade when required quote data is unavailable after fallback.
7. Backtest integration still supports existing option exit rules when real contract and quote inputs are injected.

## Implementation Sequence

1. Add selector tests and execution-pricer tests.
2. Implement `backend/options_contract_selector.py`.
3. Implement `backend/options_execution_pricer.py`.
4. Implement `backend/options_market_data.py` with Alpaca-backed fetch helpers.
5. Integrate shared modules into [scripts/backtest/backtest_intraday_options.py](scripts/backtest/backtest_intraday_options.py).
6. Run focused backtest tests.
7. Update [scripts/day_trade_options.py](scripts/day_trade_options.py) to call the shared selector.
8. Run focused runner tests.

## Risks

- Alpaca option-history coverage or field availability may differ from assumed timestamps and quote resolution.
- Historical Delta may not always be directly available in the same shape as snapshot data. If that happens, Delta calculation may need a local fallback using quote/underlying inputs, but only after confirming the exact Alpaca response shape.
- Conservative `ask`/`bid` fills and liquidity thresholds may reduce trade count materially. That is acceptable because credibility is preferred over inflated performance.

## Success Criteria

Phase 1 is successful when:

- `QQQ` and `SPY` backtests run on real option-chain-backed contract selection.
- Selected contracts follow the agreed DTE, Delta, and liquidity rules.
- Entry and exit prices use conservative quote-aware semantics.
- Shared selector logic is no longer duplicated between backtest and runner paths.
- Focused tests for selector and execution pricing pass.