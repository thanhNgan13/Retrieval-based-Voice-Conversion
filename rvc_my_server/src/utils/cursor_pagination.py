from typing import Any, Callable, Iterable, Optional

DEFAULT_LIMIT = 10
MAX_LIMIT = 100


def normalize_limit(limit: Optional[int]) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    try:
        n = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    if n < 1:
        return 1
    if n > MAX_LIMIT:
        return MAX_LIMIT
    return n


def build_pagination_block(
    items: list,
    limit: int,
    id_field: str = "id",
) -> dict:
    has_next = len(items) > limit
    page = items[:limit]
    next_cursor = page[-1].get(id_field) if has_next and page else None
    return {
        "limit": limit,
        "hasNext": has_next,
        "nextCursor": next_cursor,
        "currentCount": len(page),
    }


def apply_cursor_query(
    query,
    start_after: Optional[str],
    limit: int,
    get_doc_snapshot: Optional[Callable[[str], Any]] = None,
):
    """
    Apply Firestore cursor (start_after) + limit (+1 to detect hasNext).
    `get_doc_snapshot` returns the DocumentSnapshot for the cursor id, if needed.
    """
    if start_after and get_doc_snapshot is not None:
        snap = get_doc_snapshot(start_after)
        if snap is not None:
            query = query.start_after(snap)
    return query.limit(limit + 1)
