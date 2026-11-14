"""Thumbnail buffer: filled in the background around the viewing position, capped in bytes.

Distance of a photo is measured from the visible page: 0 for photos on the page,
growing with the number of steps away. Loading goes nearest first. When the cap
is reached, a nearer photo can replace a farther one, so the buffer is always a
window around the viewing position. The visible page itself is never evicted.
"""

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

from viewer.paging import PAGE_SIZE
from viewer.thumbnails import Photo, make_thumbnail

MEMORY_CAP_BYTES = 2 * 1024**3  # 2 GiB of thumbnail bytes on a 16 GB machine
WORKERS = 4


class ThumbnailBuffer:
    """Hold thumbnails for an ordered list of photos, loading them in the background.

    Args:
        order: Photos in display order. Positions are indices into this list.
        cap_bytes: Maximum total size of the buffered thumbnails.
        loader: Builds one thumbnail from a photo. Defaults to `make_thumbnail`.
    """

    def __init__(
        self,
        order: list[Photo],
        cap_bytes: int = MEMORY_CAP_BYTES,
        loader: Callable[[Photo], bytes] = make_thumbnail,
    ) -> None:
        self._order = order
        self._cap = cap_bytes
        self._loader = loader
        self._items: dict[int, bytes] = {}
        self._used = 0
        self._focus = 0
        self._generation = 0  # bumped by every focus(); stale workers stop
        self._futures: list[Future] = []
        self._error: BaseException | None = None
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=WORKERS)

    @property
    def used_bytes(self) -> int:
        """Total size of the buffered thumbnails in bytes."""
        with self._lock:
            return self._used

    def focus(self, index: int) -> None:
        """Move the viewing position to `index` and restart loading around it.

        The page starts at `index` and spans PAGE_SIZE photos. Queued work from
        the previous position is cancelled.

        Raises:
            IndexError: If `index` is outside the photo list.
        """
        if not 0 <= index < len(self._order):
            raise IndexError(f"Index {index} outside 0..{len(self._order) - 1}")
        with self._lock:
            self._focus = index
            self._generation += 1
            generation = self._generation
            for future in self._futures:
                future.cancel()
            missing = sorted(
                (i for i in range(len(self._order)) if i not in self._items),
                key=lambda i: (self._distance(i), abs(i - index)),
            )
            futures = [self._pool.submit(self._load, i, generation) for i in missing]
            self._futures = futures
        # Outside the lock: a finished future runs its callback at once, and that callback takes the lock.
        for future in futures:
            future.add_done_callback(self._record_error)

    def get(self, index: int) -> bytes:
        """Return the thumbnail of photo `index`, building it now if it is not buffered.

        Raises:
            ValueError: If the visible page cannot fit in the memory cap.
            Exception: The first error raised by a background load.
        """
        with self._lock:
            if self._error is not None:
                raise self._error
            data = self._items.get(index)
        if data is not None:
            return data
        data = self._loader(self._order[index])
        with self._lock:
            if not self._store(index, data) and self._distance(index) == 0:
                raise ValueError(f"Memory cap of {self._cap} bytes cannot hold the visible page")
        return data

    def close(self) -> None:
        """Stop background loading and release the worker threads."""
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _distance(self, index: int) -> int:
        """Steps from the visible page to `index` (0 when it is on the page). Caller holds the lock."""
        last = self._focus + PAGE_SIZE - 1
        return max(self._focus - index, index - last, 0)

    def _store(self, index: int, data: bytes) -> bool:
        """Insert a thumbnail, evicting farther ones to make room. Caller holds the lock.

        Returns:
            False if the thumbnail does not fit even after evicting every farther one.
        """
        if index in self._items:
            return True
        while self._used + len(data) > self._cap:
            far = max(self._items, key=self._distance, default=None)
            if far is None or self._distance(far) <= self._distance(index):
                return False
            self._used -= len(self._items.pop(far))
        self._items[index] = data
        self._used += len(data)
        return True

    def _worth_building(self, index: int) -> bool:
        """Cheap pre-check before decoding a photo. Caller holds the lock."""
        if self._used < self._cap:
            return True
        far = max(self._items, key=self._distance, default=None)
        return far is not None and self._distance(far) > self._distance(index)

    def _load(self, index: int, generation: int) -> None:
        """Worker task: build one thumbnail if it is still wanted by this generation."""
        with self._lock:
            if generation != self._generation or index in self._items or not self._worth_building(index):
                return
        data = self._loader(self._order[index])
        with self._lock:
            if generation == self._generation:
                self._store(index, data)

    def _record_error(self, future: Future) -> None:
        """Keep the first background error so the next get() re-raises it."""
        if not future.cancelled() and future.exception() is not None:
            with self._lock:
                self._error = self._error or future.exception()
