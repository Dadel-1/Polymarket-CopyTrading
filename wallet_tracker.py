import json
import asyncio
import logging
import requests
from typing import Dict
from web3 import Web3
from config import RPC_URL
from py_clob_client.order_builder.constants import BUY, SELL
from abi.ERC20_abi import ERC20_ABI

logger = logging.getLogger(__name__)

class WalletTracker:
    """Tracks a wallet's positions and cash"""

    API_BASE_URL = "https://data-api.polymarket.com"
    USDC_ADDRESS = Web3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")

    def __init__(self, address: str):
        self.address = Web3.to_checksum_address(address)
        self.positions: Dict[str, Dict[str, float]] = {}
        self.balance: int = 0 # USDC balance
        self.w3 = Web3(Web3.HTTPProvider(RPC_URL))
        self.usdc = self.w3.eth.contract(address=self.USDC_ADDRESS, abi=ERC20_ABI)

    async def start(self, refresh_interval: int = 60) -> None:
        await asyncio.gather(
            self._init_positions(),
            self._refresh_balance()
        )
        logger.info(
            "✅ WalletTracker ready for %s (%d pos, %.2f USDC)",
            self.address,
            len(self.positions),
            self.balance,
        )
        # Start background task to refresh cache periodically
        asyncio.create_task(self._periodic_balance_refresh())
        asyncio.create_task(self._periodic_positions_refresh(refresh_interval))

    # Fetch positions of the wallet for the first time
    async def _init_positions(self) -> None:
        await asyncio.to_thread(self.refresh_positions)
    
    def _fetch_all_positions(self, address: str):
        url = f"{self.API_BASE_URL}/positions"
        offset = 0
        limit = 500
        result_length = limit
        result = []
        while result_length == limit:
            params = {
                "sizeThreshold": 0.1, # Min 0.1 share
                "limit": limit,
                "offset": offset,
                "user": address
            }
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                result_length = len(data)
                offset += limit
                result.extend(data)
            else:
                logger.error("Positions API failed (%s): %s", response.status_code, response.text)
                break
        return result
    
    def refresh_positions(self) -> None:
        """Fetch and update positions from API"""
        try:
            data = self._fetch_all_positions(self.address)
            self.positions.clear()
            for pos in data:
                condition_id = pos["conditionId"]
                token_id = pos["asset"]
                size = pos["size"]
                if condition_id not in self.positions:
                    self.positions[condition_id] = {}
                self.positions[condition_id][token_id] = size
        except requests.exceptions.Timeout:
            logger.warning("Positions refresh timed out after 10s")
        except Exception as e:
            logger.error("Unexpected error refreshing positions: %s", e)

    async def _periodic_positions_refresh(self, interval: int) -> None:
        try:
            while True:
                await asyncio.sleep(interval)
                await asyncio.to_thread(self.refresh_positions)
                logger.debug("Refreshed positions for %s: %d markets", self.address, len(self.positions))
        except asyncio.CancelledError:
            pass

    # Fetch USDC balance from blockchain
    async def _refresh_balance(self) -> None:
        def fetch_balance() -> None:
            raw_balance = self.usdc.functions.balanceOf(self.address).call()
            self.balance = raw_balance / (10 ** 6) # USDC has 6 decimals
        try:
            await asyncio.to_thread(fetch_balance)
        except Exception as e:
            logger.error(f"Unexpected error refreshing balance: {e}")

    async def _periodic_balance_refresh(self) -> None:
        """Periodically refresh the balance"""
        try:
            while True:
                await asyncio.sleep(60)  # Refresh every 60 seconds
                await self._refresh_balance()
                logger.debug("Refreshed balance for %s: %.2f USDC", self.address, self.balance)
        except asyncio.CancelledError:
            pass

    def get_position(self, condition_id: str, token_id: str) -> float:
        amount = 0
        if condition_id == "USDC" or token_id == "USDC":
            amount = self.balance 
        else:
            if condition_id in self.positions:
                amount = self.positions[condition_id].get(token_id, 0)
        return amount
    
    def get_mergeable_amount(self, condition_id: str) -> float:
        mergeable = 0
        if condition_id in self.positions:
            token_ids = list(self.positions[condition_id].keys())
            if len(token_ids) == 2:
                tok1 = token_ids[0]
                tok2 = token_ids[1]
                mergeable = min(self.positions[condition_id][tok1], self.positions[condition_id][tok2])
        return mergeable

    def is_redeemable(self, condition_id: str) -> bool:
        redeemable = False
        if condition_id in self.positions:
            redeemable = len(self.positions[condition_id]) > 0
        return redeemable
    
    def _get_tokenIds_from_conditionId(self, condition_id: str):
        url = "https://gamma-api.polymarket.com/markets"
        params = {"condition_ids": condition_id}
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                market = data[0]
                token_ids = market.get('clobTokenIds', [])
                return json.loads(token_ids)
            else:
                logger.error(f"No market found for condition ID: {condition_id}")
                return []
        else:
            logger.error(f"API request failed with status {response.status_code}: {response.text}")
            return []
    
    def _update_position(self, condition_id: str, token_id: str, amount: float, is_add: bool) -> None:
        if condition_id not in self.positions:
            self.positions[condition_id] = {}
        current = self.positions[condition_id].get(token_id, 0)
        new_amount = current + amount if is_add else current - amount
        if new_amount < 0:
            logger.warning(f"Position went negative for {token_id = } in condition {condition_id = }: {new_amount}")
            new_amount = 0
        if new_amount == 0:
            del self.positions[condition_id][token_id]
        else:
            self.positions[condition_id][token_id] = new_amount
        if len(self.positions[condition_id]) == 0:
            del self.positions[condition_id]

    def update_positions(self, type: str, side: str, condition_id: str, token_id: str, size: float) -> None:
        if type == "TRADE":
            if side == BUY:
                self._update_position(condition_id, token_id, size, is_add=True)
            elif side == SELL:
                self._update_position(condition_id, token_id, size, is_add=False)
            else:
                logger.error(f"Unknown trade side in activity: {side}")
        elif type == "SPLIT":
            token_ids = self._get_tokenIds_from_conditionId(condition_id)
            for tok in token_ids:
                self._update_position(condition_id, tok, size, is_add=True)
        elif type == "MERGE" or type == "REDEEM":
            if self.positions.get(condition_id):
                condition_ids = list(self.positions[condition_id].keys())
                for tok in condition_ids:
                    self._update_position(condition_id, tok, size, is_add=False)
        else:
            logger.warning(f"Unsupported activity type for position update: {type}")

    def get_stats(self) -> dict:
        """Get tracker statistics"""
        return {
            "numpositions": len(self.positions.keys()),
            "balance": self.balance
        }
