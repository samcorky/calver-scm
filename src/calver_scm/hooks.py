"""Entry points for git hooks run through pre-commit or prek."""

from __future__ import annotations

import os
import sys

from calver_scm.cli import main as cli_main

TAG_REF_PREFIX = "refs/tags/"


def main() -> int:
    """Validate the tag a pre-push hook is pushing; ignore any other push.

    pre-commit and prek name the ref being pushed in `PRE_COMMIT_REMOTE_BRANCH`
    (`refs/tags/v2026.4.3` for a tag). The tag is checked as `validate --tag`
    checks it, against the settings in the current directory. It sees one ref per
    run, and git runs no pre-push hook at all for a tag on a commit the remote
    already has, so this guards new tags, not every tag.
    """
    ref = os.environ.get("PRE_COMMIT_REMOTE_BRANCH")
    if ref is None:
        print(
            "error: PRE_COMMIT_REMOTE_BRANCH is not set; this hook is meant to run "
            "in the pre-push stage",
            file=sys.stderr,
        )
        return 2
    if not ref.startswith(TAG_REF_PREFIX):
        return 0
    return cli_main(["validate", ref.removeprefix(TAG_REF_PREFIX), "--tag"])
