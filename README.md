# Sentinel Capital Engine

Automated equities/ETF trading system deployed on Railway using Alpaca.

![Status](https://img.shields.io/badge/status-active-brightgreen)
![Deploy](https://img.shields.io/badge/deploy-railway-purple)
![Strategy](https://img.shields.io/badge/style-risk_managed-blue)

## What it does
- Trades a curated basket (ex: SPY, QQQ, XLE)
- Uses risk limits (cash reserve, daily budget, daily stop)
- Avoids overtrading by throttling entries and tightening signals
- Sleeps when market is closed

## Risk Controls (Built-In)
- Cash reserve (example: uses only 70–80% of equity)
- Daily spend cap (example: $90 max notional per day)
- Daily profit target (stops trading when reached)
- Safety checks to prevent unsafe order sizes