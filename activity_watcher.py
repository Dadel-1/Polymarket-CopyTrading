import asyncio
import requests
import logging
from typing import Optional, List
from datetime import datetime
from config import POLL_INTERVAL, HEARTBEAT_INTERVAL

logger = logging.getLogger(__name__)

class ActivityWatcher:
    """Fetches trading activities from Polymarket API asynchronously"""
    
    API_BASE_URL = "https://data-api.polymarket.com"
    
    def __init__(self, queue: asyncio.Queue, target_address: Optional[str] = None):
        """
        Initialize the activity watcher
        
        Args:
            queue: asyncio.Queue instance to add activities to
            target_address: Target trader address to monitor (defaults to config)
        """
        self.queue = queue
        self.target_address = target_address
        self.last_fetch_time: int = int(datetime.now().timestamp())
        self.last_poll_time: float = datetime.now().timestamp()
        self._last_heartbeat_log: float = datetime.now().timestamp()
        self.nb_timeouts: int = 0
        self.nb_activities: int = 0
        self.running = False
   
    async def _fetch_new_activities(self) -> List[object]:
        """
        Fetch activities and filter for new ones since last fetch time
        """      
        url = f"{self.API_BASE_URL}/activity"
        params = {
            "limit": 100,
            "sortBy": "TIMESTAMP",
            "sortDirection": "DESC",
            "user": self.target_address
        }
        activities = []
        try:
            # Run blocking HTTP call off the event loop to avoid stalling polling
            response = await asyncio.to_thread(requests.get, url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                logger.debug(f"Fetched {len(data)} activities from API")
                new_last_fetch_time = self.last_fetch_time
                for item in data:
                    timestamp = int(item.get("timestamp", 0))
                    if timestamp > new_last_fetch_time:
                        new_last_fetch_time = timestamp
                    if timestamp > self.last_fetch_time:
                        if not item.get("type") in ("YIELD", "REWARD"):
                            activities.append(item)
                    else:
                        break  # Stop processing older activities
                self.last_fetch_time = new_last_fetch_time
            else:
                logger.error(f"API request failed with status {response.status_code}: {response.text}")
        except requests.exceptions.Timeout:
            logger.warning("Activity fetch timed out after 5s")
            self.nb_timeouts += 1
        except Exception as e:
            logger.error(f"Unexpected error fetching activities: {e}")
        
        return activities
    
    def _merge_activities(self, activities: List[object], merged: List[object]):
        if not activities:
            return activities

        for activity in activities:
            if merged:
                last = merged[-1]
                if (
                    last.get("type") == activity.get("type")
                    and last.get("side") == activity.get("side")
                    and last.get("conditionId") == activity.get("conditionId")
                    and last.get("asset") == activity.get("asset")
                ):
                    l_size = last.get("size", 0.0)
                    a_size = activity.get("size", 0.0)
                    last["size"] = l_size + a_size
                    last["usdcSize"] = last.get("usdcSize", 0.0) + activity.get("usdcSize", 0.0)
                    # Weighted average
                    last["price"] = (last.get("price", 0.0) * l_size + activity.get("price", 0.0) * a_size) / (l_size + a_size)
                    last["timestamp"] = max(last.get("timestamp", 0), activity.get("timestamp", 0))
                    continue
            merged.append(activity)

        return merged
    
    async def _fetch_and_queue(self) -> None:
        """Fetch activities and add new ones to the queue"""
        self.last_poll_time = datetime.now().timestamp()
        new_activities = await self._fetch_new_activities()

        if new_activities:
            merged = []
            self._merge_activities(new_activities, merged)
            n = len(new_activities)
            m = len(merged)
            new_activities = merged
            if m < n:
                logger.info(f"Found {n} new activit{'ies' if n > 1 else 'y'} merged into {m}")
            else:
                logger.debug(f"Found {n} new activit{'ies' if n > 1 else 'y'}")

            for i in range(len(new_activities)-1, -1, -1):
                activity = new_activities[i]
                await self.queue.put(activity)
                self.nb_activities += 1
                side = activity.get("side")
                logger.info(
                    "🆕 %s \"%s\" (size=%s, price=%s, usdc=%s)",
                    activity.get("type") + f"|{side}" if side else "",
                    activity.get("title"),
                    activity.get("size"),
                    activity.get("price"),
                    activity.get("usdcSize"),
                )
    
    async def start(self) -> None:
        """Start the continuous fetching loop"""
        if self.running:
            logger.warning("Watcher already running")
            return
        
        self.running = True
        logger.info(f"Starting activity watcher for address: {self.target_address}")
        
        while self.running:
            try:
                await self._fetch_and_queue()
            except asyncio.CancelledError:
                logger.info("Activity watcher cancelled")
                self.running = False
            except Exception as e:
                logger.error(f"Fatal error in watcher loop: {e}", exc_info=True)
                self.running = False
            # Heartbeat so we can detect if the loop is alive even when idle
            now = datetime.now().timestamp()
            if now - self._last_heartbeat_log >= HEARTBEAT_INTERVAL:
                seconds_since_fetch = now - self.last_poll_time
                logger.info(
                    "📍 Watcher heartbeat (Running: %s, Last fetch: %.3fs, Timeouts: %d, Activities: %d)",
                    self.running,
                    seconds_since_fetch,
                    self.nb_timeouts,
                    self.nb_activities,
                )
                self._last_heartbeat_log = now
                self.nb_timeouts = 0
            await asyncio.sleep(POLL_INTERVAL)
    
    async def stop(self) -> None:
        """Stop the fetching loop"""
        logger.info("Stopping activity watcher...")
        self.running = False

    def isrunning(self) -> bool:
        """Check if watcher is running"""
        return self.running
    
    def get_stats(self) -> dict:
        """Get watcher statistics"""
        return {
            "running": self.running,
            "target_address": self.target_address,
            "last_fetch_time": self.last_fetch_time,
            "nb_activities": self.nb_activities,
            "seconds_since_last_poll": max(0.0, datetime.now().timestamp() - self.last_poll_time),
        }

