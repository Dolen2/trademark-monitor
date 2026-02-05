#!/usr/bin/env python3
"""
Test script to verify the trademark monitoring system works correctly.
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

def test_database():
    """Test database initialization and operations."""
    print("\n" + "=" * 60)
    print("Testing Database Module")
    print("=" * 60)

    from src.database import TrademarkDatabase

    db = TrademarkDatabase('data/test_trademark.db')

    # Test adding our trademarks
    db.add_our_trademark('TOPO', '99634122', [9, 42])
    db.add_our_trademark('TOPO', '99634130', [9, 42])
    db.add_our_trademark('TOPOLOGY', '99634140', [9, 42])
    db.add_our_trademark('TOPOLOGY', '99634135', [9, 42])

    # Verify
    our_tms = db.get_our_trademarks()
    print(f"✓ Added {len(our_tms)} trademark records")

    # Test adding a processed filing
    db.add_processed_filing({
        'serial_number': '99999999',
        'mark_text': 'TESTMARK',
        'filing_date': '2026-02-01',
        'classes': [9],
        'goods_services': 'Computer software',
        'applicant_name': 'Test Corp'
    })
    print("✓ Added test filing")

    # Test adding a conflict
    db.add_flagged_conflict({
        'serial_number': '99888888',
        'mark_text': 'TOPOWORLD',
        'matched_trademark': 'TOPO',
        'similarity_score': 85.5,
        'similarity_reasons': {'starts_with': "Starts with 'TOPO'"},
        'classes': [9, 42],
        'goods_services': 'Social networking software',
        'applicant_name': 'Tech Startup Inc',
        'filing_date': '2026-02-01'
    })
    print("✓ Added test conflict")

    # Get stats
    stats = db.get_dashboard_stats()
    print(f"✓ Dashboard stats: {stats['total_processed']} processed, {stats['conflict_stats'].get('total', 0)} conflicts")

    return True


def test_similarity():
    """Test similarity matching algorithms."""
    print("\n" + "=" * 60)
    print("Testing Similarity Module")
    print("=" * 60)

    from src.similarity import TrademarkSimilarity, check_similarity

    analyzer = TrademarkSimilarity({
        'min_score': 60,
        'watch_patterns': [r'^TOPO', r'TOPO$', r'^TOPOLOGY', r'TOPOL']
    })

    test_cases = [
        ("TOPO", True, "Exact match"),
        ("TOPOLOGY", True, "Exact match"),
        ("TOPOWORLD", True, "Starts with TOPO"),
        ("TOPOLOGIX", True, "Starts with TOPOLOGY"),
        ("MYTOPO", True, "Contains TOPO"),
        ("TOPOSPHERE", True, "Starts with TOPO"),
        ("TOPOLINK", True, "Starts with TOPO"),
        ("APPLE", False, "Unrelated mark"),
        ("MICROSOFT", False, "Unrelated mark"),
        ("GREENTECH", False, "Unrelated mark"),
    ]

    passed = 0
    for mark, should_match, reason in test_cases:
        results = analyzer.analyze(mark)
        matched = len(results) > 0
        status = "✓" if matched == should_match else "✗"

        if matched:
            score = max(r.score for r in results)
            print(f"{status} {mark}: Score {score:.1f}% ({reason})")
        else:
            print(f"{status} {mark}: No match ({reason})")

        if matched == should_match:
            passed += 1

    print(f"\nPassed {passed}/{len(test_cases)} test cases")
    return passed == len(test_cases)


def test_xml_parser():
    """Test XML parsing functionality."""
    print("\n" + "=" * 60)
    print("Testing XML Parser Module")
    print("=" * 60)

    from src.xml_parser import USPTOXMLParser

    parser = USPTOXMLParser()

    # Create test XML
    test_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <trademark-applications-daily>
        <case-file>
            <serial-number>99123456</serial-number>
            <filing-date>20260115</filing-date>
            <mark-identification>TOPOMAP</mark-identification>
            <mark-drawing-code>4</mark-drawing-code>
            <status-code>620</status-code>
            <classification>
                <international-code>9</international-code>
                <goods-services-description>Computer software for social networking</goods-services-description>
            </classification>
            <party-name>
                <name>Test Company Inc.</name>
            </party-name>
        </case-file>
        <case-file>
            <serial-number>99123457</serial-number>
            <filing-date>20260115</filing-date>
            <mark-identification>RANDOMMARK</mark-identification>
            <classification>
                <international-code>25</international-code>
                <goods-services-description>Clothing</goods-services-description>
            </classification>
        </case-file>
    </trademark-applications-daily>
    """

    # Parse it
    records = list(parser._parse_xml_content(test_xml.encode(), "test.xml"))

    print(f"✓ Parsed {len(records)} records from test XML")

    for record in records:
        print(f"  - {record['mark_text']}: Serial {record['serial_number']}, Classes {record['classes']}")

    stats = parser.get_stats()
    print(f"✓ Parser stats: {stats['parsed']} parsed, {stats['errors']} errors")

    return len(records) == 2


