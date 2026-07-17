# Combat Tutorial

This tutorial explains Lorecraft combat from a player point of view. Use it when you want to
survive your first fight, understand why actions resolve after a short delay, or help another
player without learning internal engine details.

## Table of Contents

- [The Short Version](#the-short-version)
- [Before You Fight](#before-you-fight)
- [Starting Combat](#starting-combat)
- [Reading The Browser Combat Feed](#reading-the-browser-combat-feed)
- [During A Fight](#during-a-fight)
- [Helping Another Player](#helping-another-player)
- [Winning, Fleeing, And Going Down](#winning-fleeing-and-going-down)
- [What Combat Is Not](#what-combat-is-not)
- [Related](#related)

## The Short Version

Combat uses scheduled intent. When you type `attack goblin`, the command commits your action,
then the world resolves it after a short wind-up. You are not expected to spam commands. Pick your
next action, watch the result, and adjust.

Useful first commands:

```text
attack <target>    start or continue a melee attack
shoot <target>     start or continue a ranged attack
consider <target>  appraise a nearby opponent
defend             brace for incoming attacks
guard [ally]       protect yourself or an ally from melee attacks
flee               try to leave the encounter
stance <stance>    choose balanced, aggressive, defensive, or mobile
reaction <policy>  choose defensive, conserve, or never
assist <player>    join a nearby player's active fight on their side
```

In Ashmoore, the training academy west of South Gate is the safest place to try these commands.
Talk to Armsmaster Seren Vale in the drill hall, take practice gear from the pegs, and spar with
Tobin in the yard.

## Before You Fight

Check your equipment before starting trouble:

```text
equipment
inventory
wield <weapon>
wear <armor>
```

Weapons and armor already matter. A wielded weapon affects damage, accuracy, and penetration.
Wearable armor can reduce incoming damage. You can still fight unarmed, but it is weaker.

At the academy, try:

```text
take club
wield club
take vest
wear vest
```

You can also take and wield the training bow before trying `shoot`.

## Starting Combat

Use `attack <target>` against a nearby non-player character:

```text
attack goblin
```

Use `shoot <target>` for ranged attacks:

```text
shoot goblin
```

Use `consider <target>` before a fight to check the opponent's HP and your likely odds:

```text
consider goblin
```

Ranged combat is intentionally simple. Lorecraft does not ask you to manage formations, distance
bands, or advance/retreat positioning. A shot records that it was ranged and can support bows,
crossbows, tower guards, or sniper-like authored encounters later.

Terrain and cover are also simple. Some rooms, such as forests, mountain paths, and swamps, make
targets a little harder to hit, and builders can author explicit light/partial/heavy cover on a
room. You do not spend actions to enter cover or track positions; the room environment is applied
automatically when an attack resolves.

Some authored actions can create a follow-up opening, then another authored action can consume
that opening for a temporary accuracy or damage bonus. You do not manage a separate combo meter;
if an action supports a combo hook, the combat feed and admin traces record the result.

Special arena or boss encounters can opt into simultaneous-planning mode. In that mode, the NPC
queues its response as soon as you commit, and both actions share the same resolve time. You still
use the normal combat commands; the authored encounter changes timing.

## Reading The Browser Combat Feed

Combat output appears in two forms:

- prose in the normal feed, such as who attacked, guarded, fled, or went down
- structured combat state used by the browser to keep participants, statuses, stances, and
  attention cues current
- a compact opponent health line after combat updates, showing current HP

If you see your action committed but not resolved yet, that is normal scheduled intent. The action
has a short wind-up, then recovery. Once a fight is active, participants keep queuing basic attacks
automatically every few game seconds until someone dies, is defeated, or escapes. You can still
replace your next queued primary action by choosing to attack a target, defend, switch stance, or
flee.

The browser may continue to show dead, defeated, or escaped participants briefly because combat
state keeps the outcome explicit instead of making actors vanish from the record.

## During A Fight

After you act, you enter recovery. During recovery you may queue one replacement primary action.
The newer choice replaces the older pending one, so choose deliberately.

Stances change your trade-off for the encounter:

```text
stance balanced
stance aggressive
stance defensive
stance mobile
```

- `balanced` is the default.
- `aggressive` favors offense and damage.
- `defensive` favors avoiding damage.
- `mobile` makes escape less costly.

Reactions are automatic defensive responses with a cooldown:

```text
reaction defensive
reaction conserve
reaction never
```

`defensive` lets your character spend an available brace reaction when attacked. `never` disables
that automatic reaction.

If you type a new primary action while one is already queued, the older one is cancelled. This is
useful when the fight changes, but it also means frantic command spam can throw away the action you
actually wanted.

## Helping Another Player

If another player in your room is already fighting, join their side:

```text
assist petem
```

Assisting makes you a participant in that encounter. It records that you joined as help, so later
reward and audit systems can treat your help as participation. It does not start PvP and it does
not create party formations.

To protect someone from melee attacks:

```text
guard ally
```

Guarding can redirect an incoming melee attack to you. It does not intercept ranged shots.

## Winning, Fleeing, And Dying

NPCs defeated at 0 HP leave the fight as defeated. Players who hit 0 HP die, leave active combat,
lose any queued combat action, and immediately respawn at their respawn point with a fraction of max
HP restored. Death leaves a corpse in the room where you fell; 20% of your carried coins and loose,
unbound carried items move into it. Equipped and bound items stay with you, and you wake with a
temporary weakened effect.

To leave before things go badly:

```text
flee
```

Your stance can affect the stamina cost of fleeing. `mobile` is the safest stance when your plan is
to survive and get out.

Some strong hits apply short-lived status effects, such as being off balance. These expire on game
time and show up in structured combat state.

Combat may also affect reputation when a world builder has authored that consequence. For example,
attacking a guard can lower standing with that guard's faction. Those consequences come from world
content and are not a separate bounty or arrest system yet.

## What Combat Is Not

Combat is a supporting system, not the whole game. Stealth, conversation, exploration, quests,
trading, and avoidance are still valid ways to play.

The current combat model deliberately avoids:

- player formations
- persistent near/far distance bands
- advance/retreat/disengage positioning verbs
- full PvP duel consent and stakes
- server-side player combat scripts

Those ideas should only return if playtesting shows a clear need.

## Related

- [Player Guide](user_guide.md#combat)
- [Combat Design](combat_design.md)
- [Admin Builder Guide](admin_builder_guide.md#combat-implementation-notes)
