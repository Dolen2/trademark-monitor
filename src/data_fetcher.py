"""
Data Fetcher module for USPTO trademark data.
Handles downloading daily XML files and TSDR API lookups.
"""

import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import time
import logging
import hashlib
import json

logger = logging.getLogger(__name__)


class USPTODataFetcher:
    """
    Fetches trademark data from USPTO sources:
    1. Daily XML bulk files (TDXF) - for new applications
    2. TSDR API - for detailed trademark status lookups
    """

    # USPTO bulk data URLs
    BULK_DATA_URLS = [
        "https://bulkdata.uspto.gov/data/trademark/dailyxml/applications",
        "https://bulkdata.uspto.gov/data/trademark/dailyxml/apc",
    ]

    # Alternative sources (Reed Tech mirrors)
    REEDTECH_URL = "https://trademarks.reedtech.com/tmappxml.php"

    # TSDR API base URL
    TSDR_API_URL = "https://tsdrapi.uspto.gov/ts/cd"

    def __init__(self, data_dir: str = "data/uspto_xml", api_key: str = None):
        """
        Initialize the data fetcher.

        Args:
            data_dir: Directory to store downloaded files
            api_key: USPTO API key for TSDR API (optional for bulk downloads)
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'TrademarkMonitor/1.0 (Relatent Inc; contact@relatent.com)'
        })

    def fetch_daily_file(self, date: datetime) -> Optional[Path]:
        """
        Download the daily XML file for a specific date.

        Args:
            date: Date to fetch data for

        Returns:
            Path to downloaded file or None if not available
        """
        # Format: apcYYMMDD.zip
        date_str = date.strftime('%y%m%d')
        filename = f"apc{date_str}.zip"
        local_path = self.data_dir / filename

        # Check if already downloaded
        if local_path.exists():
            logger.info(f"File already exists: {filename}")
            return local_path

        # Try each potential URL
        urls_to_try = [
            f"{self.BULK_DATA_URLS[0]}/{filename}",
            f"{self.BULK_DATA_URLS[1]}/{filename}",
        ]

        for url in urls_to_try:
            try:
                logger.info(f"Attempting to download: {url}")
                response = self.session.get(url, timeout=60, stream=True)

                if response.status_code == 200:
                    # Download the file
                    with open(local_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)

                    logger.info(f"Successfully downloaded: {filename}")
                    return local_path

                elif response.status_code == 404:
                    logger.debug(f"File not found at {url}")
                    continue

                else:
                    logger.warning(f"Unexpected status {response.status_code} from {url}")

            except requests.exceptions.RequestException as e:
                logger.warning(f"Error fetching {url}: {e}")
                continue

        logger.warning(f"Could not download file for date {date.strftime('%Y-%m-%d')}")
        return None

    def fetch_date_range(self, start_date: datetime, end_date: datetime = None,
                        skip_weekends: bool = True) -> List[Tuple[datetime, Optional[Path]]]:
        """
        Download daily files for a date range.

        Args:
            start_date: Start date
            end_date: End date (defaults to today)
            skip_weekends: Whether to skip Saturday/Sunday (USPTO doesn't publish)

        Returns:
            List of (date, path) tuples
        """
        if end_date is None:
            end_date = datetime.now()

        results = []
        current = start_date

        while current <= end_date:
            # Skip weekends if requested (USPTO typically doesn't publish on weekends)
            if skip_weekends and current.weekday() >= 5:
                current += timedelta(days=1)
                continue

            path = self.fetch_daily_file(current)
            results.append((current, path))

            # Rate limiting
            if path:
                time.sleep(1)

            current += timedelta(days=1)

        return results

    def get_recent_files(self, days: int = 7) -> List[Tuple[datetime, Optional[Path]]]:
        """
        Fetch files for the last N days.

        Args:
            days: Number of days to look back

        Returns:
            List of (date, path) tuples
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        return self.fetch_date_range(start_date, end_date)

    def list_available_files(self) -> List[Dict[str, Any]]:
        """
        List available USPTO bulk data files from the web directory.

        Returns:
            List of file info dictionaries
        """
        files = []

        for url in self.BULK_DATA_URLS:
            try:
                response = self.session.get(url, timeout=30)
                if response.status_code == 200:
                    # Parse directory listing (simplified - assumes HTML listing)
                    import re
                    pattern = r'apc\d{6}\.zip'
                    matches = re.findall(pattern, response.text)
                    for match in set(matches):
                        date_str = match[3:9]  # Extract YYMMDD
                        try:
                            date = datetime.strptime(date_str, '%y%m%d')
                            files.append({
                                'filename': match,
                                'date': date,
                                'url': f"{url}/{match}"
                            })
                        except ValueError:
                            pass
            except Exception as e:
                logger.warning(f"Error listing files at {url}: {e}")

        return sorted(files, key=lambda x: x['date'], reverse=True)

    def get_local_files(self) -> List[Path]:
        """Get list of already downloaded files."""
        return sorted(self.data_dir.glob("apc*.zip"), reverse=True)

    # ==================== TSDR API Methods ====================

    def lookup_trademark(self, serial_number: str) -> Optional[Dict[str, Any]]:
        """
        Look up detailed trademark information via TSDR API.

        Args:
            serial_number: USPTO serial number

        Returns:
            Trademark details or None if not found
        """
        # Clean serial number
        serial = serial_number.replace('/', '').replace('-', '')

        url = f"{self.TSDR_API_URL}/casestatus/sn{serial}/info.json"

        headers = {}
        if self.api_key:
            headers['X-API-Key'] = self.api_key

        try:
            response = self.session.get(url, headers=headers, timeout=30)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                logger.warning("TSDR API requires authentication. Get an API key at developer.uspto.gov")
                return None
            elif response.status_code == 404:
                logger.debug(f"Trademark not found: {serial_number}")
                return None
            else:
                logger.warning(f"TSDR API error {response.status_code} for {serial_number}")
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Error looking up trademark {serial_number}: {e}")
            return None

    def get_trademark_status(self, serial_number: str) -> Optional[str]:
        """
        Get the current status of a trademark.

        Args:
            serial_number: USPTO serial number

        Returns:
            Status description or None
        """
        data = self.lookup_trademark(serial_number)
        if data:
            try:
                return data.get('trademarkStatus', {}).get('statusDescription')
            except (KeyError, AttributeError):
                pass
        return None

    def get_tsdr_link(self, serial_number: str) -> str:
        """
        Generate TSDR website link for a trademark.

        Args:
            serial_number: USPTO serial number

        Returns:
            URL to TSDR page
        """
        serial = serial_number.replace('/', '').replace('-', '')
        return f"https://tsdr.uspto.gov/#caseNumber={serial}&caseSearchType=US_APPLICATION&caseType=DEFAULT&searchType=statusSearch"

    def batch_lookup(self, serial_numbers: List[str], delay: float = 1.0) -> Dict[str, Dict]:
        """
        Look up multiple trademarks with rate limiting.

        Args:
            serial_numbers: List of serial numbers
            delay: Delay between requests in seconds

        Returns:
            Dictionary mapping serial numbers to their data
        """
        results = {}
        for serial in serial_numbers:
            data = self.lookup_trademark(serial)
            if data:
                results[serial] = data
            time.sleep(delay)
        return results

    # ==================== Utility Methods ====================

    def verify_file_integrity(self, file_path: Path) -> bool:
        """
        Verify a downloaded file is valid.

        Args:
            file_path: Path to the file

        Returns:
            True if file is valid
        """
        import zipfile
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                # Check that it's a valid zip with XML content
                return any(f.endswith('.xml') for f in zf.namelist())
        except zipfile.BadZipFile:
            return False

    def cleanup_old_files(self, days_to_keep: int = 90):
        """
        Remove downloaded files older than specified days.

        Args:
            days_to_keep: Number of days of files to keep
        """
        cutoff = datetime.now() - timedelta(days=days_to_keep)

        for file_path in self.data_dir.glob("apc*.zip"):
            try:
                # Extract date from filename
                date_str = file_path.stem[3:9]
                file_date = datetime.strptime(date_str, '%y%m%d')

                if file_date < cutoff:
                    file_path.unlink()
                    logger.info(f"Removed old file: {file_path.name}")

            except (ValueError, OSError) as e:
                logger.debug(f"Error processing {file_path}: {e}")

    def get_download_stats(self) -> Dict[str, Any]:
        """Get statistics about downloaded files."""
        files = list(self.data_dir.glob("apc*.zip"))
        total_size = sum(f.stat().st_size for f in files)

        dates = []
        for f in files:
            try:
                date_str = f.stem[3:9]
                dates.append(datetime.strptime(date_str, '%y%m%d'))
            except ValueError:
                pass

        return {
            'total_files': len(files),
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'oldest_date': min(dates).strftime('%Y-%m-%d') if dates else None,
            'newest_date': max(dates).strftime('%Y-%m-%d') if dates else None,
        }


class MockUSPTOFetcher(USPTODataFetcher):
    """
    Mock fetcher for testing that generates sample data.
    Useful when USPTO data is not accessible.
    """

    def __init__(self, data_dir: str = "data/uspto_xml"):
        super().__init__(data_dir)

    def create_sample_data(self, date: datetime, num_records: int = 50) -> Path:
        """
        Create a sample XML file with realistic trademark data.
        Includes some marks that should trigger our similarity checks.
        """
        import random

        sample_marks = [
            # Marks that SHOULD be flagged
            ("TOPOWORLD", [9, 42], "Computer software for mapping and navigation"),
            ("TOPOLOGIX", [9], "Downloadable mobile applications for social networking"),
            ("MYTOPO", [9, 42], "Computer software platform for social media"),
            ("TOPOLINK", [42], "Online social networking services"),
            ("TOPOSPHERE", [9, 42], "Software for social network analysis"),
            # Marks that should NOT be flagged (different classes/unrelated)
            ("GREENTECH", [11], "Lighting fixtures"),
            ("BLUEMOON", [25], "Clothing"),
            ("FASTTRACK", [39], "Transportation services"),
            ("GOLDSTAR", [14], "Jewelry"),
            ("SUNBRIGHT", [3], "Cosmetics"),
            # More tech marks that might be close but different classes
            ("DATAFLOW", [9, 35], "Database software"),
            ("CLOUDBASE", [42], "Cloud computing services"),
            ("NETLINK", [38], "Telecommunications"),
        ]

        date_str = date.strftime('%y%m%d')
        filename = f"apc{date_str}_sample.zip"
        xml_filename = f"apc{date_str}.xml"

        # Generate XML content
        xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>\n<trademark-applications-daily>']

        base_serial = 99000000 + random.randint(1, 999999)

        for i in range(num_records):
            if i < len(sample_marks):
                mark, classes, gs = sample_marks[i]
            else:
                # Generate random marks
                mark = f"BRAND{random.randint(1000, 9999)}"
                classes = [random.choice([1, 3, 5, 9, 14, 25, 35, 41, 42])]
                gs = "Various goods and services"

            serial = base_serial + i
            filing_date = date.strftime('%Y%m%d')

            xml_parts.append(f'''
    <case-file>
        <serial-number>{serial}</serial-number>
        <filing-date>{filing_date}</filing-date>
        <mark-identification>{mark}</mark-identification>
        <mark-drawing-code>4</mark-drawing-code>
        <status-code>620</status-code>
        <classification>
            <international-code>{classes[0]}</international-code>
            <goods-services-description>{gs}</goods-services-description>
        </classification>
        <party-name>
            <name>Sample Applicant {i} LLC</name>
        </party-name>
    </case-file>''')

        xml_parts.append('\n</trademark-applications-daily>')
        xml_content = ''.join(xml_parts)

        # Create ZIP file
        import zipfile
        zip_path = self.data_dir / filename
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(xml_filename, xml_content)

        logger.info(f"Created sample data file: {filename} with {num_records} records")
        return zip_path


if __name__ == "__main__":
    # Test the data fetcher
    logging.basicConfig(level=logging.INFO)

    fetcher = USPTODataFetcher()

    # Show download stats
    print("Download Statistics:")
    stats = fetcher.get_download_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # Try to fetch recent files
    print("\nAttempting to fetch recent files...")
    # results = fetcher.get_recent_files(days=3)
    # for date, path in results:
    #     status = "Downloaded" if path else "Not available"
    #     print(f"  {date.strftime('%Y-%m-%d')}: {status}")

    # Generate sample data for testing
    print("\nGenerating sample data for testing...")
    mock_fetcher = MockUSPTOFetcher()
    sample_path = mock_fetcher.create_sample_data(datetime.now(), 50)
    print(f"Sample file created: {sample_path}")
