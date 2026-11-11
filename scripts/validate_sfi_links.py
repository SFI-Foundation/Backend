#!/usr/bin/env python3
"""Revalidate public links using a local import report; does not modify a database."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from catalog_links import validate_links


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--import-report', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.import_report.read_text())
    result = validate_links(report['entries'])
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(f'Checked {result["checked"]}; verified current {result["verified_current"]}')
    return 1 if result['discovery_failures'] else 0


if __name__ == '__main__':
    main()
