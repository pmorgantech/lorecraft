"""Browser e2e: level-up feedback in the player UI (Sprint 73.9).

Covers the two pieces of client-visible behaviour that don't already have
integration coverage on the backend side:

- the "You reach level N!" feed line (`MessageType.LEVEL` -> `msg-level`)
  gets distinct visual treatment, mirroring
  `test_gameplay_flows.py::test_help_output_gets_bold_accent_styling`'s
  `.msg-help` check (Sprint 71.4).
- the Stats pane's live re-render on the `stats_update` push shows the new
  level/xp and the skill points granted by the level-up payout, without a
  page reload.

Uses `admin_server` (not `live_server`) so the seeded superadmin can retune
`ProgressionConfig` down to a trivially-reachable threshold via the same
`POST /admin/progression/config` endpoint Task 1's admin-console tests cover.

The level-up trigger is the "Lights in the Square" quest's 50 xp stage
reward (`world_content/world.yaml`'s `investigate_lights` quest), reached the
same way `test_gameplay_flows.py::test_dialogue_choice_starts_quest` starts
it -- deterministic, unlike exploration's `search` command (RNG skill-check
gated).

**Known backend gap worked around here (found verifying this task, reported
separately -- not this agent's lane to fix):** nothing in the engine ever
creates a fresh character's *first* `PlayerStats` row -- not character
creation, not `save`/`load` (an empty snapshot round-trips to another empty
snapshot; `_apply_stats_snapshot` no-ops on `not snapshot`). Every XP/reward
grant (`apply_rewards`, `engine/game/leveling.py`) is correctly gated behind
`ctx.player_repo.stats(player_id) is not None`, so a brand-new character can
never actually level up in production today -- confirmed by direct DB
inspection: `playerstats` stays empty through `save` + `load` + a completed
quest reward. Until that's fixed (PlayerRepo.stats() get-or-create, or an
eager row at character creation -- Backend Engineer's call), this test seeds
the row directly as a test precondition (not a production change) via the
same sqlite file `admin_server` already created, reachable through the
shared per-test `tmp_path` fixture.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlmodel import Session, create_engine, select

from lorecraft.engine.models.player import Player, PlayerStats
from tests.e2e._helpers import create_character, send_command
from tests.e2e.conftest import ADMIN_PASS, ADMIN_USER

pytestmark = pytest.mark.e2e


def _tune_progression_config(base_url: str, **fields: int) -> None:
    token = httpx.post(
        f"{base_url}/admin/auth/token",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
    ).json()["access_token"]
    resp = httpx.post(
        f"{base_url}/admin/progression/config",
        json=fields,
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()


def _seed_player_stats(tmp_path: Path, username: str) -> None:
    """Work around the missing-first-PlayerStats-row gap (see module docstring)
    by inserting one directly into the same sqlite file `admin_server` uses
    (`tmp_path / "e2e-game.db"`, per `tests/e2e/conftest.py`)."""
    engine = create_engine(f"sqlite:///{tmp_path / 'e2e-game.db'}")
    with Session(engine) as session:
        player = session.exec(select(Player).where(Player.username == username)).one()
        session.add(PlayerStats(player_id=player.id))
        session.commit()


def _complete_investigate_lights_quest(page: Any) -> None:
    """Start + complete the "Lights in the Square" quest for a 50 xp reward.

    Same path as `test_dialogue_choice_starts_quest` plus the follow-through
    to the market stalls, whose `room_visited` condition (evaluated on
    `PLAYER_MOVED`, no RNG) completes the quest's only stage.
    """
    send_command(page, "go west")
    page.locator("#room-description", has_text="Wandering Crow Inn").wait_for()

    send_command(page, "talk mira")
    overlay = page.locator("#dialogue-overlay")
    overlay.wait_for(state="visible")
    overlay.get_by_text("Any news around town?").click()
    page.locator("#dialogue-overlay", has_text="I'll look into it.").wait_for()
    overlay.get_by_text("End conversation").click()
    overlay.wait_for(state="hidden")

    send_command(page, "go east")
    page.locator("#room-description", has_text="Village Square").wait_for()
    send_command(page, "go east")
    page.locator("#room-description", has_text="Market Stalls").wait_for()


def test_level_up_message_gets_distinct_styling(
    page: Any, admin_server: str, tmp_path: Path
) -> None:
    # investigate_lights' visit_market stage grants exactly 50 xp -- tune the
    # curve's base cost down to that so completing the quest levels the
    # player up deterministically, with no XP grinding in the test.
    _tune_progression_config(admin_server, base=50, step=1000)

    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, admin_server, username)
    _seed_player_stats(tmp_path, username)

    _complete_investigate_lights_quest(page)

    message = page.locator("#feed .msg.msg-level", has_text="You reach level 2!")
    message.wait_for()
    font_weight = message.evaluate("el => getComputedStyle(el).fontWeight")
    # Browsers normalize named weights ("bold") to numeric; either form
    # clears "normal"/400, same assertion shape as the msg-help test.
    assert font_weight not in ("normal", "400")


def test_stats_pane_live_updates_on_level_up(
    page: Any, admin_server: str, tmp_path: Path
) -> None:
    _tune_progression_config(
        admin_server, base=50, step=1000, coins_per_level=10, skill_points_per_level=3
    )

    username = f"e2e_{uuid.uuid4().hex[:8]}"
    create_character(page, admin_server, username)
    _seed_player_stats(tmp_path, username)

    # Open the Stats tab before leveling so the OOB swap's target element is
    # already the one visibly on-screen (it also works while hidden, since
    # Alpine's x-show only toggles display -- this just makes the assertion
    # closer to what a player actually sees).
    page.click("button[role='tab']:has-text('Stats')")
    page.locator("#stats-panel", has_text="Level 1").wait_for()

    _complete_investigate_lights_quest(page)

    # No page reload -- the same #stats-panel element re-renders in place via
    # the command response's hx-swap-oob, mirroring the quest-tracker
    # OOB-swap convention (features/quests/service.py's "quest_update" push).
    page.locator("#stats-panel", has_text="Level 2").wait_for()
    skill_points_row = (
        page.locator("#stats-panel").get_by_text("Skill Points").locator("xpath=..")
    )
    assert skill_points_row.inner_text().strip().endswith("3")
