"""
Configuration file for the Polymarket Copy Trading Bot
"""
import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

PRIVATE_KEY: Optional[str] = os.getenv("POLYMARKET_PRIVATE_KEY", None)

# CLOB Client Configuration
CLOB_HOST: str = os.getenv("CLOB_HOST", "https://clob.polymarket.com")
CHAIN_ID: int = int(os.getenv("CHAIN_ID", "137"))  # Polygon mainnet
SIGNATURE_TYPE: int = int(os.getenv("SIGNATURE_TYPE", "2"))  # 0=EOA, 1=Email/Magic, 2=Browser proxy
POLYMARKET_PROXY_ADDRESS: Optional[str] = os.getenv("POLYMARKET_PROXY_ADDRESS", None)  # Required for proxy wallets

# Relayer Client Configuration
RELAYER_URL: str = os.getenv("RELAYER_URL", "https://relayer-v2.polymarket.com/")
BUILDER_API_KEY: str = os.getenv("BUILDER_API_KEY", None)
BUILDER_SECRET: str = os.getenv("BUILDER_SECRET", None)
BUILDER_PASS_PHRASE = os.getenv("BUILDER_PASS_PHRASE", None)

# Target trader to copy
TARGET_TRADER_ADDRESS: str = os.getenv("TARGET_TRADER_ADDRESS", None)

# Bot Configuration
POLL_INTERVAL: float = float(os.getenv("POLL_INTERVAL", 1))  # seconds
RPC_URL: str = os.getenv("RPC_URL", "https://polygon-rpc.com")

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: Optional[str] = os.getenv("LOG_FILE", "bot.log")
HEARTBEAT_INTERVAL: float = float(os.getenv("HEARTBEAT_INTERVAL", 60)) # seconds

