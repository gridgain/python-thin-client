# Changelog

This file records the changes that a user of `pygridgain` can see: new API, changed
behaviour, and fixed defects. Internal work appears here only when it changes what the
client does.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Changed

- **The client now needs Python 3.9 or newer.** The metadata said 3.7, but the wheels, the
  tested versions and the documentation have all said 3.9 for several releases. `pip` now
  reports this instead of installing a client that was not built for the interpreter.
- **The installed package no longer contains a top-level `tests` package.** The wheel put
  the client's tests into `site-packages/tests`, where they clashed with any other project
  that ships a `tests` package. Only `pygridgain` is installed now. The source
  distribution still contains the tests.
- **The client no longer pins exact versions of its dependencies, and no longer needs
  `contextvars`.** `attrs` and `tzlocal` were pinned with `==`, so the client could not be
  installed together with an application that needed another version. They are now
  minimum versions (`attrs>=23.2.0`, `tzlocal>=4.3.1`). `contextvars` has been in the
  standard library since Python 3.7, so the backport only added `immutables` for nothing.
- The package metadata moved from `setup.py` to `pyproject.toml`, and the license now uses
  the PEP 639 fields instead of the deprecated license classifier. `setup.py` still builds
  the C extension. Building from a source distribution now needs setuptools 77 or newer,
  which `pip` installs on its own.
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
- Vector query responses decode in one pass, directly from the response buffer. The vector
  cursors no longer unwrap each value a second time. Queries that carry values are a further
  18% faster at `k=100`; rows are unchanged. Two response shapes change at the edges:
  - An asyncio legacy `(key, value)` row is now a `tuple`. Before, it was a `list`. The
    synchronous client always returned a `tuple`, so the two clients now agree.
  - `pygridgain.api.sql.vector()` returns legacy rows as a list of `(key, value)` tuples.
    Before, it returned a dictionary. The wire order stays the same, and the cursor gives
    the same rows as before. This function is low-level; `Cache.vector()` is unchanged.

  ([GG-49932](https://ggsystems.atlassian.net/browse/GG-49932))

### Fixed

- **A string that contains a NUL character (U+0000) is no longer truncated.** The string
  codec used a ctypes `c_char` array, which stops at the first NUL. The client cut such a
  string on read and on write, so `'a\x00b'` went to the server as `'a'` and came back as
  `'a'`. This applies to every string the client sends or receives, not only to vector
  queries. ([GG-49932](https://ggsystems.atlassian.net/browse/GG-49932))
