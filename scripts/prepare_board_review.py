#!/usr/bin/env python3
"""Prepare a NEW local board-review catalog using the existing import/validator.

Private source evidence stays in the explicit report file. Only the two meeting
PDFs are assessed for public approval. No manufacturer records or jobs are stored.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from catalog_import import apply_import, build_import
from catalog_links import validate_links
from scripts.migrate_sfi_catalog import upgrade
from scripts.phase1_local import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, help='NEW local SQLite URI')
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument(
        '--report', type=Path, required=True, help='Private report outside Git'
    )
    args = parser.parse_args()
    # Existing preparation refuses non-SQLite URIs and existing files.
    prepare(args.database)
    engine = create_engine(args.database)
    upgrade(engine)
    catalog_path = Path(__file__).resolve().parents[1] / 'sfi_specs.json'
    catalog = json.loads(catalog_path.read_text())
    report = build_import(args.source_dir, catalog)
    if report['errors'] or not report['entries']:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
        print('Source import needs review; see the private report.')
        return 1
    selected = [
        entry for entry in report['entries']
        if entry['spec_number'] in {'1.1', '3.3'}
    ]
    report['link_validation'] = validate_links(selected)
    with Session(engine) as session:
        report['upsert'] = apply_import(session, report)
    engine.dispose()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    states = {entry['spec_number']: entry['document']['status'] for entry in selected}
    print(json.dumps({'meeting_pdf_states': states, 'upsert': report['upsert']}))
    return 0 if states == {'1.1': 'verified_current', '3.3': 'verified_current'} else 1


if __name__ == '__main__':
    sys.exit(main())
