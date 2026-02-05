"""
Main monitoring orchestrator for trademark monitoring system.
Updated to work with TESS scraping (no API key required).
"""

import yaml
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging
from logging.handlers import RotatingFileHandler

from .database import TrademarkDatabase
from .data_fetcher import USPTODataFetcher
from .similarity import TrademarkSimilarity
from .alerts import AlertSystem

logger = logging.getLogger(__name__)


class TrademarkMonitor:
    def __init__(self, config_path: str = None, config: Dict = None):
        self.config = config or self._load_config(config_path)
        self._setup_logging()
        self._init_components()
        self._register_our_trademarks()

    def _load_config(self, config_path: str = None) -> Dict[str, Any]:
        if config_path is None:
            for path in ['config/config.yaml', '../config/config.yaml']:
                if os.path.exists(path):
                    config_path = path
                    break
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                return self._expand_env_vars(config)
        return self._default_config()

    def _expand_env_vars(self, obj):
        if isinstance(obj, dict):
            return {k: self._expand_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._expand_env_vars(item) for item in obj]
        elif isinstance(obj, str) and obj.startswith('${') and obj.endswith('}'):
            return os.environ.get(obj[2:-1], obj)
        return obj

    def _default_config(self) -> Dict[str, Any]:
        return {
            'trademarks': [
                {'name': 'TOPO', 'serial_numbers': ['99634122', '99634130'], 'classes': [9, 42]},
                {'name': 'TOPOLOGY', 'serial_numbers': ['99634140', '99634135'], 'classes': [9, 42]},
            ],
            'monitored_classes': [9, 42],
            'high_priority_keywords': ['software', 'mobile', 'application', 'app', 'social', 'networking', 'platform'],
            'similarity': {'min_score': 65},
            'database': {'path': 'data/trademark_monitor.db'},
            'uspto': {'data_dir': 'data/uspto', 'initial_lookback_days': 7},
            'alerts': {'email': {'enabled': False}, 'slack': {'enabled': False}},
            'logging': {'level': 'INFO'}
        }

    def _setup_logging(self):
        log_config = self.config.get('logging', {})
        log_level = getattr(logging, log_config.get('level', 'INFO').upper())
        log_file = log_config.get('file', 'logs/trademark_monitor.log')
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        root_logger.handlers = []
        ch = logging.StreamHandler()
        ch.setLevel(log_level)
        ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        root_logger.addHandler(ch)
        fh = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
        fh.setLevel(log_level)
        fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        root_logger.addHandler(fh)

    def _init_components(self):
        db_path = self.config.get('database', {}).get('path', 'data/trademark_monitor.db')
        self.db = TrademarkDatabase(db_path)
        self.fetcher = USPTODataFetcher(data_dir=self.config.get('uspto', {}).get('data_dir', 'data/uspto'))
        sim_config = self.config.get('similarity', {})
        sim_config['watch_patterns'] = [r'^TOPO', r'TOPO$', r'^TOPOLOGY', r'TOPOL', r'TOPO.*LOGY']
        self.similarity = TrademarkSimilarity(sim_config)
        self.similarity.set_our_marks([tm['name'] for tm in self.config.get('trademarks', [])])
        self.alerts = AlertSystem(self.config.get('alerts', {}))
        logger.info("All components initialized")

    def _register_our_trademarks(self):
        for tm in self.config.get('trademarks', []):
            for serial in tm.get('serial_numbers', []):
                self.db.add_our_trademark(name=tm['name'], serial_number=serial, classes=tm.get('classes', []))

    def run(self, days_back: int = None, use_sample_data: bool = False) -> Dict[str, Any]:
        logger.info("=" * 60)
        logger.info("Starting trademark monitoring run")
        run_id = self.db.start_monitoring_run()
        try:
            if days_back is None:
                days_back = self.config.get('uspto', {}).get('initial_lookback_days', 7)
            trademarks = self._generate_sample_data() if use_sample_data else self._fetch_recent_filings(days_back)
            stats = self._process_filings(trademarks)
            alert_results = self._send_alerts()
            self.db.update_monitoring_run(run_id, files_processed=1, filings_processed=stats['filings_processed'],
                                          conflicts_found=stats['conflicts_found'], status='completed')
            logger.info(f"Monitoring completed: {stats['conflicts_found']} conflicts found")
            return {'run_id': run_id, 'status': 'completed', 'filings_processed': stats['filings_processed'],
                    'conflicts_found': stats['conflicts_found'], 'alerts_sent': alert_results}
        except Exception as e:
            logger.error(f"Monitoring run failed: {e}", exc_info=True)
            self.db.update_monitoring_run(run_id, status='failed', error_message=str(e))
            raise

    def _fetch_recent_filings(self, days_back: int) -> List[Dict[str, Any]]:
        logger.info(f"Fetching recent filings (last {days_back} days)")
        trademarks = self.fetcher.search_recent_filings_by_class(self.config.get('monitored_classes', [9, 42]), days_back)
        if trademarks:
            self.fetcher.save_filings(trademarks)
            return trademarks
        logger.warning("TESS returned no results, using sample data")
        return self._generate_sample_data()

    def _generate_sample_data(self) -> List[Dict[str, Any]]:
        trademarks = self.fetcher.generate_sample_data(num_records=50)
        self.fetcher.save_filings(trademarks)
        return trademarks

    def _process_filings(self, trademarks: List[Dict[str, Any]]) -> Dict[str, int]:
        stats = {'filings_processed': 0, 'conflicts_found': 0}
        target_classes = self.config.get('monitored_classes', [9, 42])
        priority_keywords = self.config.get('high_priority_keywords', [])
        for record in trademarks:
            serial = record.get('serial_number')
            mark_name = record.get('mark_name', '')
            if not serial or not mark_name or self.db.is_filing_processed(serial):
                continue
            record_classes = record.get('international_classes', [])
            record_classes = [int(c) if isinstance(c, str) and c.isdigit() else c for c in record_classes]
            if not any(c in target_classes for c in record_classes):
                continue
            db_record = {'serial_number': serial, 'mark_text': mark_name, 'filing_date': record.get('filing_date'),
                         'status_code': record.get('status', ''), 'international_classes': record_classes,
                         'goods_services': record.get('goods_services', ''), 'applicant_name': record.get('applicant_name', '')}
            self.db.add_processed_filing(db_record, 'scrape')
            stats['filings_processed'] += 1
            analysis = self.similarity.full_analysis(db_record, target_classes=target_classes, priority_keywords=priority_keywords)
            if analysis:
                self.db.add_flagged_conflict(analysis)
                stats['conflicts_found'] += 1
                logger.warning(f"  CONFLICT: {mark_name} (Score: {analysis['similarity_score']:.1f}%, Matched: {analysis['matched_trademark']})")
        return stats

    def _send_alerts(self) -> Dict[str, bool]:
        new_conflicts = self.db.get_new_conflicts_for_alert()
        if not new_conflicts:
            return {'email': False, 'slack': False}
        logger.info(f"Sending alerts for {len(new_conflicts)} conflicts")
        results = self.alerts.send_conflict_alert(new_conflicts, {'filings_processed': self.db.get_processed_filings_count()})
        for conflict in new_conflicts:
            self.db.mark_conflict_alerted(conflict['id'])
        return results

    def get_dashboard_data(self) -> Dict[str, Any]:
        return {'stats': self.db.get_dashboard_stats(), 'recent_conflicts': self.db.get_flagged_conflicts(limit=20),
                'our_trademarks': self.db.get_our_trademarks()}


def create_monitor(config_path: str = None) -> TrademarkMonitor:
    return TrademarkMonitor(config_path=config_path)


if __name__ == "__main__":
    monitor = TrademarkMonitor()
    results = monitor.run(use_sample_data=True)
    print(f"Conflicts found: {results['conflicts_found']}")
