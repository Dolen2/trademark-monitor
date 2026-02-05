"""
Data Fetcher module for USPTO trademark data.
Uses TESS scraping to find recent trademark filings - NO API KEY REQUIRED.
"""

import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
import time
import logging
import json
import re
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class USPTODataFetcher:
    """
    Fetches trademark data from USPTO sources via web scraping.
    No API key required - uses publicly accessible TESS search.
    """

    TESS_BASE = "https://tmsearch.uspto.gov"
    TSDR_BASE = "https://tsdr.uspto.gov"

    def __init__(self, data_dir: str = "data/uspto"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })
        self.tess_state = None

    def _init_tess_session(self) -> bool:
        try:
            response = self.session.get(
                f"{self.TESS_BASE}/bin/gate.exe?f=login&p_lang=english&p_d=trmk",
                timeout=30
            )
            if response.status_code == 200:
                match = re.search(r'state=([^&"\'>\s]+)', response.text)
                if match:
                    self.tess_state = match.group(1)
                    logger.info(f"TESS session initialized")
                    return True
            return False
        except Exception as e:
            logger.error(f"Error initializing TESS session: {e}")
            return False

    def search_recent_filings_by_class(self, international_classes: List[int], days_back: int = 7) -> List[Dict[str, Any]]:
        """Search for recent trademark filings in specific classes."""
        if not self.tess_state:
            if not self._init_tess_session():
                logger.warning("TESS unavailable, returning empty results")
                return []

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        date_from = start_date.strftime('%Y%m%d')
        date_to = end_date.strftime('%Y%m%d')

        all_results = []
        for ic in international_classes:
            query = f"[{date_from},{date_to}][FD] AND {ic:03d}[IC]"
            logger.info(f"Searching TESS: {query}")
            results = self._search_tess(query)
            for r in results:
                r['international_classes'] = [ic]
                if r not in all_results:
                    all_results.append(r)
            time.sleep(2)
        return all_results

    def _search_tess(self, query: str) -> List[Dict[str, Any]]:
        try:
            params = {
                'f': 'toc', 'state': self.tess_state,
                'p_search': 'search', 'p_s_ALL': query,
                'p_L': 500, 'a_search': 'Submit Query',
            }
            response = self.session.get(f"{self.TESS_BASE}/bin/gate.exe", params=params, timeout=60)
            if response.status_code == 200:
                return self._parse_tess_results(response.text)
        except Exception as e:
            logger.error(f"TESS search error: {e}")
        return []

    def _parse_tess_results(self, html: str) -> List[Dict[str, Any]]:
        results = []
        try:
            soup = BeautifulSoup(html, 'html.parser')
            for row in soup.find_all('tr'):
                serial_link = row.find('a', href=re.compile(r'serial'))
                if serial_link:
                    href = serial_link.get('href', '')
                    serial_match = re.search(r'(\d{8})', href)
                    if serial_match:
                        results.append({
                            'serial_number': serial_match.group(1),
                            'mark_name': serial_link.get_text(strip=True) or 'Unknown',
                            'source': 'TESS'
                        })
        except Exception as e:
            logger.error(f"Error parsing TESS: {e}")
        return results

    def get_tsdr_link(self, serial_number: str) -> str:
        serial = serial_number.replace('/', '').replace('-', '').replace(' ', '')
        return f"https://tsdr.uspto.gov/#caseNumber={serial}&caseSearchType=US_APPLICATION&caseType=DEFAULT&searchType=statusSearch"

    def get_trademark_details(self, serial_number: str) -> Optional[Dict[str, Any]]:
        return {'serial_number': serial_number, 'status': 'Unknown'}

    def save_filings(self, trademarks: List[Dict], date: datetime = None):
        if date is None:
            date = datetime.now()
        filename = f"filings_{date.strftime('%Y%m%d')}.json"
        filepath = self.data_dir / filename
        with open(filepath, 'w') as f:
            json.dump({'date': date.isoformat(), 'trademarks': trademarks}, f, indent=2)
        logger.info(f"Saved {len(trademarks)} trademarks to {filename}")

    def generate_sample_data(self, date: datetime = None, num_records: int = 50) -> List[Dict[str, Any]]:
        import random
        if date is None:
            date = datetime.now()

        similar_marks = [
            {"mark_name": "TOPOWORLD", "classes": [9, 42], "gs": "Computer software"},
            {"mark_name": "TOPOLOGIX", "classes": [9], "gs": "Mobile applications"},
            {"mark_name": "MYTOPO", "classes": [9, 42], "gs": "Social media platform"},
            {"mark_name": "TOPOLINK", "classes": [42], "gs": "Online networking"},
            {"mark_name": "TOPOSPHERE", "classes": [9, 42], "gs": "Software analysis"},
            {"mark_name": "TOPO CONNECT", "classes": [9], "gs": "Mobile app"},
            {"mark_name": "E-TOPO", "classes": [42], "gs": "SaaS platform"},
            {"mark_name": "TOPOLOGIC", "classes": [9, 42], "gs": "AI software"},
            {"mark_name": "TOPOPRO", "classes": [42], "gs": "Professional networking"},
            {"mark_name": "NEWTOPO", "classes": [9], "gs": "Digital networks"},
            {"mark_name": "TOPOLOGY MASTERS", "classes": [42], "gs": "Consulting"},
            {"mark_name": "TOPOFINDER", "classes": [9, 42], "gs": "Location app"},
        ]

        unrelated = [
            {"mark_name": "GREENTECH", "classes": [11], "gs": "Lighting"},
            {"mark_name": "BLUEMOON", "classes": [25], "gs": "Clothing"},
            {"mark_name": "FASTTRACK", "classes": [39], "gs": "Transport"},
        ]

        results = []
        base_serial = 99000000 + random.randint(1, 999999)

        for i, m in enumerate(similar_marks + unrelated):
            results.append({
                'serial_number': str(base_serial + i),
                'mark_name': m['mark_name'],
                'filing_date': date.strftime('%Y-%m-%d'),
                'status': '620',
                'international_classes': m['classes'],
                'goods_services': m['gs'],
                'applicant_name': f"Sample Applicant {i} LLC",
                'source': 'SAMPLE_DATA'
            })

        while len(results) < num_records:
            idx = len(results)
            results.append({
                'serial_number': str(base_serial + idx),
                'mark_name': f"BRAND{random.randint(1000, 9999)}",
                'filing_date': date.strftime('%Y-%m-%d'),
                'status': '620',
                'international_classes': [random.choice([9, 42])],
                'goods_services': "Various services",
                'applicant_name': f"Random Corp {idx}",
                'source': 'SAMPLE_DATA'
            })

        logger.info(f"Generated {len(results)} sample trademarks")
        return results

    def get_download_stats(self) -> Dict[str, Any]:
        return {'total_files': 0, 'total_trademarks': 0}


MockUSPTOFetcher = USPTODataFetcher
