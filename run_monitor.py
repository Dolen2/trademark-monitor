#!/usr/bin/env python3
"""
Main entry point for the Trademark Monitoring System.

Usage:
    python run_monitor.py                    # Run with default settings
    python run_monitor.py --days 14          # Scan last 14 days
    python run_monitor.py --sample           # Use sample data (for testing)
    python run_monitor.py --dashboard        # Launch web dashboard
    python run_monitor.py --schedule         # Run scheduled monitoring
"""

import argparse
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.monitor import TrademarkMonitor
from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser(
        description='Trademark Monitoring System for Relatent, Inc.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_monitor.py                     Run monitoring scan
  python run_monitor.py --days 30           Scan last 30 days
  python run_monitor.py --sample            Test with sample data
  python run_monitor.py --dashboard         Launch web dashboard
  python run_monitor.py --check-status      Check our trademarks' status
  python run_monitor.py --schedule          Run as scheduled service
        """
    )

    parser.add_argument(
        '--days', '-d',
        type=int,
        default=7,
        help='Number of days to scan (default: 7)'
    )

    parser.add_argument(
        '--sample', '-s',
        action='store_true',
        help='Use sample/mock data for testing'
    )

    parser.add_argument(
        '--dashboard',
        action='store_true',
        help='Launch the Streamlit web dashboard'
    )

    parser.add_argument(
        '--check-status',
        action='store_true',
        help='Check status of our trademark applications'
    )

    parser.add_argument(
        '--schedule',
        action='store_true',
        help='Run as scheduled service (continuous monitoring)'
    )

    parser.add_argument(
        '--config', '-c',
        type=str,
        default='config/config.yaml',
        help='Path to configuration file'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Launch dashboard mode
    if args.dashboard:
        launch_dashboard()
        return

    # Initialize monitor
    print("=" * 60)
    print("  TRADEMARK MONITOR - Relatent, Inc.")
    print("  Monitoring: TOPO and TOPOLOGY")
    print("=" * 60)
    print()

    try:
        monitor = TrademarkMonitor(config_path=args.config)
    except Exception as e:
        print(f"Error initializing monitor: {e}")
        sys.exit(1)

    # Check status mode
    if args.check_status:
        print("Checking status of our trademark applications...")
        print("-" * 40)
        results = monitor.check_our_marks_status()
        for r in results:
            print(f"  {r['name']} ({r['serial_number']}): {r['status']}")
            print(f"    → {r['tsdr_link']}")
        return

    # Schedule mode
    if args.schedule:
        run_scheduled(monitor)
        return

    # Normal run mode
    print(f"Scanning USPTO data for last {args.days} days...")
    if args.sample:
        print("(Using sample data for testing)")
    print()

    try:
        results = monitor.run(days_back=args.days, use_sample_data=args.sample)

        print()
        print("=" * 60)
        print("  RESULTS")
        print("=" * 60)
        print(f"  Files processed:   {results['files_processed']}")
        print(f"  Filings analyzed:  {results['filings_processed']}")
        print(f"  Conflicts found:   {results['conflicts_found']}")
        print()

        if results['conflicts_found'] > 0:
            print("⚠️  POTENTIAL CONFLICTS DETECTED!")
            print("-" * 40)
            conflicts = monitor.db.get_flagged_conflicts(status='new')
            for c in conflicts[:10]:
                print(f"  • {c['mark_text']} (Score: {c['similarity_score']:.1f}%)")
                print(f"    Serial: {c['serial_number']}, Matched: {c['matched_trademark']}")
                print(f"    Classes: {c['classes']}")
                print()

            if len(conflicts) > 10:
                print(f"  ... and {len(conflicts) - 10} more. Check the dashboard for details.")
        else:
            print("✓ No new conflicts detected.")

        print()
        print("Run 'python run_monitor.py --dashboard' to view the web interface.")

    except Exception as e:
        print(f"Error during monitoring: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def launch_dashboard():
    """Launch the Streamlit dashboard."""
    import subprocess

    dashboard_path = project_root / 'dashboard' / 'app.py'

    print("Launching Trademark Monitor Dashboard...")
    print("Open http://localhost:8501 in your browser")
    print("Press Ctrl+C to stop")
    print()

    try:
        subprocess.run([
            sys.executable, '-m', 'streamlit', 'run',
            str(dashboard_path),
            '--server.port=8501',
            '--browser.gatherUsageStats=false'
        ])
    except KeyboardInterrupt:
        print("\nDashboard stopped.")


def run_scheduled(monitor):
    """Run monitoring on a schedule."""
    import schedule
    import time

    print("Starting scheduled monitoring service...")
    print("Monitoring will run daily at 8:00 AM")
    print("Press Ctrl+C to stop")
    print()

    def run_job():
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Running scheduled scan...")
        try:
            results = monitor.run(days_back=1)
            print(f"Scan complete: {results['conflicts_found']} conflicts found")
        except Exception as e:
            print(f"Scan failed: {e}")

    # Schedule daily run
    schedule.every().day.at("08:00").do(run_job)

    # Also run immediately on startup
    run_job()

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nScheduled monitoring stopped.")


if __name__ == '__main__':
    main()
