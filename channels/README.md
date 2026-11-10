# Channel files

One file per channel — `nightly.json`, `weekly.json`, `stable.json` — each a few
hundred bytes naming **one digest**. See
[ADR-0015](../docs/adr/0015-release-channels-by-promotion.md).

There are no files here yet. They appear the first time `promote` runs, which is
correct: a channel that names a digest that does not exist is worse than a
channel that does not exist.

## Rules

- **Only `.github/workflows/promote.yml` writes this directory.** Protect it with
  a ruleset and `CODEOWNERS`; anyone who can write a channel file can redirect
  every device in the fleet.
- **A promotion is one commit.** `git log channels/stable.json` is the audit
  trail: who promoted what, when, and what it replaced.
- **A file is signed.** Devices verify the embedded signature against a public
  key baked into the image, then install the digest it names. GitHub's
  immutability protects releases; it does not protect this pointer.
- **`supersedes` means withdrawn**, not "the previous digest". Normal promotion
  history lives in git. A digest in `supersedes` must never be staged, on any
  channel.
- **Never edit these files by hand.** If a promotion is wrong, revert the commit
  and let the next promotion run; if a release is bad, use `withdraw`, which
  moves the pointer back and records the bad digest.
