"""More than one star: what each orbit goes around, and how far it may reach.

A **host** is a star, by name, or a **group**: stars bound together, whose
shared centre of gravity something orbits, written as their names joined
with "+" ("A+B"). A companion star's `host` defaults to the primary,
and so does a planet's, a belt's, and a point of interest's around a star.

The stars form a tree. Each companion, with whatever orbits it, orbits its
host; the host and the companions that orbit it make the next group up, and
companions whose host is that group the one after. So "B orbits A, C orbits
A+B" is α Centauri A and B with Proxima. A group is valid when the tree has
it.

Where something may orbit and stay (Holman & Wiegert 1999): around one star
of a pair inside a fraction of their separation (S-type), around a pair
outside a multiple of it (P-type), both depending on the pair's
eccentricity and masses.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from typing import Any, Optional

from galaxy.stars import Star, star

SEPARATOR = "+"


@dataclass
class Node:
    """A star, or a group: its `core` (the host the satellites orbit) and
    the satellites, each a companion star's orbit and what orbits with it."""
    names: frozenset[str]
    star: Optional[Star] = None                     # a single star's class
    name: str = ""                                  # a single star's name
    core: Optional["Node"] = None
    satellites: list[tuple[dict[str, Any], "Node"]] = field(default_factory=list)
    parent: Optional["Node"] = None
    order: dict[str, int] = field(default_factory=dict, repr=False)

    @property
    def key(self) -> str:
        """As it is written: its stars' names in the system's order."""
        return key_of(self.names, self.order)

    @property
    def mass(self) -> Optional[float]:
        """In suns: a star's, or a group's stars' together; None where one has
        no class to go by."""
        if self.core is None:
            return self.star.mass if self.star else None
        masses = [self.core.mass] + [n.mass for _, n in self.satellites]
        return None if any(m is None for m in masses) else sum(masses)

    @property
    def luminosity(self) -> Optional[float]:
        """In suns: a star's, or a group's stars' together; None where one has
        no class to go by."""
        if self.core is None:
            return self.star.luminosity if self.star else None
        values = [self.core.luminosity] + [n.luminosity for _, n in self.satellites]
        return None if any(v is None for v in values) else sum(values)

    def nodes(self):
        """This node and every node inside it."""
        yield self
        if self.core is not None:
            yield from self.core.nodes()
            for _, n in self.satellites:
                yield from n.nodes()


def key_of(names, order: Optional[dict[str, int]] = None) -> str:
    """A host's name: its stars' names in the system's order, joined."""
    order = order or {}
    return SEPARATOR.join(sorted(names, key=lambda n: (order.get(n, len(order)), n)))


def names_of(host: str) -> frozenset[str]:
    """The star names a host is written with, "A+B" → {A, B}."""
    return frozenset(part.strip() for part in host.split(SEPARATOR) if part.strip())


def star_names(system: dict[str, Any]) -> list[str]:
    """The system's star names in order; without a `stars` list, the system's
    own name for its one star."""
    stars = system.get("stars") or []
    return [(s.get("name") or "").strip() for s in stars] if stars else [system.get("name") or ""]


def primary_name(system: dict[str, Any]) -> str:
    """The primary star's name, or the system's while the star has none."""
    return star_names(system)[0] or system.get("name") or ""


def host_names(system: dict[str, Any], host: Optional[str]) -> frozenset[str]:
    """The stars a host names; no host is the primary."""
    return names_of(host) if host else frozenset({primary_name(system)})


@dataclass
class Tree:
    """A system's stars as a tree (`tree`), its nodes also by their stars' names."""
    root: Node
    by_names: dict[frozenset[str], Node]
    unplaced: list[str]          # stars the tree does not reach: a host it does not have

    def node(self, names: frozenset[str]) -> Optional[Node]:
        return self.by_names.get(names)


