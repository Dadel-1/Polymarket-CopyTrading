"""
Main entry point for Polymarket Copy Trading Bot
"""
import asyncio
import logging
import signal
import sys
from config import LOG_LEVEL, LOG_FILE, TARGET_TRADER_ADDRESS, POLYMARKET_PROXY_ADDRESS
from activity_watcher import ActivityWatcher
from trade_copier import TradeCopier

# Configure logging
handlers = [logging.StreamHandler(sys.stdout)]
if LOG_FILE:
    handlers.append(logging.FileHandler(LOG_FILE, encoding='utf-8'))

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=handlers,
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class CopyTradingBot:
    """Main bot class that orchestrates the copy trading system"""
    
    def __init__(self, copier_address, target_address):
        """Initialize the bot"""
        logger.info("Initializing copy-trading bot")
        self.copier_address = copier_address
        self.target_address = target_address
        
        self.queue = asyncio.Queue()
        self.watcher = ActivityWatcher(self.queue, target_address)
        self.copier = TradeCopier(self.queue, copier_address, target_address)
        
        self._shutdown_event = asyncio.Event()
        logger.debug("Bot initialized successfully")
    
    async def start(self) -> None:
        """Start the bot"""
        logger.info("Starting copy-trading bot")
        
        # Start the watcher task (fetches activities)
        watcher_task = asyncio.create_task(self.watcher.start())
        
        # Start the copier task (processes activities and copies trades)
        copier_task = asyncio.create_task(self.copier.start())

        logger.info("🚀 Bot running (watcher + copier) 🚀")
        
        # Wait for shutdown signal
        await self._shutdown_event.wait()
        
        # Stop both tasks
        logger.info("Shutting down bot")
        await self.watcher.stop()
        await self.copier.stop()
        watcher_task.cancel()
        copier_task.cancel()
        
        # Wait for tasks to finish
        try:
            await asyncio.gather(watcher_task, copier_task, return_exceptions=True)
        except Exception as e:
            logger.debug(f"Task cancellation: {e}")
        
        # Print final stats
        logger.info("Final watcher stats: %s", self.watcher.get_stats())
        logger.info("Final copier stats: %s", self.copier.get_stats())
        logger.info("Bot stopped")
    
    def shutdown(self) -> None:
        """Trigger shutdown"""
        logger.info("Shutdown signal received")
        self._shutdown_event.set()


async def main():
    """Main async function"""
    bot = CopyTradingBot(POLYMARKET_PROXY_ADDRESS, TARGET_TRADER_ADDRESS)
    
    # Set up signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Signal received: %s", sig)
        bot.shutdown()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        bot.shutdown()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot interrupted by user")
        sys.exit(0)

