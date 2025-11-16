#!/usr/bin/env python3

import asyncio
import signal
import sys
from datetime import datetime
import uvicorn
from typing import List, Dict, Optional

from rss_poller import RSSPoller
from webhook_server import app as webhook_app


class HybridStatusMonitor:
    def __init__(self):
        self.rss_poller: Optional[RSSPoller] = None
        self.server_task: Optional[asyncio.Task] = None
        self.poller_task: Optional[asyncio.Task] = None
        self.running = True

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        print(f"\n[{self._get_timestamp()}] Shutting down...")
        self.running = False

        if self.rss_poller:
            self.rss_poller.stop()

    def _get_timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async def run_webhook_server(self, host: str = "0.0.0.0", port: int = 8000):
        config = uvicorn.Config(
            webhook_app,
            host=host,
            port=port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()

    async def run_rss_poller(self, feed_configs: List[Dict], interval: int = 180):
        self.rss_poller = RSSPoller(feed_configs)
        await self.rss_poller.poll_loop(interval=interval)

    async def start(
        self,
        feed_configs: List[Dict],
        webhook_host: str = "0.0.0.0",
        webhook_port: int = 8000,
        rss_interval: int = 180
    ):
        print("=" * 80)
        print("Status Page Monitor")
        print("=" * 80)
        print(f"[{self._get_timestamp()}] Starting hybrid monitor")
        print(f"[{self._get_timestamp()}] Webhook receiver: http://{webhook_host}:{webhook_port}")
        print(f"[{self._get_timestamp()}] RSS poller: {len(feed_configs)} feeds, {rss_interval}s interval")
        print(f"[{self._get_timestamp()}]")
        print(f"[{self._get_timestamp()}] Webhook endpoints:")
        print(f"[{self._get_timestamp()}]   - incident.io: http://localhost:{webhook_port}/webhook/incident-io")
        print(f"[{self._get_timestamp()}]   - Generic: http://localhost:{webhook_port}/webhook/generic/{{provider}}")
        print(f"[{self._get_timestamp()}]   - Health: http://localhost:{webhook_port}/health")
        print(f"[{self._get_timestamp()}]")
        print(f"[{self._get_timestamp()}] To expose webhooks: ngrok http {webhook_port}")
        print(f"[{self._get_timestamp()}] Press Ctrl+C to stop")
        print("=" * 80)
        print()

        self.server_task = asyncio.create_task(
            self.run_webhook_server(webhook_host, webhook_port)
        )
        self.poller_task = asyncio.create_task(
            self.run_rss_poller(feed_configs, rss_interval)
        )

        try:
            await asyncio.gather(self.server_task, self.poller_task)
        except asyncio.CancelledError:
            print(f"[{self._get_timestamp()}] Tasks cancelled")

        print(f"[{self._get_timestamp()}] Monitor stopped")


async def main():
    feed_configs = [
        {
            'name': 'OpenAI',
            'url': 'https://status.openai.com/feed.rss'
        },
    ]

    monitor = HybridStatusMonitor()

    await monitor.start(
        feed_configs=feed_configs,
        webhook_host="0.0.0.0",
        webhook_port=8000,
        rss_interval=180
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nMonitor stopped by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
