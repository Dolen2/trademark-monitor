"""
Main monitoring orchestrator for trademark monitoring system.
Coordinates data fetching, parsing, similarity analysis, and alerting.
"""

import yaml
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging
from logging.handlers import RotatingFileHandler

from .database import TrademarkDatabase
from .data_fetcher import USPTODataFetcher, MockUSPTOFetcher
from .xml_parser import USPTOXMLParser, filter_by_classes
from .similarity import TrademarkSimilarity
from .alerts import AlertSystem

logger = logging.getLogger(__name__)


class TrademarkMonitor:
    """
    Main orchestrator for the trademark monitoring system.
    """

    def __init__(self, config_path: str = None, config: Dict = None):
        """
        Initialize the trademark monitor.

        Args:
            config_path: Path to YAML configuration file
            config: Configuration dictionary (overrides file if provided)
        """
        self.config = config or self._load_config(config_path)
        self._setup_logging()
        self._init_components()
        self._register_our_trademarks()

    def _load_config(self, config_path: str = None) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if config_path is None:
            # Try default locations
            possible_paths = [
                'config/config.yaml',
                '../config/config.yaml',
                os.path.expanduser('~/.trademark_monitor/config.yaml'),
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    config_path = path
                    break

        if config_path and os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                # Expand environment variables
                config = self._expand_env_vars(config)
                return config

        logger.warning("No configuration file found, using defaults")
        return self._default_config()

    def _expand_env_vars(self, obj):
        """Recursively expand environment variables in configuration."""
        if isinstance(obj, dict):
            return {k: self._expand_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._expand_env_vars(item) for item in obj]
        elif isinstance(obj, str) and obj.startswith('${') and obj.endswith('}'):
            env_var = obj[2:-1]
            return os.environ.get(env_var, obj)
        return obj

    def _default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            'trademarks': [
                {'name': 'TOPO', 'serial_numbers': ['99634122', '99634130'], 'classes': [9, 42]},
                {'name': 'TOPOLOGY', 'serial_numbers': ['99634140', '99634135'], 'classes': [9, 42]},
            ],
            'monitored_classes': [9, 42],
            'high_priority_keywords': [
                'software', 'mobile', 'application', 'app', 'social',
                'networking', 'platform', 'downloadable', 'online'
            ],
            'similarity': {'min_score': 65},
            'database': {'path': 'data/trademark_monitor.db'},
            'uspto': {
                'data_dir': 'data/uspto_xml',
                'initial_lookback_days': 30
            },
            'alerts': {
                'email': {'enabled': False},
                'slack': {'enabled': False}
            },
            'logging': {'level': 'INFO'}
        }

    def _setup_logging(self):
        """Configure logging."""
        log_config = self.config.get('logging', {})
        log_level = getattr(logging, log_config.get('level', 'INFO').upper())
        log_file = log_config.get('file', 'logs/trademark_monitor.log')

        # Create logs directory
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_format)
        root_logger.addHandler(console_handler)

        # File handler with rotation
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=log_config.get('max_size_mb', 10) * 1024 * 1024,
            backupCount=log_config.get('backup_count', 5)
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(console_format)
        root_logger.addHandler(file_handler)

        logger.info("Logging configured")

    def _init_components(self):
        """Initialize all system components."""
        # Database
        db_path = self.config.get('database', {}).get('path', 'data/trademark_monitor.db')
        self.db = TrademarkDatabase(db_path)

        # Data fetcher
        uspto_config = self.config.get('uspto', {})
        self.fetcher = USPTODataFetcher(
            data_dir=uspto_config.get('data_dir', 'data/uspto_xml'),
            api_key=os.environ.get('USPTO_API_KEY')
        )

        # XML Parser
        self.parser = USPTOXMLParser()

        # Similarity analyzer
        sim_config = self.config.get('similarity', {})
        sim_config['watch_patterns'] = [r'^TOPO', r'TOPO$', r'^TOPOLOGY', r'TOPOL', r'TOPO.*LOGY']
        self.similarity = TrademarkSimilarity(sim_config)

        # Set our marks in similarity analyzer
        our_marks = [tm['name'] for tm in self.config.get('trademarks', [])]
        self.similarity.set_our_marks(our_marks)

        # Alert system
        self.alerts = AlertSystem(self.config.get('alerts', {}))

        logger.info("All components initialized")

    def _register_our_trademarks(self):
        """Register our trademarks in the database."""
        for tm in self.config.get('trademarks', []):
            for serial in tm.get('serial_numbers', []):
                self.db.add_our_trademark(
                    name=tm['name'],
                    serial_number=serial,
                    classes=tm.get('classes', [])
                )
        logger.info(f"Registered {len(self.config.get('trademarks', []))} trademarks to monitor")

    def run(self, days_back: int = None, use_sample_data: bool = False) -> Dict[str, Any]:
        """
        Run the monitoring process.

        Args:
            days_back: Number of days to look back (defaults to config)
            use_sample_data: Use mock data for testing

        Returns:
            Summary of the monitoring run
        """
        logger.info("=" * 60)
        logger.info("Starting trademark monitoring run")
        logger.info("=" * 60)

        # Start tracking run
        run_id = self.db.start_monitoring_run()

        try:
            # Determine date range
            if days_back is None:
                days_back = self.config.get('uspto', {}).get('initial_lookback_days', 7)

            # Fetch data
            if use_sample_data:
                files = self._generate_sample_data(days_back)
            else:
                files = self._fetch_data(days_back)

            # Process files
            stats = self._process_files(files)

            # Send alerts for new conflicts
            alert_results = self._send_alerts()

            # Update run status
            self.db.update_monitoring_run(
                run_id,
                files_processed=stats['files_processed'],
                filings_processed=stats['filings_processed'],
                conflicts_found=stats['conflicts_found'],
                status='completed'
            )

            summary = {
                'run_id': run_id,
                'status': 'completed',
                'files_processed': stats['files_processed'],
                'filings_processed': stats['filings_processed'],
                'conflicts_found': stats['conflicts_found'],
                'alerts_sent': alert_results,
                'timestamp': datetime.now().isoformat()
            }

            logger.info("=" * 60)
            logger.info(f"Monitoring run completed: {stats['conflicts_found']} conflicts found")
            logger.info("=" * 60)

            return summary

        except Exception as e:
            logger.error(f"Monitoring run failed: {e}", exc_info=True)
            self.db.update_monitoring_run(
                run_id,
                status='failed',
                error_message=str(e)
            )
            raise

    def _fetch_data(self, days_back: int) -> List[Path]:
        """Fetch USPTO data files."""
        logger.info(f"Fetching data for last {days_back} days")

        results = self.fetcher.get_recent_files(days=days_back)

        files = []
        for date, path in results:
            if path:
                files.append(path)
                logger.info(f"  {date.strftime('%Y-%m-%d')}: Downloaded")
            else:
                logger.debug(f"  {date.strftime('%Y-%m-%d')}: Not available")

        logger.info(f"Fetched {len(files)} files")
        return files

    def _generate_sample_data(self, days_back: int) -> List[Path]:
        """Generate sample data for testing."""
        logger.info(f"Generating sample data for {days_back} days")

        mock_fetcher = MockUSPTOFetcher(
            self.config.get('uspto', {}).get('data_dir', 'data/uspto_xml')
        )

        files = []
        for i in range(days_back):
            date = datetime.now() - timedelta(days=i)
            if date.weekday() < 5:  # Skip weekends
                path = mock_fetcher.create_sample_data(date, num_records=50)
                files.append(path)

        logger.info(f"Generated {len(files)} sample files")
        return files

    def _process_files(self, files: List[Path]) -> Dict[str, int]:
        """Process downloaded files and find conflicts."""
        stats = {
            'files_processed': 0,
            'filings_processed': 0,
            'conflicts_found': 0
        }

        target_classes = self.config.get('monitored_classes', [9, 42])
        priority_keywords = self.config.get('high_priority_keywords', [])

        for file_path in files:
            logger.info(f"Processing: {file_path.name}")

            # Parse file
            self.parser.reset_stats()
            records = list(self.parser.parse_zip_file(str(file_path)))

            parse_stats = self.parser.get_stats()
            logger.info(f"  Parsed {parse_stats['parsed']} records ({parse_stats['errors']} errors)")

            # Filter by classes first
            relevant_records = list(filter_by_classes(iter(records), target_classes))
            logger.info(f"  {len(relevant_records)} records in target classes")

            # Analyze each relevant record
            for record in relevant_records:
                serial = record.get('serial_number')

                # Skip if already processed
                if self.db.is_filing_processed(serial):
                    continue

                # Store the filing
                self.db.add_processed_filing(record, str(file_path.name))
                stats['filings_processed'] += 1

                # Check for similarity
                analysis = self.similarity.full_analysis(
                    record,
                    target_classes=target_classes,
                    priority_keywords=priority_keywords
                )

                if analysis:
                    # Found a potential conflict!
                    self.db.add_flagged_conflict(analysis)
                    stats['conflicts_found'] += 1
                    logger.warning(
                        f"  ⚠️ CONFLICT: {record.get('mark_text')} "
                        f"(Score: {analysis['similarity_score']:.1f}%, "
                        f"Matched: {analysis['matched_trademark']})"
                    )

            stats['files_processed'] += 1

        return stats

    def _send_alerts(self) -> Dict[str, bool]:
        """Send alerts for new conflicts."""
        new_conflicts = self.db.get_new_conflicts_for_alert()

        if not new_conflicts:
            logger.info("No new conflicts to alert")
            return {'email': False, 'slack': False}

        logger.info(f"Sending alerts for {len(new_conflicts)} new conflicts")

        # Get summary for alert
        summary = {
            'files_processed': len(self.fetcher.get_local_files()),
            'filings_processed': self.db.get_processed_filings_count()
        }

        # Send alerts
        results = self.alerts.send_conflict_alert(new_conflicts, summary)

        # Mark conflicts as alerted
        for conflict in new_conflicts:
            self.db.mark_conflict_alerted(conflict['id'])
            if results.get('email') or results.get('slack'):
                self.db.log_alert(
                    conflict['id'],
                    'email' if results.get('email') else 'slack',
                    True
                )

        return results

    def check_our_marks_status(self) -> List[Dict[str, Any]]:
        """
        Check the current status of our trademark applications.
        """
        results = []
        for tm in self.config.get('trademarks', []):
            for serial in tm.get('serial_numbers', []):
                status = self.fetcher.get_trademark_status(serial)
                result = {
                    'name': tm['name'],
                    'serial_number': serial,
                    'status': status or 'Unknown',
                    'tsdr_link': self.fetcher.get_tsdr_link(serial)
                }
                results.append(result)
                self.db.update_our_trademark_status(serial, status or 'Unknown')

        return results

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get data for the dashboard."""
        return {
            'stats': self.db.get_dashboard_stats(),
            'recent_conflicts': self.db.get_flagged_conflicts(limit=20),
            'recent_runs': self.db.get_recent_runs(limit=10),
            'our_trademarks': self.db.get_our_trademarks(),
            'conflict_stats': self.db.get_conflict_stats()
        }

    def dismiss_conflict(self, conflict_id: int, notes: str = None):
        """Dismiss a flagged conflict."""
        self.db.update_conflict_status(conflict_id, 'dismissed', notes)
        logger.info(f"Dismissed conflict {conflict_id}")

    def mark_conflict_reviewed(self, conflict_id: int, notes: str = None):
        """Mark a conflict as reviewed."""
        self.db.update_conflict_status(conflict_id, 'reviewed', notes)
        logger.info(f"Marked conflict {conflict_id} as reviewed")

    def mark_conflict_action_taken(self, conflict_id: int, notes: str = None):
        """Mark a conflict as action taken."""
        self.db.update_conflict_status(conflict_id, 'action_taken', notes)
        logger.info(f"Marked conflict {conflict_id} as action taken")


def create_monitor(config_path: str = None) -> TrademarkMonitor:
    """Factory function to create a configured monitor instance."""
    return TrademarkMonitor(config_path=config_path)


if __name__ == "__main__":
    # Run a test monitoring cycle
    monitor = TrademarkMonitor()

    # Run with sample data for testing
    print("\nRunning monitoring with sample data...")
    results = monitor.run(days_back=3, use_sample_data=True)

    print("\n" + "=" * 60)
    print("MONITORING RESULTS")
    print("=" * 60)
    print(f"Files processed: {results['files_processed']}")
    print(f"Filings processed: {results['filings_processed']}")
    print(f"Conflicts found: {results['conflicts_found']}")

    # Show conflicts
    conflicts = monitor.db.get_flagged_conflicts()
    if conflicts:
        print("\nFlagged Conflicts:")
        for c in conflicts[:5]:
            print(f"  - {c['mark_text']} (Score: {c['similarity_score']:.1f}%, Matched: {c['matched_trademark']})")
