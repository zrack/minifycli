# Synthetic log-retention fixtures

These are handcrafted regression fixtures, not captures from installed test
frameworks and not evidence of production compression rates. They reproduce
Jest/Vitest-shaped summaries mixed with application output.

- `jest-application-success.log`: the original checkmark deletion issue, all
  three success-marker variants, timing-looking application messages, and a
  plain `PASS` application message. Only the column-zero test-file header is
  removed in the corresponding `.expected.log`.
- `jest-application-failure.log`: application messages before a failure and
  success-looking assertion diagnostics inside the failure block. The failure
  suffix remains byte-for-byte unchanged.
- `vitest-application-success.log`: individual success lines and file-summary
  lookalikes are ambiguous, so the complete fixture must remain unchanged.
- `jest-application-crlf.log`: CRLF line endings with no final newline. Its
  expected output preserves both properties after removing the file header.

`tests/log_retention.rs` runs each fixture as stdout, stderr, and both streams
through a disposable executable named `npm`. Exit status is also preserved.
