#!/usr/bin/env python3
"""Check that PR title severity matches the most severe commit in the PR.

This script ensures that breaking changes in commits are reflected in the PR title,
preventing accidental minor/patch releases when a major bump is required.

Severity levels (highest to lowest):
- major: commits with `!` suffix (e.g., `feat!:`, `fix(scope)!:`) or BREAKING CHANGE footer
- minor: `feat:` commits (new features)
- patch: `fix:`, `chore:`, `refactor:`, `perf:`, `style:`, `test:`, `docs:`, `build:`, `ci:`

Usage:
    python scripts/check_pr_severity.py --pr-title "feat!: breaking change" --base-ref origin/main
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

# Conventional commit pattern
# Matches: type(scope)!: description or type!: description or type: description
COMMIT_PATTERN = re.compile(
    r'^(?P<type>\w+)(?:\([^)]+\))?(?P<breaking>!)?\s*:\s*(?P<description>.+)$'
)

# Types that trigger a minor bump (new features)
MINOR_TYPES = {'feat'}

# Types that trigger a patch bump
PATCH_TYPES = {
    'fix',
    'chore',
    'refactor',
    'perf',
    'style',
    'test',
    'docs',
    'build',
    'ci',
}

SEVERITY_ORDER = {'major': 3, 'minor': 2, 'patch': 1, 'none': 0}


def get_commit_severity(message: str) -> str:
    """Determine the severity level of a single commit message."""
    match = COMMIT_PATTERN.match(message.strip())
    if not match:
        return 'none'

    commit_type = match.group('type').lower()
    has_breaking = match.group('breaking') == '!'

    if has_breaking:
        return 'major'

    if commit_type in MINOR_TYPES:
        return 'minor'
    if commit_type in PATCH_TYPES:
        return 'patch'

    return 'none'


def check_for_breaking_change_footer(commit_hash: str) -> bool:
    """Check if a commit has BREAKING CHANGE in its footer."""
    result = subprocess.run(
        ['git', 'log', '-1', '--format=%B', commit_hash],
        capture_output=True,
        text=True,
        check=True,
    )
    body = result.stdout

    return bool(re.search(r'^BREAKING[ -]CHANGE\s*:', body, re.MULTILINE))


def get_commits_in_range(base_ref: str) -> list[tuple[str, str]]:
    """Get all commits between base_ref and HEAD."""
    result = subprocess.run(
        ['git', 'log', f'{base_ref}..HEAD', '--format=%H %s'],
        capture_output=True,
        text=True,
        check=True,
    )

    commits = []
    for line in result.stdout.strip().split('\n'):
        if line:
            parts = line.split(' ', 1)
            if len(parts) == 2:
                commits.append((parts[0], parts[1]))

    return commits


def get_max_commit_severity(base_ref: str) -> tuple[str, list[str]]:
    """Determine the maximum severity across all commits in the PR."""
    commits = get_commits_in_range(base_ref)

    if not commits:
        return 'none', []

    max_severity = 'none'
    breaking_commits = []

    for commit_hash, subject in commits:
        severity = get_commit_severity(subject)

        if severity != 'major' and check_for_breaking_change_footer(commit_hash):
            severity = 'major'

        if severity == 'major':
            breaking_commits.append(subject)

        if SEVERITY_ORDER[severity] > SEVERITY_ORDER[max_severity]:
            max_severity = severity

    return max_severity, breaking_commits


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Check PR title severity matches commit severity'
    )
    parser.add_argument(
        '--pr-title',
        required=True,
        help='The PR title to check',
    )
    parser.add_argument(
        '--base-ref',
        required=True,
        help='The base ref to compare against (e.g., origin/main)',
    )

    args = parser.parse_args()

    pr_severity = get_commit_severity(args.pr_title)
    commit_severity, breaking_commits = get_max_commit_severity(args.base_ref)

    print(f'PR title: {args.pr_title}')
    print(f'PR title severity: {pr_severity}')
    print(f'Max commit severity: {commit_severity}')

    if breaking_commits:
        print('\nBreaking commits found:')
        for commit in breaking_commits:
            print(f'  - {commit}')

    if SEVERITY_ORDER[pr_severity] < SEVERITY_ORDER[commit_severity]:
        print(
            f'\n❌ ERROR: PR title indicates "{pr_severity}" bump, '
            f'but commits require "{commit_severity}" bump.'
        )
        print('\nTo fix this:')
        if commit_severity == 'major':
            print('  Add "!" to your PR title type, e.g.: feat!: or fix(scope)!:')
        elif commit_severity == 'minor':
            print('  Use "feat:" prefix in your PR title')
        return 1

    print(
        f'\n✅ PR title severity ({pr_severity}) matches or exceeds '
        f'commit severity ({commit_severity})'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
