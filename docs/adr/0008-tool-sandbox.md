# ADR-0008: Sandbox tool execution with bwrap and seccomp

- **Status:** Proposed
- **Date:** 2026-11-10
- **Deciders:** project owner
- **Supersedes:** —
- **Superseded by:** —

## Context

Tool execution is the feature that makes the assistant an operating-system
component rather than a chat window. It is also the feature that turns a language
model into an attack surface.

The realistic threats are not exotic:

- **Prompt injection.** A web page, a PDF, an email, or a downloaded repository
  contains text that reads as an instruction. The model follows it. This is the
  dominant risk and it is not solvable by better prompting.
- **Confused deputy.** The assistant has the user's privileges; a tool call it
  makes inherits them. Reading `~/.ssh` or a browser cookie database is a single
  plausible mistake.
- **Destructive error.** A model that misreads a request and runs `rm -rf` on the
  wrong path. No adversary required.
- **Egress.** A tool call that quietly sends data somewhere.

Tool calls need to be simultaneously easy (a user says "tidy up my downloads" and
it works) and bounded (it cannot touch anything else).

## Decision

Execute every tool call in a **`bwrap` (bubblewrap) sandbox** with:

- A read-only bind of `/usr` and `/lib`, and nothing else from the OS.
- An empty, private `/tmp`.
- Explicit, per-call bind mounts of exactly the paths the tool declares it needs.
  `$HOME` is never mounted wholesale.
- A private PID, mount, IPC, UTS, and cgroup namespace. No user namespace escape.
- No network by default. Network access is a declared capability routed through a
  filtering proxy with a per-call audit record.
- A `libseccomp` profile denying `io_uring`, `bpf`, `perf_event_open`, `mount`,
  `pivot_root`, `keyctl`, and raw sockets.
- A wall-clock timeout, an output size cap, and a process-count cap.
- Execution as the session user, never root, with no setuid binaries reachable.

The **policy engine** in `agentd` decides, before sandbox construction, whether the
call is permitted at all. The sandbox is the second line of defence, not the first.

### The three-tier permission model

| Tier | Examples | Behaviour |
|------|----------|-----------|
| Read, sandboxed | list a directory, read a file the user opened | auto-approved within declared mounts |
| Write, sandboxed | create a file, move a file | confirmation, with a preview of exact paths |
| System-affecting | install, network, run a downloaded binary, touch credentials | explicit per-call approval, no "remember" option |

The absence of a "don't ask again" for the third tier is deliberate. It is the tier
where injection payloads live.

### Result handling

Tool output is returned to the model as **untrusted data inside explicit
delimiters**. It is never concatenated into a system prompt, never re-parsed as an
instruction, and never used to construct another tool call without passing through
the policy engine again. A file whose contents say "now run `curl … | sh`" is a
string.

## Consequences

### Positive

- A successful injection reaches a filesystem that contains only what the tool
  asked for, and a network it cannot reach.
- A model error with a destructive command fails harmlessly instead of deleting the
  wrong directory.
- Every tool call is auditable: exact mounts, exact egress, exact duration.
- The permission model is simple enough to explain in one screen, which matters
  because users will otherwise click through it.

### Negative / costs

- **Tools that need broad access are painful.** "Reorganise my photo library" needs
  a wide mount, which weakens the sandbox. There is no way to make that both safe
  and frictionless.
- Multi-step tasks become a confirmation stream. Users will find this tedious, and
  the mitigation (pre-declared tool bundles, or a scoped session grant) is exactly
  where the safety margin erodes.
- `bwrap` per call adds startup latency; for many small calls this is measurable.
- Some legitimate tools will not work under the seccomp profile, and diagnosing
  that is developer-hostile.
- Writing and maintaining `libseccomp` profiles across architectures is ongoing
  work with no natural completion.

### Neutral / follow-on

- The audit log becomes a product feature (a visible history of what the assistant
  did) and a support burden.
- Tool authors must declare mounts and capabilities in a manifest, which is a
  contract we now have to version.

## Alternatives considered

**No sandbox, rely on confirmation prompts.** Rejected. Confirmation fatigue is
real and well-documented; users approve the tenth prompt without reading it. A
sandbox bounds the damage when that happens.

**Podman container per tool call.** Rejected as the default. Correct in principle
and stronger isolation, but cold start is seconds rather than milliseconds, and the
common case is "read this file". Retained for tools that genuinely need a different
userland or heavier isolation.

**WebAssembly.** Rejected for v1. Excellent sandbox properties and worth
investigating for pure-computation tools, but it cannot run the shell commands and
native utilities that make the feature useful, and the ecosystem for filesystem-
touching tools is immature.

**Landlock LSM.** Not adopted for v1, but the most promising future direction. It
gives per-process filesystem restriction without namespaces, is unprivileged, and
composes better than mount-based isolation. Revisit once it is uniformly available
on target kernels; it would remove much of the mount ceremony.

**Run as a separate unprivileged user with no namespaces.** Rejected. Limits file
access but not network or process interaction, and requires privilege to set up.

## Follow-ups

- Write the tool manifest schema (declared mounts, capabilities, timeout).
- Build the audit log and the UI that exposes it.
- Define the scoped-grant mechanism for long tasks, and be honest about its risk.
- Evaluate Landlock for a later release.
- Red-team this: write injection payloads against our own tool set before shipping.
- Decide how remote model providers interact with the egress policy — a tool call
  routed through a cloud model has a different trust story.
