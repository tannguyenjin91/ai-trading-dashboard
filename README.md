# 🇻🇳 VN AI Trader

An autonomous AI trading system for Vietnamese stock markets (equities + VN30F derivatives).

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, asyncio |
| AI Agent | Google Gemini / Anthropic Claude |
| Data Cache | Redis 7 |
| Database | SQLite (audit log) |
| Broker | TCBS API |
| Frontend | React 18 + TypeScript + TailwindCSS |
| Monitoring | Telegram bot |
| Container | Docker Compose |

## Quick Start

```bash
# 1. Copy environment file
cp .env.example .env
# Fill in your API keys in .env

# 2. Start infrastructure
docker-compose up redis -d

# 3. Start backend (development)
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 4. Start frontend (development)
cd frontend
npm install
npm run dev
```

## Phases

- **Phase 1** ✅ Foundation — project scaffold, Docker, health endpoint
- **Phase 2** 🔜 Data Layer — market data feed, indicators engine
- **Phase 3** 🔜 Agent Core — AI loop, strategies, decision gate
- **Phase 4** 🔜 TCBS Execution — order routing, position management
- **Phase 5** 🔜 Frontend — full dashboard, charts, kill switch
- **Phase 6** 🔜 Integration & Testing — end-to-end, performance

## Safety

This system includes multiple safety mechanisms:
- **Decision Gate** — 9 hard blocks before any order is placed
- **Circuit Breakers** — automatic position reduction at drawdown thresholds
- **Kill Switch** — emergency close all positions (UI + API)
- **Paper Mode** — TCBS_PAPER_MODE=true for dry-run testing

> ⚠️ Trading carries risk. Always test in paper mode first.
