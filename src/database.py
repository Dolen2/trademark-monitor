"""
Database module for trademark monitoring system.
Handles SQLite storage for processed trademarks, flagged conflicts, and alert history.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


class TrademarkDatabase:
    """SQLite database handler for trademark monitoring."""

    def __init__(self, db_path: str = "data/trademark_monitor.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _init_database(self):
        """Initialize database tables."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Table for our monitored trademarks
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS our_trademarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    serial_number TEXT UNIQUE NOT NULL,
                    registration_number TEXT,
                    classes TEXT NOT NULL,  -- JSON array
                    filing_date DATE,
                    status TEXT,
                    last_checked TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Table for all processed trademark filings
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_filings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    serial_number TEXT UNIQUE NOT NULL,
                    mark_text TEXT,
                    filing_date DATE,
                    classes TEXT,  -- JSON array
                    goods_services TEXT,
                    applicant_name TEXT,
                    applicant_address TEXT,
                    status_code TEXT,
                    mark_type TEXT,
                    processed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    xml_source_file TEXT
                )
            """)

            # Table for flagged potential conflicts
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS flagged_conflicts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    serial_number TEXT NOT NULL,
                    mark_text TEXT NOT NULL,
                    matched_trademark TEXT NOT NULL,  -- Our trademark it matched
                    similarity_score REAL NOT NULL,
                    similarity_reasons TEXT,  -- JSON with reasons
                    classes TEXT,
                    goods_services TEXT,
                    applicant_name TEXT,
                    filing_date DATE,
                    flagged_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'new',  -- new, reviewed, dismissed, action_taken
                    notes TEXT,
                    alert_sent BOOLEAN DEFAULT FALSE,
                    UNIQUE(serial_number, matched_trademark)
                )
            """)

            # Table for alert history
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alert_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conflict_id INTEGER,
                    alert_type TEXT NOT NULL,  -- email, slack
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    success BOOLEAN,
                    error_message TEXT,
                    FOREIGN KEY (conflict_id) REFERENCES flagged_conflicts(id)
                )
            """)

            # Table for monitoring runs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS monitoring_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    files_processed INTEGER DEFAULT 0,
                    filings_processed INTEGER DEFAULT 0,
                    conflicts_found INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'running',  -- running, completed, failed
                    error_message TEXT
                )
            """)

            # Indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_processed_serial ON processed_filings(serial_number)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_processed_date ON processed_filings(filing_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_flagged_status ON flagged_conflicts(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_flagged_serial ON flagged_conflicts(serial_number)")

            logger.info(f"Database initialized at {self.db_path}")

    # ==================== Our Trademarks ====================

    def add_our_trademark(self, name: str, serial_number: str, classes: List[int],
                          registration_number: str = None, filing_date: str = None,
                          status: str = "pending") -> int:
        """Add one of our trademarks to monitor."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO our_trademarks
                (name, serial_number, registration_number, classes, filing_date, status, last_checked)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (name, serial_number, registration_number, json.dumps(classes),
                  filing_date, status, datetime.now().isoformat()))
            return cursor.lastrowid

    def get_our_trademarks(self) -> List[Dict[str, Any]]:
        """Get all our monitored trademarks."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM our_trademarks ORDER BY name")
            rows = cursor.fetchall()
            return [self._row_to_dict(row, parse_json=['classes']) for row in rows]

    def update_our_trademark_status(self, serial_number: str, status: str):
        """Update status of our trademark."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE our_trademarks
                SET status = ?, last_checked = ?
                WHERE serial_number = ?
            """, (status, datetime.now().isoformat(), serial_number))

    # ==================== Processed Filings ====================

    def is_filing_processed(self, serial_number: str) -> bool:
        """Check if a filing has already been processed."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM processed_filings WHERE serial_number = ?",
                (serial_number,)
            )
            return cursor.fetchone() is not None

    def add_processed_filing(self, filing: Dict[str, Any], source_file: str = None) -> int:
        """Add a processed trademark filing."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO processed_filings
                (serial_number, mark_text, filing_date, classes, goods_services,
                 applicant_name, applicant_address, status_code, mark_type, xml_source_file)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                filing.get('serial_number'),
                filing.get('mark_text'),
                filing.get('filing_date'),
                json.dumps(filing.get('classes', [])),
                filing.get('goods_services'),
                filing.get('applicant_name'),
                filing.get('applicant_address'),
                filing.get('status_code'),
                filing.get('mark_type'),
                source_file
            ))
            return cursor.lastrowid

    def get_processed_filings_count(self) -> int:
        """Get total number of processed filings."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM processed_filings")
            return cursor.fetchone()[0]

    def get_recent_filings(self, days: int = 7, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recently processed filings."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM processed_filings
                WHERE processed_date >= datetime('now', ?)
                ORDER BY processed_date DESC
                LIMIT ?
            """, (f'-{days} days', limit))
            rows = cursor.fetchall()
            return [self._row_to_dict(row, parse_json=['classes']) for row in rows]

    # ==================== Flagged Conflicts ====================

    def add_flagged_conflict(self, conflict: Dict[str, Any]) -> int:
        """Add a flagged potential conflict."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO flagged_conflicts
                (serial_number, mark_text, matched_trademark, similarity_score,
                 similarity_reasons, classes, goods_services, applicant_name, filing_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                conflict.get('serial_number'),
                conflict.get('mark_text'),
                conflict.get('matched_trademark'),
                conflict.get('similarity_score'),
                json.dumps(conflict.get('similarity_reasons', {})),
                json.dumps(conflict.get('classes', [])),
                conflict.get('goods_services'),
                conflict.get('applicant_name'),
                conflict.get('filing_date')
            ))
            return cursor.lastrowid

    def get_flagged_conflicts(self, status: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get flagged conflicts, optionally filtered by status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("""
                    SELECT * FROM flagged_conflicts
                    WHERE status = ?
                    ORDER BY flagged_date DESC
                    LIMIT ?
                """, (status, limit))
            else:
                cursor.execute("""
                    SELECT * FROM flagged_conflicts
                    ORDER BY flagged_date DESC
                    LIMIT ?
                """, (limit,))
            rows = cursor.fetchall()
            return [self._row_to_dict(row, parse_json=['similarity_reasons', 'classes']) for row in rows]

    def get_new_conflicts_for_alert(self) -> List[Dict[str, Any]]:
        """Get new conflicts that haven't been alerted yet."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM flagged_conflicts
                WHERE alert_sent = FALSE AND status = 'new'
                ORDER BY similarity_score DESC
            """)
            rows = cursor.fetchall()
            return [self._row_to_dict(row, parse_json=['similarity_reasons', 'classes']) for row in rows]

    def mark_conflict_alerted(self, conflict_id: int):
        """Mark a conflict as having been alerted."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE flagged_conflicts SET alert_sent = TRUE WHERE id = ?",
                (conflict_id,)
            )

    def update_conflict_status(self, conflict_id: int, status: str, notes: str = None):
        """Update the status of a flagged conflict."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if notes:
                cursor.execute(
                    "UPDATE flagged_conflicts SET status = ?, notes = ? WHERE id = ?",
                    (status, notes, conflict_id)
                )
            else:
                cursor.execute(
                    "UPDATE flagged_conflicts SET status = ? WHERE id = ?",
                    (status, conflict_id)
                )

    def get_conflict_stats(self) -> Dict[str, int]:
        """Get statistics on flagged conflicts."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM flagged_conflicts
                GROUP BY status
            """)
            stats = {row['status']: row['count'] for row in cursor.fetchall()}
            cursor.execute("SELECT COUNT(*) FROM flagged_conflicts")
            stats['total'] = cursor.fetchone()[0]
            return stats

    # ==================== Alert History ====================

    def log_alert(self, conflict_id: int, alert_type: str, success: bool, error_message: str = None):
        """Log an alert attempt."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO alert_history (conflict_id, alert_type, success, error_message)
                VALUES (?, ?, ?, ?)
            """, (conflict_id, alert_type, success, error_message))

    # ==================== Monitoring Runs ====================

    def start_monitoring_run(self) -> int:
        """Start a new monitoring run and return its ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO monitoring_runs (start_time) VALUES (?)",
                (datetime.now().isoformat(),)
            )
            return cursor.lastrowid

    def update_monitoring_run(self, run_id: int, files_processed: int = None,
                              filings_processed: int = None, conflicts_found: int = None,
                              status: str = None, error_message: str = None):
        """Update a monitoring run."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            updates = []
            params = []
            if files_processed is not None:
                updates.append("files_processed = ?")
                params.append(files_processed)
            if filings_processed is not None:
                updates.append("filings_processed = ?")
                params.append(filings_processed)
            if conflicts_found is not None:
                updates.append("conflicts_found = ?")
                params.append(conflicts_found)
            if status:
                updates.append("status = ?")
                params.append(status)
                if status in ('completed', 'failed'):
                    updates.append("end_time = ?")
                    params.append(datetime.now().isoformat())
            if error_message:
                updates.append("error_message = ?")
                params.append(error_message)

            if updates:
                params.append(run_id)
                cursor.execute(
                    f"UPDATE monitoring_runs SET {', '.join(updates)} WHERE id = ?",
                    params
                )

    def get_recent_runs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent monitoring runs."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM monitoring_runs
                ORDER BY start_time DESC
                LIMIT ?
            """, (limit,))
            return [self._row_to_dict(row) for row in cursor.fetchall()]

    # ==================== Utilities ====================

    def _row_to_dict(self, row: sqlite3.Row, parse_json: List[str] = None) -> Dict[str, Any]:
        """Convert a sqlite3.Row to a dictionary, optionally parsing JSON fields."""
        result = dict(row)
        if parse_json:
            for field in parse_json:
                if field in result and result[field]:
                    try:
                        result[field] = json.loads(result[field])
                    except (json.JSONDecodeError, TypeError):
                        pass
        return result

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Get comprehensive stats for dashboard."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Total processed filings
            cursor.execute("SELECT COUNT(*) FROM processed_filings")
            total_processed = cursor.fetchone()[0]

            # Filings by class
            cursor.execute("""
                SELECT classes, COUNT(*) as count
                FROM processed_filings
                WHERE classes IS NOT NULL
                GROUP BY classes
            """)

            # Conflicts by status
            conflict_stats = self.get_conflict_stats()

            # Recent run info
            cursor.execute("""
                SELECT * FROM monitoring_runs
                ORDER BY start_time DESC
                LIMIT 1
            """)
            last_run = cursor.fetchone()

            return {
                'total_processed': total_processed,
                'conflict_stats': conflict_stats,
                'last_run': self._row_to_dict(last_run) if last_run else None,
                'our_trademarks': self.get_our_trademarks()
            }
