# Polymarket CopyTrading

Python tooling for monitoring a target Polymarket wallet and optionally copying trades from a separate wallet.

> ⚠️ Trading bots can move real funds. Start with read-only monitoring or a dry run before enabling live order placement. Never paste seed phrases, exchange passwords, or private keys into prompts.

## Safer local setup

```bash
git clone https://github.com/Dadel-1/Polymarket-CopyTrading.git
cd Polymarket-CopyTrading
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` locally. Do not commit `.env`.

## Configuration

The bot reads settings from environment variables loaded by `python-dotenv`.

Important variables:

- `TARGET_TRADER_ADDRESS` — public wallet address to monitor/copy.
- `POLYMARKET_PRIVATE_KEY` — signing key for the copier wallet. Keep this secret.
- `POLYMARKET_PROXY_ADDRESS` — Polymarket proxy wallet address when using proxy signatures.
- `BUILDER_API_KEY`, `BUILDER_SECRET`, `BUILDER_PASS_PHRASE` — builder/relayer credentials when needed.
- `POLL_INTERVAL` — seconds between checks.
- `RPC_URL` — Polygon RPC endpoint.

## Safety checklist before live trading

- Use a new wallet with limited funds.
- Confirm whether the code path is read-only or places orders.
- Start with the smallest possible trade size.
- Keep private keys in a secret manager or local `.env` file that is never committed.
- Do not enter Polymarket passwords, seed phrases, or private keys into untrusted prompts or third-party downloads.
- Review logs before leaving the bot unattended.

## Running

After configuring `.env`, run:

```bash
python main.py
```

## Notes

This repository includes example env names and helper modules for Polymarket CLOB/relayer integration. Verify current Polymarket API requirements before enabling live copying, because authentication and proxy wallet rules can change.
