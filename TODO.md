# Improvement Backlog

Ideas for future improvements. These are not implemented yet.

## Download options

- Reorganize `download_options.json` into clearly separated `general`,
  `video`, and `audio` settings. Keep options near the mode where they apply,
  and document the new structure and any migration considerations.

## Download caching

- Explore caching downloaded video sources in the system temporary directory
  for five minutes. Reusing a cached video should extend its lifetime by
  another five minutes. Since the downloader process may exit before the cache
  expires, determine a reliable cleanup strategy across runs (for example,
  removing expired entries on later runs) and account for storage limits and
  concurrent downloads.

## Warning investigation

- Investigate the source of the output warning
  ``<string>:1: SyntaxWarning: invalid decimal literal``. Identify which code
  generates the string being parsed, determine whether the warning indicates a
  real bug, and fix or document it accordingly.
