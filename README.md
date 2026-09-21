# AI Trading Bot

AI-assisted paper trading system for Indian markets.

## Current Mode

PAPER TRADING ONLY.

No real BUY or SELL orders are sent to the broker.

## Components

- telemetry_engine.py
- state_manager.py
- main_orchestrator.py
- config.py
- broker_interface.py
- risk_manager.py
- paper_broker.py

## Purpose

The system is designed to combine:

- Market candles
- Technical indicators
- Price action
- AI-assisted analysis
- Risk controls
- Position management
- Paper order simulation

## Safety

Live trading is disabled during development.

API credentials must never be hard-coded or committed to GitHub.

Before enabling live execution, the system must be tested extensively with paper trading and broker-side order reconciliation.
