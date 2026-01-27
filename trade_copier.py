"""
Trade copier that processes activities from queue and copies trades proportionally
"""
import asyncio
import logging

from wallet_tracker import WalletTracker
from blockchain_client import BlockchainClient
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderType, MarketOrderArgs, OrderArgs
from py_clob_client.order_builder.constants import BUY, SELL
from config import CLOB_HOST, CHAIN_ID, PRIVATE_KEY, POLYMARKET_PROXY_ADDRESS, SIGNATURE_TYPE

logger = logging.getLogger(__name__)


class TradeCopier:
    """Copies trades from target trader proportionally"""
    
    def __init__(self, queue: asyncio.Queue, copier_address: str, target_address: str):
        """
        Initialize trade copier
        
        Args:
            queue: Queue containing activities from the watcher
            copier_wallet_manager: WalletManager for the copier wallet
        """
        self.queue = queue
        self.copier_address = copier_address
        self.target_address = target_address
        self.copier_wallet_tracker = WalletTracker(copier_address)
        self.target_wallet_tracker = WalletTracker(target_address)
        # Initialize CLOB client
        self.client = ClobClient(host=CLOB_HOST, key=PRIVATE_KEY, chain_id=CHAIN_ID, funder=POLYMARKET_PROXY_ADDRESS, signature_type=SIGNATURE_TYPE)
        self.client.set_api_creds(self.client.create_or_derive_api_creds())
        # Initialize blockchain client
        self.blockchain_client = BlockchainClient()
        # Stats
        self._copied_trades = 0
        self._skipped_trades = 0
        self._failed_trades = 0
        self._running = False

    async def start(self) -> None:
        """Start the copier loop"""
        if self._running:
            logger.warning("Copier is already running")
            return
        
        self._running = True
        logger.info("Starting trade copier...")
        
        # Initialize: fetch positions and trader value
        await asyncio.gather(
            self.copier_wallet_tracker.start(refresh_interval=1),
            self.target_wallet_tracker.start()
        )

        while self._running:
            try:
                # Get activity from queue (with timeout to allow checking running status)
                try:
                    activity = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                    await self._process_activity(activity)
                except asyncio.TimeoutError:
                    # No activity in queue, continue loop
                    continue
            
            except asyncio.CancelledError:
                logger.info("Trade copier cancelled")
                self._running = False
                break
            except Exception as e:
                logger.error(f"Error in copier loop: {e}", exc_info=True)
                await asyncio.sleep(1)  # Brief pause before retrying
    
    def _get_trading_ratio(self, condition_id: str, token_id: str) -> float:
        """
        Calculate the proportional ratio between copier and trader wallets
        
        Returns:
            Ratio as float (copier_value / trader_value)
        """
        copier_amount = self.copier_wallet_tracker.get_position(condition_id, token_id)
        trader_amount = self.target_wallet_tracker.get_position(condition_id, token_id)
        
        if trader_amount == 0:
            logger.warning("No trader balance for %s in %s; ratio fallback to 0", token_id, condition_id)
            return 0

        ratio = copier_amount / trader_amount
        logger.debug("Ratio: %.4f (copier=%s trader=%s)", ratio, copier_amount, trader_amount)
        return ratio

    def _get_proportional_amount(self, original_amount: float, condition_id: str, token_id: str) -> float:
        ratio = self._get_trading_ratio(condition_id, token_id)
        proportional_amount = original_amount * ratio
        return proportional_amount
    
    async def _process_activity(self, activity: dict) -> None:
        activity_type = activity.get("type") # TRADE, SPLIT, MERGE, REDEEM, REWARD, CONVERSION
        side = activity.get("side") # BUY or SELL
        condition_id = activity.get("conditionId")
        token_id = activity.get("asset")
        size = float(activity.get("size"))
        usdc_size = float(activity.get("usdcSize"))
        signed_order, tx, action = None, None, None
        orderType = OrderType.FOK

        # 1. Create copy trade
        if activity_type == "TRADE":

            if side == BUY:
                usdc_amount = self._get_proportional_amount(usdc_size, "USDC", "USDC")
                if usdc_amount > 0:
                    if usdc_amount > self.copier_wallet_tracker.get_position("USDC", "USDC"):
                        logger.info(f"⏩ Not enough USDC for BUY order, skipping BUY")
                    if usdc_amount > 1:
                        # Market order for orders > $1
                        order_args = MarketOrderArgs(
                            token_id = token_id,
                            amount = usdc_amount,
                            side = BUY,
                        )
                        signed_order = self.client.create_market_order(order_args)
                        logger.info(f"📈 BUY ${usdc_amount} of {activity.get('eventSlug')}")
                    else:
                        # Hack limit order (transformed to market order) for orders <= $1
                        share_amount = self._get_proportional_amount(size, "USDC", "USDC")
                        share_amount = max(share_amount, 1.02) # 1.02 is min so that x * 0.99 >= $1
                        order_args = OrderArgs(
                            price=0.99, # Maximum allowed price for Limit orders
                            size=share_amount,
                            side=BUY,
                            token_id = token_id,
                        )
                        signed_order = self.client.create_order(order_args)
                        orderType = OrderType.GTC
                        logger.info(f"📈 BUY {share_amount} shares of {activity.get('eventSlug')}")
                else:
                    logger.info("⏩ Calculated buy amount is 0 for, skipping BUY")

            elif side == SELL:
                copier_available = self.copier_wallet_tracker.get_position(condition_id, token_id)
                trader_available = self.target_wallet_tracker.get_position(condition_id, token_id)
                proportional_amount = self._get_proportional_amount(size, condition_id, token_id)
                # Check if trader is selling all his bag or not enough tokens
                if size >= trader_available or proportional_amount > copier_available:
                    amount = copier_available
                else:
                    amount = proportional_amount

                if amount > 0:
                    order_args = MarketOrderArgs(
                        token_id = token_id,
                        amount = amount,
                        side = SELL,
                    )
                    signed_order = self.client.create_market_order(order_args)
                    logger.info(f"📉 SELL {amount} shares of {activity.get('eventSlug')}")
                else:
                    logger.info("⏩ Calculated sell amount is 0, skipping SELL")
            else:
                logger.warning("Unknown trade side in activity: %s", side)

        elif activity_type == "SPLIT":
            usdc_amount = self._get_proportional_amount(usdc_size, "USDC", "USDC")
            tx, action = self.blockchain_client.split(condition_id, usdc_amount)

        elif activity_type == "MERGE":
            target_mergeable = self.target_wallet_tracker.get_mergeable_amount(condition_id)
            copier_mergeable = self.copier_wallet_tracker.get_mergeable_amount(condition_id)
            if target_mergeable == 0 or copier_mergeable == 0:
                logger.info("⏩ No mergeable positions, skipping MERGE")
            else:
                amount = 0
                # Check if trader is merging all his mergeable tokens
                if size >= target_mergeable:
                    amount = copier_mergeable
                else:
                    ratio = copier_mergeable / target_mergeable
                    amount = size * ratio
                if amount > 0:
                    tx, action = self.blockchain_client.merge(condition_id, amount)
                else:
                    logger.info("⏩ Calculated merge amount is 0, skipping MERGE")
            
        elif activity_type == "REDEEM":
            if self.target_wallet_tracker.is_redeemable(condition_id):
                tx, action = self.blockchain_client.redeem(condition_id)
            else:
                logger.debug("⏩ No redeemable positions, skipping REDEEM")
    
        else:
            logger.debug("⏩ Skipping unsupported activity type: %s", activity_type)
            return

        # 2. Update target positions
        self.target_wallet_tracker.update_positions(activity_type, side, condition_id, token_id, size)

        # 3. Execute copy trade
        if signed_order:            
            # Send trade to CLOB
            resp = self.client.post_order(signed_order, orderType = orderType)
            if not resp or not resp.get("success", False):
                logger.error("CLOB error response: %s", resp)
        if tx and action:
            self.blockchain_client.execute_transaction(tx, action)

    async def stop(self) -> None:
        logger.info("Stopping trade copier")
        self._running = False
    
    def is_running(self) -> bool:
        return self._running
    
    def get_stats(self) -> dict:
        return {
            "running": self._running,
            "copied_trades": self._copied_trades,
            "skipped_trades": self._skipped_trades,
            "failed_trades": self._failed_trades,
            "copier_wallet_tracker": self.copier_wallet_tracker.get_stats(),
            "target_wallet_tracker": self.target_wallet_tracker.get_stats()
        }
