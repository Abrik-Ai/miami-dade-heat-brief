"""Compare two FortyGuard REST response bodies field by field.

Built for the repeatability check: the same point and day requested twice,
once started via MCP and once via REST, both saved from the REST API.

Reports, separately:
  1. byte-level: sizes and sha256, and whether the bodies are identical
  2. structure: JSON paths present in only one body, and JSON type differences
     (e.g. int vs float, number vs null, different list lengths)
  3. non-hourly values: every scalar outside the hourly parameter arrays
     (wrapper, message, activity_id, metadata, location, solar irradiance)
  4. hourly values: every one of the 24 values in every parameter array
  5. key order: whether keys appear in the same order (affects bytes, not data)

Usage:
    uv run scripts/compare_api_bodies.py A.json B.json
"""

import hashlib
import json
import sys
from pathlib import Path

HOURLY = ("data", "result", "locations", 0, "parameters")


def jtype(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return f"list[{len(v)}]"
    return "object"


def walk(v, path=()):
    """Yield (path, value) for every node; lists of numbers count as one leaf."""
    yield path, v
    if isinstance(v, dict):
        for k, x in v.items():
            yield from walk(x, path + (k,))
    elif isinstance(v, list) and any(isinstance(x, (dict, list)) for x in v):
        for i, x in enumerate(v):
            yield from walk(x, path + (i,))


def fmt(path):
    return "".join(f"[{p}]" if isinstance(p, int) else (f".{p}" if i else p) for i, p in enumerate(path))


def key_orders(v, path=()):
    if isinstance(v, dict):
        yield path, list(v.keys())
        for k, x in v.items():
            yield from key_orders(x, path + (k,))
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from key_orders(x, path + (i,))


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    pa, pb = Path(sys.argv[1]), Path(sys.argv[2])
    ba, bb = pa.read_bytes(), pb.read_bytes()
    a, b = json.loads(ba), json.loads(bb)

    print(f"A: {pa}  ({len(ba)} bytes, sha256 {hashlib.sha256(ba).hexdigest()[:16]}…)")
    print(f"B: {pb}  ({len(bb)} bytes, sha256 {hashlib.sha256(bb).hexdigest()[:16]}…)")
    print(f"bodies byte-identical: {ba == bb}")

    na, nb = dict(walk(a)), dict(walk(b))

    # 2. structure
    only_a = sorted((p for p in na if p not in nb), key=fmt)
    only_b = sorted((p for p in nb if p not in na), key=fmt)
    type_diffs = [(p, jtype(na[p]), jtype(nb[p])) for p in na if p in nb and jtype(na[p]) != jtype(nb[p])]
    elem_type_diffs = []
    for p in na:
        if p in nb and isinstance(na[p], list) and isinstance(nb[p], list) and len(na[p]) == len(nb[p]):
            for i, (x, y) in enumerate(zip(na[p], nb[p])):
                if not isinstance(x, (dict, list)) and jtype(x) != jtype(y):
                    elem_type_diffs.append((p + (i,), jtype(x), jtype(y)))
    print(f"\n[structure] paths only in A: {len(only_a)}, only in B: {len(only_b)}, "
          f"type differences: {len(type_diffs) + len(elem_type_diffs)}")
    for p in only_a:
        print(f"  only in A: {fmt(p)}")
    for p in only_b:
        print(f"  only in B: {fmt(p)}")
    for p, ta, tb in sorted(type_diffs + elem_type_diffs, key=lambda t: fmt(t[0])):
        print(f"  type: {fmt(p)}  A={ta}  B={tb}")

    # 3. non-hourly scalars
    scalar = [p for p in na if p in nb and p[:len(HOURLY)] != HOURLY
              and not isinstance(na[p], (dict, list))]
    lists_outside = [p for p in na if p in nb and p[:len(HOURLY)] != HOURLY
                     and isinstance(na[p], list) and not any(isinstance(x, (dict, list)) for x in na[p])]
    meta_diffs = [(p, na[p], nb[p]) for p in scalar + lists_outside if na[p] != nb[p]]
    print(f"\n[non-hourly values] compared: {len(scalar) + len(lists_outside)}, differences: {len(meta_diffs)}")
    for p, x, y in sorted(meta_diffs, key=lambda t: fmt(t[0])):
        print(f"  {fmt(p)}\n    A={json.dumps(x)[:200]}\n    B={json.dumps(y)[:200]}")

    # 4. hourly values
    pa_ = a["data"]["result"]["locations"][0]["parameters"]
    pb_ = b["data"]["result"]["locations"][0]["parameters"]
    hourly_diffs, n = [], 0
    for k in sorted(set(pa_) & set(pb_)):
        for h, (x, y) in enumerate(zip(pa_[k], pb_[k])):
            n += 1
            if x != y:
                hourly_diffs.append((k, h, x, y))
    print(f"\n[hourly values] fields compared: {len(set(pa_) & set(pb_))}, values compared: {n}, "
          f"differences: {len(hourly_diffs)}")
    for k, h, x, y in hourly_diffs:
        print(f"  {k}  hour {h:02d}  A={x!r}  B={y!r}")

    # 5. key order
    oa, ob = dict(key_orders(a)), dict(key_orders(b))
    order_diffs = [p for p in oa if p in ob and oa[p] != ob[p] and set(oa[p]) == set(ob[p])]
    print(f"\n[key order] objects with same keys in a different order: {len(order_diffs)}")
    for p in order_diffs:
        print(f"  {fmt(p) or '(root)'}:\n    A={oa[p]}\n    B={ob[p]}")


if __name__ == "__main__":
    main()
