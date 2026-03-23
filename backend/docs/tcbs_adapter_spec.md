# TCBS Adapter Specification & Observability Strategy

## A. Evaluation of Current TCBS Integration
- **Working**: Basic order placement and protocol adherence.
- **Improvements**: Decoupled TCBS-specific payloads from business logic via `OrderRequestNormalized`. Added typed exceptions for precise error handling.
- **WebSocket**: Implemented exponential backoff and heartbeat logic to prevent app crashes.

## B. Internal Architecture
The `TcbsBrokerAdapter` acts as a **bridge** between the standardized `BrokerInterface` and the raw TCBS REST/WS endpoints.
1. **Request Normalizer**: Converts `TradeIntent` or `OrderRequest` into TCBS JSON.
2. **Response Normalizer**: Converts raw TCBS responses into `OrderReceipt` or raises `RejectError`.
3. **Event Streamer**: Converts TCBS WebSocket messages into `FillEvent` or `OrderStateNormalized`.

## E. TODO Mapping Table (TCBS Fields)
| TCBS Field | Standard Model | Description | Status |
| :--- | :--- | :--- | :--- |
| `side` | `TradeAction` | 'B' (Buy), 'S' (Sell) | ✅ Confirmed |
| `orderType` | `OrderType` | 'LO' (Limit), 'MTL' (Market), 'ATC' | [ ] To Map |
| `price` | `price` | Price for Limit orders | ✅ Confirmed |
| `volume` | `qty` | Number of contracts/shares | ✅ Confirmed |
| `account` | `None` | TCBS Account No (from settings) | ✅ Confirmed |
| `rc` | `Exceptions` | Response Code (0 = OK) | ✅ Confirmed |
| `status` | `OrderStatus` | Mapping 'FULLY_FILLED', 'REJECTED', etc | [ ] To Verify |

## F. Logging & Telemetry Strategy
- **Audit Logging**: Every order request has a unique `trace_id` logged at `INFO` level.
- **Exception Tracking**: Detailed stack traces for `BrokerError` but clean, user-friendly alerts for Telegram.
- **Metrics (TODO)**: Track latency of `place_order` and count of `NetworkError` events.
- **Telegram Alerts**:
  - `🔄 SYSTEM`: Reconnect events with attempt count.
  - `🚫 REJECT`: Detailed broker rejection messages.
  - `🛑 AUTH`: Failures in login/TOTP flow.

## G. Test Checklist
- [ ] Mock `RateLimitError` and verify backoff.
- [ ] Mock `RejectError` (e.g., Code 403) and verify Telegram alert.
- [ ] Verify `amend_order` in paper mode returns `True`.
- [ ] Test WebSocket reconnect loop (simulate 3 failures).

## H. Go-Live Checklist
- [ ] Update `tcbs_account_no` in `.env`.
- [ ] Verify TOTP secret works via manual login once.
- [ ] Check symbol whitelist for VN30F futures.
- [ ] Set `LIVE_TRADING=true` ONLY after paper mode pass.
