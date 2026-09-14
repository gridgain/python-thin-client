# Changelog

This file records the changes that a user of `pygridgain` can see: new API, changed
behaviour, and fixed defects. Internal work appears here only when it changes what the
client does.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Changed

- **`Cache.vector()` and `AioCache.vector()` now use `k` as the default `page_size`**
  (before: `1`). A vector query returns at most `k` rows, so the whole result now arrives in
  one page. The old default made one server round trip for every result row: a `k=10` query
  used 20 socket reads, and now it uses 2. This is a **public API behaviour change**. Pass
  `page_size` explicitly to keep a smaller page.
  ([GG-49932](https://ggsystems.atlassian.net/browse/GG-49932))
- **`Cache.vector()` and `AioCache.vector()` reject a non-positive `k` with `ValueError`.**
  Before, the client sent the request and the server refused it. The server keeps the upper
  bound, because `GRIDGAIN_VECTOR_MAX_K` is configurable there.
  ([GG-49932](https://ggsystems.atlassian.net/browse/GG-49932))
- Response parsing shares one ctypes class for each distinct structure shape, instead of
  building a new class for every element of every row. Vector queries that carry values are
  20% to 28% faster, and the client keeps no dead classes. There is no API change.
  ([GG-49932](https://ggsystems.atlassian.net/browse/GG-49932))
