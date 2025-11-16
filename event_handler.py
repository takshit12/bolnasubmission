#!/usr/bin/env python3

import asyncio
from datetime import datetime
from typing import Dict, Set
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
import hashlib
import re


class EventHandler:
    def __init__(self):
        self.seen_incidents: Set[str] = set()
        self._lock = asyncio.Lock()

    def _get_timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async def is_seen(self, incident_id: str) -> bool:
        async with self._lock:
            return incident_id in self.seen_incidents

    async def mark_seen(self, incident_id: str):
        async with self._lock:
            self.seen_incidents.add(incident_id)

    def _normalize_webhook_data(self, event_data: Dict, source_name: str) -> Dict:
        event_type = event_data.get('event_type', '')
        data = event_data.get('data', event_data)
        incident = data.get('incident', data)

        normalized = {
            'id': incident.get('id', ''),
            'source': source_name,
            'source_type': 'webhook',
            'event_type': event_type,
            'title': incident.get('name', incident.get('title', 'Unknown Incident')),
            'status': incident.get('status', {}).get('label', 'Unknown') if isinstance(incident.get('status'), dict) else str(incident.get('status', 'Unknown')),
            'severity': incident.get('severity', {}).get('label', '') if isinstance(incident.get('severity'), dict) else '',
            'description': incident.get('summary', incident.get('description', '')),
            'components': [],
            'link': incident.get('permalink', incident.get('url', '')),
            'timestamp': datetime.utcnow().isoformat(),
        }

        if 'affected_components' in incident:
            normalized['components'] = [
                comp.get('name', str(comp))
                for comp in incident['affected_components']
            ]

        created_at = incident.get('created_at', event_data.get('created_at'))
        if created_at:
            try:
                dt = date_parser.parse(created_at)
                normalized['timestamp'] = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass

        return normalized

    def _normalize_rss_data(self, entry: Dict, source_name: str) -> Dict:
        incident_id = entry.get('id', entry.get('guid', ''))
        if not incident_id:
            id_source = f"{entry.get('title', '')}{entry.get('published', '')}"
            incident_id = hashlib.md5(id_source.encode()).hexdigest()

        normalized = {
            'id': incident_id,
            'source': source_name,
            'source_type': 'rss',
            'title': entry.get('title', 'Unknown Incident'),
            'description': entry.get('description', entry.get('summary', '')),
            'link': entry.get('link', ''),
            'components': [],
            'status': 'Unknown',
            'timestamp': entry.get('published', ''),
        }

        description = normalized['description']
        if description:
            soup = BeautifulSoup(description, 'lxml')

            component_tags = soup.find_all(['strong', 'b'])
            for tag in component_tags:
                text = tag.get_text(strip=True)
                if text and not text.lower().startswith('status'):
                    normalized['components'].append(text)

            description_text = soup.get_text(separator=' ', strip=True)
            status_patterns = [
                r'(operational|degraded|partial|major|maintenance|outage|incident|investigating|monitoring|resolved)',
                r'status:\s*(\w+)',
            ]

            for pattern in status_patterns:
                match = re.search(pattern, description_text, re.IGNORECASE)
                if match:
                    normalized['status'] = match.group(1).title()
                    break

        if normalized['timestamp']:
            try:
                dt = date_parser.parse(normalized['timestamp'])
                normalized['timestamp'] = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                normalized['timestamp'] = self._get_timestamp()
        else:
            normalized['timestamp'] = self._get_timestamp()

        return normalized

    def _format_incident_output(self, incident: Dict) -> str:
        components_str = ', '.join(incident['components']) if incident['components'] else 'General'
        output = f"[{incident['timestamp']}] "

        if incident['source']:
            output += f"Provider: {incident['source']} | "

        output += f"Product: {components_str}\n"
        output += f"Status: {incident['status']} - {incident['title']}"

        if incident.get('event_type'):
            output += f"\nEvent: {incident['event_type']}"

        if incident.get('link'):
            output += f"\nLink: {incident['link']}"

        return output

    async def handle_webhook_event(self, event_data: Dict, source_name: str = "Unknown"):
        try:
            incident = self._normalize_webhook_data(event_data, source_name)

            if await self.is_seen(incident['id']):
                print(f"[{self._get_timestamp()}] Duplicate webhook event (already seen): {incident['id']}")
                return

            await self.mark_seen(incident['id'])

            print("\n" + "=" * 80)
            print(self._format_incident_output(incident))
            print("=" * 80)

        except Exception as e:
            print(f"[{self._get_timestamp()}] Error processing webhook event: {e}")

    async def handle_rss_entry(self, entry: Dict, source_name: str = "Unknown"):
        try:
            incident = self._normalize_rss_data(entry, source_name)

            if await self.is_seen(incident['id']):
                return

            await self.mark_seen(incident['id'])

            print("\n" + "=" * 80)
            print(self._format_incident_output(incident))
            print("=" * 80)

        except Exception as e:
            print(f"[{self._get_timestamp()}] Error processing RSS entry: {e}")


event_handler = EventHandler()
