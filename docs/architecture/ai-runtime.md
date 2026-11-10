# AI runtime

## Shape of the problem

A desktop AI system has four jobs that are usually conflated and should not be:

1. **Store models** — multi-gigabyte immutable artefacts, often several variants
   of the same base model at different quantisations.
2. **Route inference** — decide what runs where, and ensure exactly one thing
   owns the GPU.
3. **Manage context** — conversation, retrieved documents, per-application state.
4. **Execute tools** — the dangerous one. Arbitrary command execution suggested
   by a stochastic model.

These live in one daemon (`agentd`) behind one API, but with separate internal
components and separate privilege levels.

## Process model

| Process | User | Role | Long-lived |
|---------|------|------|-----------|
| `agentd` | `aios` | API, registry, routing, policy, sessions | yes |
| `aios-model-runner` | `aios-model` | Wraps llama.cpp; one per loaded model | while loaded |
| CUDA container | `aios-model` | vLLM / PyTorch workloads | on demand |
| `bwrap` sandbox | session user | One process tree per tool call | per call |

`agentd` is deliberately unprivileged and has no GPU access. It cannot load a
model itself; it asks a runner to. This means a compromise of the daemon does not
grant GPU or file access — it grants the ability to *request* those things,
which the policy engine can refuse.

Implementation language is undecided (Go is the fast path for a supervisor with
an HTTP surface and static musl linking; Rust is preferable if llama.cpp bindings
become first-class in-process). Recorded as an open question in
[../README.md](../README.md#open-questions).

## API surface

Two listeners:

- **Unix socket** `/run/user/$UID/aios.sock`, mode 0600 — the native API used by
  the assistant UI and CLI.
- **Loopback HTTPS** `127.0.0.1:11434` — an OpenAI-compatible subset
  (`/v1/chat/completions`, `/v1/embeddings`, `/v1/models`) so existing tooling
  works unchanged.

No listener binds a non-loopback address by default. Exposing inference to the
LAN is an explicit, separately confirmed setting, because a local model server
with tool access on an open port is a remote code execution service.

## GPU arbitration

The naive design — let every runner take the device — fails in a predictable way:
the compositor, a chat model, and an embedding model contend, and the desktop
stutters or the model OOMs.

Instead, a single **GPU warden** inside `agentd` owns the device and hands out
exclusive leases:

```
lease = { model_id, vram_bytes, priority, granted_at }
```

Rules:

- One inference lease at a time. A second request waits or preempts.
- Preemption order: LRU, then lowest priority. Never preempt the compositor.
- A lease reserves VRAM headroom (default 768 MiB) for the desktop.
- Llama.cpp is asked to unload rather than killed, so KV cache can be reused.
- If an allocation would exceed free VRAM, the warden returns a typed error the
  UI can explain ("needs 9.2 GiB, 6.1 GiB free"), not a crash.

This is also the reason model runners are separate processes: eviction must be
observable and graceful, and a shared-address-space runner cannot be evicted.

## Model store

Content-addressed, on its own volume so it can be moved between machines.

```
/models/
  blobs/sha256/ab/cd/abcdef...        # actual bytes, immutable
  manifests/
    llama-3.2-3b-instruct-q4_k_m.json
    llm-jp-3-13b-q5_k_m.json
  refs/                               # pinned names -> manifest digest
  tmp/                                # in-progress downloads
```

A manifest records:

```json
{
  "schema": 1,
  "name": "llama-3.2-3b-instruct",
  "format": "gguf",
  "quant": "Q4_K_M",
  "blobs": [{ "sha256": "…", "size": 2147483648, "role": "weights" }],
  "context_length": 131072,
  "architecture": "llama",
  "capabilities": ["chat", "tools"],
  "license": "Llama-3.2-Community",
  "source": "https://…",
  "created": "2026-11-10T00:00:00Z"
}
```

Why content-addressing rather than a flat directory of files:

- Two manifests can share a blob (same weights, different chat template), so
  deduplication is free and correct.
- Integrity is checkable at any time without a separate checksum file.
- Garbage collection is refcount-by-manifest, and cannot delete a blob that a
  pinned name still resolves to.
- Downloads resume and verify chunk-by-chunk.

Blobs are stored uncompressed. GGUF weights are already quantised and do not
compress; zstd on them wastes CPU and slows mmap. Manifests and tokeniser
metadata are compressed, since they are text and small.

A model that is mid-download lives in `tmp/` and is invisible to the registry
until every blob verifies.

## Context and sessions

SQLite at `/var/lib/aios/sessions.db`, WAL mode.

- One row per message, immutable, append-only.
- Embeddings for retrieval stay beside the messages, never in the OS image.
- Per-application context is namespaced; the assistant cannot read another
  application's thread unless the user grants it.
- The database is encrypted when the state volume is encrypted. There is no
  separate password.

Retention is a first-class setting: "keep everything", "keep 30 days", "keep
nothing". The default is 30 days, because an unbounded local transcript of
everything you have done is a liability nobody asked for.

## Tool execution

The flow, in order, with the gate at each step:

```
model emits tool_call
  -> schema validation (does this tool exist, are args well-typed)
  -> policy check (is this tool allowed for this session and this origin)
  -> user confirmation if the action is not pre-approved
  -> sandbox construction (mounts, namespaces, seccomp, egress)
  -> execute with timeout and output cap
  -> return result as untrusted data
```

The last step matters architecturally. Tool output is **data**. It is returned to
the model inside explicit delimiters, never concatenated into a system prompt,
and never re-parsed as an instruction. A file the user downloaded can contain
text that looks like a command; that text is a string, not a directive.

See [ADR-0008](../adr/0008-tool-sandbox.md) for the sandbox mechanics.

## Threat model

| Asset | Threat | Mitigation |
|-------|--------|------------|
| User files | Prompt injection causes a destructive tool call | Sandbox with explicit bind mounts; confirmation for writes; no ambient `$HOME` |
| Credentials | Model reads `~/.ssh`, browser profile, tokens | Deny-by-default paths; secrets never in assistant context |
| GPU | Malicious container escapes to host | Rootless Podman, no privileged mode, device access only via lease |
| Model store | Tampered weights (backdoored model) | SHA-256 on every blob, verified on load; provenance in manifest |
| Network | Exfiltration via tool egress | Default-deny egress; allowlist proxy; per-call audit log |
| OS image | Persistence of a malicious change | Read-only verified root; updates are signed and atomic |

The uncomfortable but honest statement: **a local model with tool access is a
remote code execution primitive that the user invited in.** Everything above
exists to make the blast radius a decision rather than an accident.
