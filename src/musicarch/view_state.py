from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(slots=True)
class PageResult:
    indices: list[int]
    total_records: int
    total_filtered: int
    page_size: int
    page_index: int
    total_pages: int


class RecordViewState:
    """Pure-Python state helper for filter/sort/pagination."""

    def __init__(self) -> None:
        self.records: list[dict] = []

    def set_records(self, records: list[dict]) -> None:
        self.records = records

    def build(
        self,
        *,
        status_filter: str,
        keyword: str,
        sort_key: str,
        descending: bool,
        page_size: int,
        page_index: int,
    ) -> PageResult:
        keyword_lower = keyword.strip().lower()

        filtered: list[int] = []
        for idx, record in enumerate(self.records):
            if status_filter != "全部" and str(record.get("status", "")) != status_filter:
                continue

            if keyword_lower:
                haystack = " ".join(
                    [
                        str(record.get("old_file_name", "")),
                        str(record.get("new_file_name", "")),
                        str(record.get("cloud_match_result", "")),
                    ]
                ).lower()
                if keyword_lower not in haystack:
                    continue

            filtered.append(idx)

        filtered.sort(
            key=lambda i: str(self.records[i].get(sort_key, "")).lower(),
            reverse=descending,
        )

        safe_page_size = max(1, page_size)
        total_filtered = len(filtered)
        total_pages = max(1, math.ceil(total_filtered / safe_page_size))

        safe_page_index = max(0, min(page_index, total_pages - 1))
        start = safe_page_index * safe_page_size
        end = start + safe_page_size

        return PageResult(
            indices=filtered[start:end],
            total_records=len(self.records),
            total_filtered=total_filtered,
            page_size=safe_page_size,
            page_index=safe_page_index,
            total_pages=total_pages,
        )