def tree(system: dict[str, Any], physical: bool = False) -> Tree:
    """The system's stars as a tree. `physical` leaves out a companion that
    cannot be placed — no class (so no mass) or no orbit — with whatever
    orbits it: the tree the map draws and the periods come from."""
    stars = system.get("stars") or []
    # The primary is a remnant where the system's object_type names one.
    first = ({**stars[0], "object_type": system.get("object_type")} if stars
             else {"spectral_class": system.get("spectral_class"), "object_type": system.get("object_type")})
    pname = primary_name(system)
    companions = [(s, (s.get("name") or "").strip(), host_names(system, s.get("host"))) for s in stars[1:]]
    used: set[str] = {pname}

    def leaf(record: dict[str, Any], name: str) -> Node:
        return Node(names=frozenset({name}), star=star(record.get("spectral_class"), record.get("object_type")),
                    name=name)

    def grow(node: Node) -> Node:
        while True:
            kids = []
            for record, name, host in companions:
                if host == node.names and name not in used and name:
                    used.add(name)
                    sub = grow(leaf(record, name))
                    if physical and (sub.mass is None or not (record.get("orbit") or {}).get("au")):
                        continue
                    kids.append((record.get("orbit") or {}, sub))
            if not kids:
                return node
            group = Node(names=node.names.union(*(n.names for _, n in kids)), core=node, satellites=kids)
            node.parent = group
            for _, n in kids:
                n.parent = group
            node = group

    root = grow(leaf(first, pname))
    order = {n: k for k, n in enumerate(star_names(system))}
    order[pname] = 0
    for n in root.nodes():
        n.order = order
    by_names = {n.names: n for n in root.nodes()}
    unplaced = [name for _, name, _ in companions if name and name not in root.names]
    return Tree(root, by_names, unplaced)


def hosts(system: dict[str, Any]) -> list[str]:
    """Every host something may orbit, as it is written: each star, then
    each group, smallest first."""
    t = tree(system)
    names = [primary_name(system)] + [n for n in star_names(system)[1:] if n and n in t.root.names]
    groups = sorted((n for n in t.by_names.values() if len(n.names) > 1), key=lambda g: (len(g.names), g.key))
    return names + [g.key for g in groups]


def host_star(node: Node) -> Optional[Star]:
    """What the zones and the draw go by: a star's own class, or a group's
    stars together — their mass and light."""
    if node.core is None:
        return node.star
    if node.mass is None:
        return None
    lead = next(n.star for n in node.nodes() if n.core is None)
    return dataclasses.replace(lead, spectral_class=node.key, mass=round(node.mass, 3),
                               luminosity=node.luminosity)


# ── where an orbit stays (Holman & Wiegert 1999) ─────────────────────────────

def s_ratio(e: float, mu: float) -> float:
    """Around one star of a pair, stable inside this × the pair's semi-major
    axis; `mu` the other star's share of the pair's mass."""
    return max(0.02, 0.464 - 0.380 * mu - 0.631 * e + 0.586 * mu * e + 0.150 * e ** 2 - 0.198 * mu * e ** 2)


def p_ratio(e: float, mu: float) -> float:
    """Around a pair, stable outside this × its semi-major axis; `mu` the
    lighter side's share of the pair's mass."""
    mu = min(mu, 1 - mu)
    return 1.60 + 5.10 * e - 2.22 * e ** 2 + 4.12 * mu - 4.27 * e * mu - 5.09 * mu ** 2 + 4.61 * e ** 2 * mu ** 2


def _share(a: Node, b: Node) -> Optional[float]:
    """b's share of the mass of a and b together."""
    if a.mass is None or b.mass is None:
        return None
    return b.mass / (a.mass + b.mass)


def outer_limit(node: Node) -> Optional[tuple[float, str]]:
    """How far from `node` an orbit around it may reach, in AU, and what
    sets it: the nearest pair it is one side of. None for the whole system."""
    group = node.parent
    if group is None:
        return None
    if node is group.core:
        found = []
        for orbit, other in group.satellites:
            mu = _share(node, other)
            if mu is not None and orbit.get("au"):
                found.append((s_ratio(orbit.get("e", 0.0), mu) * orbit["au"], other.key))
        return min(found) if found else None
    orbit = next(o for o, n in group.satellites if n is node)
    mu = _share(node, group.core)
    if mu is None or not orbit.get("au"):
        return None
    return s_ratio(orbit.get("e", 0.0), mu) * orbit["au"], group.core.key


def inner_limit(node: Node) -> Optional[float]:
    """How close to a group's centre an orbit around the group may come, in
    AU: outside its widest pair. None for a single star."""
    if node.core is None:
        return None
    limits = []
    for orbit, other in node.satellites:
        mu = _share(node.core, other)
        if mu is not None and orbit.get("au"):
            limits.append(p_ratio(orbit.get("e", 0.0), mu) * orbit["au"])
    inner = inner_limit(node.core)
    return max(limits + ([inner] if inner else []), default=None)
