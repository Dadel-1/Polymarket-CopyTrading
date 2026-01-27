## Polymarket Copy Trading Bot

Python bot that **copies trades from a target Polymarket trader** to your own wallet, using **proportional position sizing** and the official `py-clob-client` CLOB SDK ([example reference](https://github.com/Polymarket/py-clob-client/blob/main/examples/market_buy_order.py)).

The bot:
- Watches a target address's activity via Polymarket's data API.
- Tracks both wallets' positions and USDC balance.
- Places **market orders** on the CLOB with proportional sizing.
- Mirrors on-chain actions like **split / merge / redeem** via a blockchain helper client.

---

## Requirements

- Python **3.10+**
- A funded **Polymarket proxy wallet** (copier) with USDC on Polygon
- Access to a **target trader address** to copy
- Node provider URL for Polygon (e.g. Alchemy, Infura, or public RPC)

Python dependencies are listed in `requirements.txt`, run this command to install them:

```bash
pip install -r requirements.txt
```

Key libraries:
- **py-clob-client** – Polymarket CLOB SDK
- **py-builder-relayer-client** – for relayer / proxy interactions
- **web3** – on‑chain balance and token operations
- **aiohttp**, **python-dotenv**, **python-dateutil**

## Configuration

All configuration is done via environment variables, through a `.env` file. You can copy the file `.env.example` into a `.env` file and edit the values.

### Core keys / wallet

- **`POLYMARKET_PRIVATE_KEY`** – Private key used to sign orders and transactions for your **copier** wallet. If you connected to Polymarket with a Web3 wallet (Metamask, Phantom...), then you should input the private key of this wallet.
- **`POLYMARKET_PROXY_ADDRESS`** – Copier proxy wallet address. This the Polymarket address shown on your profile when you click "Copy Address".

### CLOB client

- **`CLOB_HOST`** – **Do not edit** – CLOB API host (default `https://clob.polymarket.com`).
- **`CHAIN_ID`** – **Do not edit** – Polygon chain ID (default `137`).
- **`SIGNATURE_TYPE`** – Signature type for `ClobClient` (0=EOA/MetaMask, 1=Email/Magic, 2=Browser wallet). Edit this depending on your sign up method on Polymarket.

### Relayer / builder

- **`RELAYER_URL`** – **Do not edit** – Relayer URL (default `https://relayer-v2.polymarket.com/`).
- **`BUILDER_API_KEY`**, **`BUILDER_SECRET`**, **`BUILDER_PASS_PHRASE`** – Credentials for the builder/relayer client. Create new Builder Keys in your builder settings (https://polymarket.com/settings?tab=builder).

### Bot behaviour

- **`TARGET_TRADER_ADDRESS`** – **Address to copy** (target). Address obtained by clicking on the "Copy Address" button on someone's profile.
- **`POLL_INTERVAL`** – Seconds between activity polls (default `1`).
- **`RPC_URL`** – Polygon RPC endpoint used to track wallet USDC cash (default `https://polygon-rpc.com`).

### Logging

- **`LOG_LEVEL`** – e.g. `INFO`, `DEBUG` (default `INFO`).
- **`LOG_FILE`** – optional path to a log file (default `bot.log`).
- **`HEARTBEAT_INTERVAL`** Seconds between Watcher heartbeats (signals to show the bot is still alive)

## Running the Bot

1. **Clone** the repo and install dependencies:

```bash
git clone <this-repo-url>
cd Polymarket-CopyTrading
pip install -r requirements.txt
```

2. **Copy `.env.example` into a `.env` file** and update the variables as explained above.

3. **Run**:

```bash
python main.py
```

The bot will:
- Start the watcher (fetching target activities).
- Start the copier (processing and mirroring actions).
- Log activity and statistics to stdout and the optional log file.

## How It Works

- `main.py` – entrypoint. Creates a `CopyTradingBot` with:
  - `ActivityWatcher` – pulls recent activity for `TARGET_TRADER_ADDRESS` and pushes it to an asyncio queue.
  - `TradeCopier` – consumes queued activities and creates proportional copy trades.
- `wallet_tracker.py` – tracks:
  - Positions per `conditionId` / `tokenId`
  - USDC balance via on‑chain calls
- `trade_copier.py`:
  - Builds a **trading ratio** between copier and target per market:
    - ratio = copier_position / target_position
  - For **BUY** trades:
    - Computes proportional **USDC** amount via `_get_proportional_amount(usdcSize, "USDC", "USDC")`.
    - Places a **market order** with `MarketOrderArgs` and `OrderType.FOK`, using `ClobClient.create_market_order` and `ClobClient.post_order`.
  - For **SELL** trades:
    - Detects if the trader is exiting the full position and mirrors behaviour based on copier's holdings.
  - For **SPLIT / MERGE / REDEEM**:
    - Calls into `BlockchainClient` to build and execute the corresponding on‑chain transactions while updating local positions.

## Safety Notes

- This bot **spends real funds** from your copier wallet. Start with **small balances** and monitor behaviour closely.
- Ensure your environment and `.env` file are kept secure; they contain sensitive keys.
- Review `trade_copier.py` sizing logic before running in production.