def test_mock_data():
    """Test sample data generation."""
    print("\n" + "=" * 60)
    print("Testing Sample Data Generation")
    print("=" * 60)

    from src.data_fetcher import MockUSPTOFetcher

    fetcher = MockUSPTOFetcher('data/test_uspto_xml')

    # Generate sample file
    sample_path = fetcher.create_sample_data(datetime.now(), num_records=20)

    print(f"✓ Created sample file: {sample_path.name}")

    # Verify it can be parsed
    from src.xml_parser import USPTOXMLParser
    parser = USPTOXMLParser()
    records = list(parser.parse_zip_file(str(sample_path)))

    print(f"✓ Parsed {len(records)} records from sample file")

    # Check for expected conflict-triggering marks
    conflict_marks = [r for r in records if 'TOPO' in (r.get('mark_text') or '').upper()]
    print(f"✓ Found {len(conflict_marks)} marks containing 'TOPO'")

    return len(records) > 0


def test_full_workflow():
    """Test the full monitoring workflow."""
    print("\n" + "=" * 60)
    print("Testing Full Monitoring Workflow")
    print("=" * 60)

    from src.monitor import TrademarkMonitor

    # Create test config
    config = {
        'trademarks': [
            {'name': 'TOPO', 'serial_numbers': ['99634122', '99634130'], 'classes': [9, 42]},
            {'name': 'TOPOLOGY', 'serial_numbers': ['99634140', '99634135'], 'classes': [9, 42]},
        ],
        'monitored_classes': [9, 42],
        'high_priority_keywords': ['software', 'mobile', 'social', 'networking', 'app'],
        'similarity': {'min_score': 60},
        'database': {'path': 'data/test_full_workflow.db'},
        'uspto': {'data_dir': 'data/test_uspto_xml'},
        'alerts': {'email': {'enabled': False}, 'slack': {'enabled': False}},
        'logging': {'level': 'WARNING', 'file': 'logs/test.log'}
    }

    monitor = TrademarkMonitor(config=config)

    # Run with sample data
    print("Running monitoring scan with sample data...")
    results = monitor.run(days_back=3, use_sample_data=True)

    print(f"\n✓ Monitoring run completed:")
    print(f"  - Files processed: {results['files_processed']}")
    print(f"  - Filings analyzed: {results['filings_processed']}")
    print(f"  - Conflicts found: {results['conflicts_found']}")

    # Show conflicts
    if results['conflicts_found'] > 0:
        conflicts = monitor.db.get_flagged_conflicts()
        print(f"\n  Flagged conflicts:")
        for c in conflicts[:5]:
            print(f"    • {c['mark_text']} (Score: {c['similarity_score']:.1f}%) - matched {c['matched_trademark']}")

    return results['files_processed'] > 0


def main():
    """Run all tests."""
    print("=" * 60)
    print("  TRADEMARK MONITOR - System Test")
    print("=" * 60)

    tests = [
        ("Database", test_database),
        ("Similarity", test_similarity),
        ("XML Parser", test_xml_parser),
        ("Sample Data", test_mock_data),
        ("Full Workflow", test_full_workflow),
    ]

    results = []
    for name, test_fn in tests:
        try:
            passed = test_fn()
            results.append((name, passed))
        except Exception as e:
            print(f"\n✗ {name} test failed with error: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("  TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, p in results if p)
    total = len(results)

    for name, status in results:
        symbol = "✓" if status else "✗"
        print(f"  {symbol} {name}")

    print(f"\n  {passed}/{total} tests passed")

    if passed == total:
        print("\n  ✓ All tests passed! System is ready for deployment.")
    else:
        print("\n  ✗ Some tests failed. Please review the errors above.")

    return passed == total


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
