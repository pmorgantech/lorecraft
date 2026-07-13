"""Coalescing policy for gateway `DeliveryDirective`s (Rust-port Phase 3c).

Design decision 10 (coalescing is Tier 2 *policy*) + decision 11 (Python owns the
payload semantics, Rust stays payload-blind): Rust's outbound-queue *mechanism*
keep-latest-collapses queued frames that share a non-``None`` ``coalesce_key`` and
never coalesces keyless frames. **Which** frames are safe to collapse is a policy
decision about payload meaning — so it lives here, on the Python side, in ONE
auditable place.

This is deliberately the *only* module that inspects a directive ``payload``'s
``type`` to decide coalescing. Every directive-building site
(``DirectiveConnectionManager`` for command effects, ``GatewayPushManager`` for
autonomous broadcasts, and the admin sink) calls :func:`coalesce_key_for` rather
than deciding for itself, so the whole policy can be read and changed in one spot.

Policy:

- ``state_change`` / panel-refresh payloads are *idempotent* — they tell a client
  "re-render these panels from current state", so two successive refreshes of the
  same panel set collapse to the latest with no lost information. They are keyed.
- ``content_changed`` is the admin console's panel-refresh nudge ("re-query this
  resource with your current filters") — idempotent in exactly the same way, keyed
  per affected resource.
- Everything else — ``feed_append``, chat, ``player_joined``/``player_left``,
  ``player_connected``/``player_disconnected``, ``connected``, narration,
  ``audit_appended``, clock ticks — is a *discrete* event that must all arrive, so
  it is never coalesced (``None``).
"""

from __future__ import annotations

from lorecraft.types import JsonValue


def coalesce_key_for(payload: JsonValue) -> str | None:
    """Return the Tier 2 coalescing key for a directive ``payload``, or ``None``.

    A non-``None`` key marks the frame as keep-latest-coalescible in Rust's
    outbound queue against other queued frames sharing that key *for the same
    recipient*; ``None`` means "never coalesce — every one of these matters".

    The key must never collapse frames that carry *different* information. For a
    ``state_change`` that means keying on the affected-panel signature: two
    refreshes of the same panel set collapse, but refreshes of *different* panel
    sets keep distinct keys and both survive. For ``content_changed`` the key
    includes the affected resource for the same reason.
    """
    if not isinstance(payload, dict):
        return None
    ptype = payload.get("type")
    if ptype == "state_change":
        affected = payload.get("affected_panels")
        if isinstance(affected, list):
            panels = ",".join(sorted(str(p) for p in affected))
        else:
            panels = ""
        return f"state_change:{panels}"
    if ptype == "content_changed":
        resource = payload.get("resource")
        return f"content_changed:{resource if isinstance(resource, str) else ''}"
    return None
