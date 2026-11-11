#!/usr/bin/env python3
"""Revalidate public links; optionally persist document states to an explicit DB."""

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
    parser.add_argument(
        '--database',
        help='Optional explicit URI: persist document states only; never inferred from app configuration',
    )
    args = parser.parse_args()
    report = json.loads(args.import_report.read_text())
    snapshots = {}
    if args.database:
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session

        from model.sfi_spec import SfiCatalogEntry

        engine = create_engine(args.database)
        with Session(engine) as session:
            for entry in report['entries']:
                old = session.get(SfiCatalogEntry, entry['spec_number'])
                if old:
                    snapshots[entry['spec_number']] = old.payload
                    entry.update(json.loads(old.payload))
    result = validate_links(report['entries'])
    if args.database:
        from catalog import retain_document_history

        # Network checks run outside write transactions. Recheck snapshots
        # under row locks; concurrent edits cannot acquire stale approval.
        with Session(engine) as session:
            try:
                for entry in report['entries']:
                    old = session.execute(
                        select(SfiCatalogEntry)
                        .where(SfiCatalogEntry.spec_number == entry['spec_number'])
                        .with_for_update()
                    ).scalar_one_or_none()
                    if old is None:
                        continue
                    payload = json.loads(old.payload)
                    document = entry['document']
                    if old.payload != snapshots.get(entry['spec_number']):
                        document = {
                            'status': 'needs_review',
                            'reason': 'catalog_changed_during_validation',
                        }
                    payload['document_history'] = retain_document_history(
                        payload, document
                    )
                    payload['document'] = document
                    old.payload = json.dumps(
                        payload, sort_keys=True, ensure_ascii=False
                    )
                session.commit()
            except Exception:
                session.rollback()
                raise
        engine.dispose()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(f'Checked {result["checked"]}; verified current {result["verified_current"]}')
    return (
        1
        if (
            result['discovery_failures']
            or not result['checked']
            or any(r['status'] != 'verified_current' for r in result['results'])
        )
        else 0
    )


if __name__ == '__main__':
    sys.exit(main())
