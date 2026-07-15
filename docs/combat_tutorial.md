# Combat Tutorial

This tutorial explains Lorecraft combat from a player point of view. Use it when you want to
survive your first fight, understand why actions resolve after a short delay, or help another
player without learning internal engine details.

## Table of Contents

- [The Short Version](#the-short-version)
- [Before You Fight](#before-you-fight)
- [Starting Combat](#starting-combat)
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
defend             brace for incoming attacks
guard [ally]       protect yourself or an ally from melee attacks
flee               try to leave the encounter
stance <stance>    choose balanced, aggressive, defensive, or mobile
reaction <policy>  choose defensive, conserve, or never
assist <player>    join a nearby player's active fight on their side
```

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

## Starting Combat

Use `attack <target>` against a nearby non-player character:

```text
attack goblin
```

Use `shoot <target>` for ranged attacks:

```text
shoot goblin
```

Ranged combat is intentionally simple. Lorecraft does not ask you to manage formations, distance
bands, or advance/retreat positioning. A shot records that it was ranged and can support bows,
crossbows, tower guards, or sniper-like authored encounters later.

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

## Winning, Fleeing, And Going Down

NPCs defeated at 0 HP leave the fight as defeated. Players who hit 0 HP become downed by default,
leave active combat, and lose any queued combat action. This is a non-lethal default policy.

To leave before things go badly:

```text
flee
```

Your stance can affect the stamina cost of fleeing. `mobile` is the safest stance when your plan is
to survive and get out.

Some strong hits apply short-lived status effects, such as being off balance. These expire on game
time and show up in structured combat state.

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
