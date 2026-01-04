# EML Sentinel Capital Engine

A risk-managed automated trading engine for equities & ETFs, deployed 24/7 on Railway and executed via Alpaca.

**Mission:** Build a disciplined, rules-based system that prioritizes capital protection, repeatability, and controlled exposure — without emotional trading.

![Status](https://img.shields.io/badge/status-active-brightgreen)
![Deploy](https://img.shields.io/badge/deploy-railway-purple)
![Execution](https://img.shields.io/badge/execution-alpaca-black)
![Style](https://img.shields.io/badge/style-risk_managed-blue)

---

## What it does
- Trades a curated basket of liquid symbols (example: **SPY, QQQ, XLE**)
- Runs as a persistent **worker service** (no browser needed)
- Checks market state and **sleeps when the market is closed**
- Executes only when rules align — focused on consistency over hype

## Risk Controls (Built In)
- **Exposure control:** uses a defined portion of equity (keeps cash reserve)
- **Daily budget cap:** prevents overspending/overtrading
- **Daily stop logic:** can pause trading after hitting profit target or risk limit
- **Order safety checks:** avoids unsafe notional sizing when buying power is low

## Who it's for
- Traders who want **automation with discipline**
- Builders who want a real, deployable system — not a "signal group"
- Operators who care about **risk, logs, and reliability**

## Deployment
This system runs on **Railway** as a persistent worker.
- Push updates to `main` on GitHub
- Railway auto-builds and redeploys (Auto-Deploy)
- Monitor runtime in Railway → Service → Logs

## Important Note
This is **not financial advice**. Automated trading involves risk, including loss of capital. Always test in paper trading before running live.