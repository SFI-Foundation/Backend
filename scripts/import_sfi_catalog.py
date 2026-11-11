#!/usr/bin/env python3
"""Explicit private catalog importer. Defaults to dry-run; never imports main."""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from catalog_import import build_import, apply_import


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--source-dir',
        type=Path,
        default=Path(os.environ.get('SFI_PRIVATE_DATA_DIR', '../sfi-private-data')),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--apply', action='store_true')
    parser.add_argument(
        '--database',
        help='Required explicit URI for apply; independent of app environment',
    )
    parser.add_argument(
        '--report',
        type=Path,
        required=True,
        help='Write outside Git; contains private provenance',
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Reject missing sources/documents, conflicts, or parser warnings',
    )
    parser.add_argument(
        '--catalog',
        type=Path,
        default=Path(__file__).resolve().parents[1] / 'sfi_specs.json',
    )
    parser.add_argument(
        '--validate-links',
        action='store_true',
        help='Fetch ONLY public official SFI pages/PDFs; no private uploads',
    )
    args = parser.parse_args()
    report = build_import(args.source_dir, json.loads(args.catalog.read_text()))
    if args.validate_links:
        from catalog_links import validate_links

        report['link_validation'] = validate_links(report['entries'])
    blocked = bool(report['errors'] or not report['entries'])
    if args.strict:
        blocked |= bool(
            report['missing_sources']
            or report['conflicts']
            or report['warnings']
            or report['counts']['unmatched']
            or report['counts']['unmatched_documents']
            or any(e['warnings'] for e in report['entries'])
        )
    report['mode'] = 'apply' if args.apply else 'dry-run'
    if (
        args.validate_links
        and report['link_validation']['discovery_failures']
        and args.strict
    ):
        blocked = True
    if args.apply and not blocked:
        if not args.database:
            parser.error(
                '--apply requires --database; production URI is never inferred'
            )
        from sqlalchemy import create_engine, inspect
        from sqlalchemy.orm import Session

        engine = create_engine(args.database)
        if not {'sfi_specs', 'sfi_catalog_entries'} <= set(
            inspect(engine).get_table_names()
        ):
            parser.error(
                'Migrate metadata and prepare the legacy spec table first; no automatic schema initialization'
            )
        with Session(engine) as session:
            try:
                report['upsert'] = apply_import(session, report)
            except Exception as exc:
                report['errors'].append(
                    {'source': 'database', 'error': type(exc).__name__}
                )
                blocked = True
    report['blocked'] = blocked
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: report[k] for k in ('mode', 'counts', 'blocked')}))
    return 1 if blocked else 0


if __name__ == '__main__':
    main()
