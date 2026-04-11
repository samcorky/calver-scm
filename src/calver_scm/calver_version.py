from __future__ import annotations

from typing import Literal

from packaging.version import Version


class CalverVersion(Version):
    """A `Version` helper that preserves CalVer-specific zero padding."""

    def format(self, *, mode: Literal["month", "day"]) -> str:
        """Render the version using the requested CalVer release shape."""
        release = self.release

        if mode == "day":
            if len(release) == 3:
                year, month, day = release
                patch = 0
            elif len(release) == 4:
                year, month, day, patch = release
            else:
                return str(self)

            base = f"{year}.{month:02d}.{day:02d}.{patch}"
        else:
            if len(release) == 2:
                year, month = release
                patch = 0
            elif len(release) == 3:
                year, month, patch = release
            else:
                return str(self)

            base = f"{year}.{month:02d}.{patch}"

        if self.pre is not None:
            pre_tag, pre_num = self.pre
            base += f"{pre_tag}{pre_num}"

        if self.post is not None:
            base += f".post{self.post}"

        if self.dev is not None:
            base += f".dev{self.dev}"

        if self.local is not None:
            base += f"+{self.local}"

        return base
