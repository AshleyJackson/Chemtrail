# ADR-0011: Local-first inference with optional cloud routing

- **Status:** Accepted
- **Date:** 2026-11-10
- **Deciders:** project owner
- **Supersedes:** —
- **Superseded by:** —

## Context

Previous documents assumed local inference with no cloud path, and treated
"nothing leaves the device" as a security property of the architecture. The
product owner has stated: **local-first, cloud optional**, with a user-held API
key for a frontier model acceptable for hard tasks.

This changes three things:

1. **The hardware floor drops.** A device that can fall back to a cloud model does
   not need to run a 30B model well to be useful. This partly relieves the VRAM
   constraint that ADR-0002 treated as fixed.
2. **The privacy claim changes from absolute to default.** "Local" becomes the
   default route rather than the only route, and the product must say so
   precisely, because a user who bought it for privacy will otherwise feel
   deceived.
3. **The trust boundary moves outward.** Tool output, file contents and
   conversation history may now be sent to a third party. The egress policy in
   ADR-0008 assumes default-deny; cloud routing is a deliberate, auditable
   exception to it.

## Decision

1. **Local is the default route.** No request leaves the device unless the user
   explicitly selects a cloud route for that request or thread.
2. **Cloud providers are user-configured with the user's own key.** No vendor
   account, no proxy through our servers, no telemetry. Keys live in the OS
   keyring.
3. **Routing is per-request and visible.** The UI always shows which model
   produced an answer, and cloud routes are visually distinct. There is no silent
   fallback: if the local model cannot serve a request, the user is asked.
4. **Cloud-origin responses get a stricter tool policy.** A tool approval granted
   for a local model does not automatically extend to a cloud model, because the
   data leaving the device and the instruction coming back have different trust
   properties.
5. **Egress is explicit and logged.** A cloud route is an allowlisted destination
   in the egress proxy. Every request records what was sent (size, categories)
   and what came back.
6. **Data minimisation before egress.** Attachment and context selection follow a
   "minimum necessary" rule, with a preview of exactly what will be transmitted
   before the first transmission in a thread.
7. **A local model is always present.** There is no cloud-only mode. The device
   must work offline, and an install without a usable local model is not a valid
   configuration.

Rules 2, 3 and 6 are the parts that keep "local-first" honest. Without them the
product is a cloud client with a local cache.

## Consequences

### Positive

- Frontier-quality answers are available without shipping frontier hardware,
  which materially improves the product for hard tasks.
- The hardware floor becomes a quality-of-experience decision rather than a
  hard capability gate.
- Users who cannot run a large model still get a good product; users who can
  never need to send anything anywhere.
- A local fallback means the product degrades rather than fails when offline or
  when a provider has an outage.

### Negative / costs

- **The privacy story is now conditional**, and that is a marketing and support
  burden forever. Every claim must be qualified, and some users will not read the
  qualification.
- Two latency profiles, two failure modes, two cost models. Every UI element that
  shows progress or errors must handle both.
- Cloud routing creates a data-egress audit obligation we did not have before.
- Provider keys are a new secret to store, rotate, and avoid leaking into logs,
  crash reports, or context sent to models.
- The sandbox's default-deny egress rule now has a complex exception, which is
  exactly where policy bugs live.
- Tool-call semantics differ across providers (schema support, parallel calls),
  adding a compatibility layer.

### Neutral / follow-on

- Enables a future "escalate this task" affordance, which is likely to become
  the most-used control in the product.
- The router becomes a real component with its own policy language, not a switch.

## Alternatives considered

**Local only.** Rejected by the product decision, and practically limiting: it
caps answer quality at what the device can run, which on mainstream hardware is a
7–14B model.

**Cloud-first with local fallback.** Rejected. It inverts the product's premise
and makes offline behaviour a degraded afterthought. It also silently sends data,
which contradicts the stated intent.

**Route everything through our own proxy.** Rejected. It centralises user data,
creates a single point of failure and a breach target, and makes us a data
processor with all the obligations that follow. Direct-to-provider with the user's
own key is strictly better for trust.

**Silent automatic escalation when local is slow.** Rejected emphatically. Sending
data without an explicit action is the one behaviour that would destroy the
product's credibility.

## Follow-ups

- Write the routing policy language and the UI that explains it in one sentence.
- Implement key storage in the OS keyring, and audit logs and crash reports for
  key leakage.
- Define the data-minimisation rules and the pre-send preview.
- Extend the sandbox egress model with a per-provider allowlist and an audit
  record.
- Decide whether cloud-routed conversations are stored locally by default, and
  what the retention rule is.
- Revisit ADR-0002: the VRAM floor is now a quality target, not a capability gate.
  State the minimum local model explicitly.
