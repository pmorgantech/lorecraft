"""Strict YAML loading for world content.

PyYAML follows YAML 1.1, which coerces the bare words ``on``/``off``/``yes``/``no`` to booleans
— the infamous "Norway problem". That silently turns a scripting-engine trigger key like
``on: encounter`` into ``{True: "encounter"}`` (and then, through the JSON column, into the
string ``"true"``). :data:`WorldYamlLoader` keeps ``true``/``false`` as booleans but leaves
``on``/``off``/``yes``/``no`` as plain strings, so ``on:`` is authorable unquoted. No world
content relied on those bare words as booleans (everything uses ``true``/``false``).
"""

from __future__ import annotations

import re

import yaml


class WorldYamlLoader(yaml.SafeLoader):
    """A SafeLoader that does not treat ``on``/``off``/``yes``/``no`` as booleans."""


# Copy the base resolvers, drop every bool resolver, then re-add a strict true/false one.
WorldYamlLoader.yaml_implicit_resolvers = {
    ch: [
        (tag, regexp) for (tag, regexp) in resolvers if tag != "tag:yaml.org,2002:bool"
    ]
    for ch, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
WorldYamlLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
)


def load_world_yaml_text(text: str) -> object:
    """Parse world-content YAML text with the strict loader."""
    return yaml.load(text, Loader=WorldYamlLoader)
