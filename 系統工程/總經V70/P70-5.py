#!/usr/bin/env python3
"""Read the existing Family V70 macro feed. No crawling or score calculation.

CLI: python P70-5.py --repo /path/to/LivingWaterAI
Python: load this module with importlib, then call read_macro(repo_path).
The returned dict retains the original family-macro-feed-v3 interface.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SOURCE = Path('系統工程/總經V70/V70_macro_latest.json')
SCHEMA = 'V70.3/family-macro-feed-v3'


def read_macro(repo: str | Path | None = None) -> dict:
    """Return the existing macro JSON unchanged for Family consumers.

    repo is the local GitHub checkout root. With no argument, use the JSON
    beside this script, or locate the repo from the script's parent folders.
    Missing, invalid or unready data raises ValueError/OSError; never fill it.
    """
    if repo is not None:
        source = Path(repo) / SOURCE
    else:
        here = Path(__file__).resolve().parent
        source = here / SOURCE.name
        if not source.is_file():
            source = next((p / SOURCE for p in (here, *here.parents)
                           if (p / SOURCE).is_file()), source)
    with source.open(encoding='utf-8-sig') as stream:
        feed = json.load(stream)
    if not isinstance(feed, dict) or feed.get('schema') != SCHEMA:
        raise ValueError('MACRO_SCHEMA_INVALID')
    verification = feed.get('verification')
    if not isinstance(verification, dict) or verification.get('ready') is not True:
        raise ValueError('MACRO_FEED_NOT_READY')
    if not isinstance(feed.get('indicators'), dict) or not feed['indicators']:
        raise ValueError('MACRO_INDICATORS_MISSING')
    if not isinstance(feed.get('asOf'), str) or not feed['asOf'].strip():
        raise ValueError('MACRO_AS_OF_MISSING')
    return feed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, help='local GitHub checkout root')
    args = parser.parse_args()
    try:
        feed = read_macro(args.repo)
    except (OSError, ValueError) as exc:
        print(json.dumps({'status': 'UNAVAILABLE', 'issue_codes': [str(exc)]},
                         ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(feed, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
