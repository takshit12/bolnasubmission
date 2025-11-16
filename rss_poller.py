#!/usr/bin/env python3

import asyncio
import aiohttp
import feedparser
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from event_handler import event_handler


class RSSPoller:
    def __init__(self, feed_configs: Optional[List[Dict[str, str]]] = None):
        self.feed_configs = feed_configs or [
            {
                'name': 'OpenAI',
                'url': 'https://status.openai.com/feed.rss'
            }
        ]
        self.etags: Dict[str, str] = {}
        self.last_modified: Dict[str, str] = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = True

    def _get_timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async def create_session(self):
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30)
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=10,
                ttl_dns_cache=300
            )
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            )

    async def close_session(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def fetch_feed(self, feed_config: Dict[str, str]) -> Tuple[Optional[str], bool]:
        url = feed_config['url']
        headers = {}

        if url in self.etags:
            headers['If-None-Match'] = self.etags[url]

        if url in self.last_modified:
            headers['If-Modified-Since'] = self.last_modified[url]

        try:
            async with self.session.get(url, headers=headers) as response:
                if response.status == 304:
                    return None, False

                if response.status != 200:
                    print(f"[{self._get_timestamp()}] RSS Error: {feed_config['name']} - "
                          f"HTTP {response.status}")
                    return None, False

                if 'ETag' in response.headers:
                    self.etags[url] = response.headers['ETag']

                if 'Last-Modified' in response.headers:
                    self.last_modified[url] = response.headers['Last-Modified']

                content = await response.text()
                return content, True

        except asyncio.TimeoutError:
            print(f"[{self._get_timestamp()}] RSS Timeout: {feed_config['name']}")
            return None, False
        except Exception as e:
            print(f"[{self._get_timestamp()}] RSS Error: {feed_config['name']} - {e}")
            return None, False

    async def check_feed_for_updates(self, feed_config: Dict[str, str]):
        content, was_modified = await self.fetch_feed(feed_config)

        if not content:
            return

        feed = feedparser.parse(content)

        for entry in feed.entries:
            await event_handler.handle_rss_entry(entry, feed_config['name'])

    async def check_all_feeds(self):
        if not self.session:
            await self.create_session()

        tasks = [
            self.check_feed_for_updates(feed_config)
            for feed_config in self.feed_configs
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

    async def poll_loop(self, interval: int = 180):
        print(f"[{self._get_timestamp()}] RSS Poller started")
        print(f"[{self._get_timestamp()}] Monitoring {len(self.feed_configs)} feed(s)")
        print(f"[{self._get_timestamp()}] Polling interval: {interval} seconds\n")

        await self.check_all_feeds()

        while self.running:
            try:
                await asyncio.sleep(interval)

                if not self.running:
                    break

                await self.check_all_feeds()

            except Exception as e:
                print(f"[{self._get_timestamp()}] RSS Error in poll loop: {e}")
                await asyncio.sleep(10)

        await self.close_session()
        print(f"[{self._get_timestamp()}] RSS Poller stopped")

    def stop(self):
        self.running = False


async def main():
    feed_configs = [
        {
            'name': 'OpenAI',
            'url': 'https://status.openai.com/feed.rss'
        },
    ]

    poller = RSSPoller(feed_configs)
    await poller.poll_loop(interval=180)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nRSS Poller stopped by user")
    except Exception as e:
        print(f"\nError: {e}")
