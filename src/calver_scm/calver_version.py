from __future__ import annotations

from typing import Literal

from packaging.version import Version


class CalverVersion(Version):
    """A `Version` helper that preserves CalVer-specific zero padding."""

    def _pep440_suffix(self) -> str:
        """Render non-release PEP 440 segments in canonical order."""
        suffix = ""

        if self.pre is not None:
            pre_tag, pre_num = self.pre
            suffix += f"{pre_tag}{pre_num}"

        if self.post is not None:
            suffix += f".post{self.post}"

        if self.dev is not None:
            suffix += f".dev{self.dev}"

        if self.local is not None:
            suffix += f"+{self.local}"

        return suffix

    def format_from_base(self, *, base: str, patch: int) -> str:
        """Render version from a pre-computed CalVer base and patch value."""
        return f"{base}.{patch}{self._pep440_suffix()}"

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

        return f"{base}{self._pep440_suffix()}"
