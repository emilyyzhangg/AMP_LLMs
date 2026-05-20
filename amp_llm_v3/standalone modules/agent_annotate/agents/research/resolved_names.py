"""
Shared helper: surface Lever-4 resolved drug names to research agents.

`_resolve_drug_names` (orchestrator) writes canonical drug names into each
metadata intervention's ``resolved`` list *before* the research agents run —
e.g. the trial code "AMG 334" resolves to "erenumab", "ZP4207" to
"dasiglucagon". Historically only ``peptide_identity`` consumed ``resolved``;
ChEMBL / FDA Drugs / NIH RePORTER / SEC EDGAR / IUPHAR read only the raw
``name`` (the trial code) and so queried unrecognized codes and came back
empty even for approved drugs.

These helpers let an agent normalize the intervention list and query the raw
name first, falling back to the resolved canonical name(s) only when the raw
query returns nothing — keeping extra API calls to a minimum.
"""

from typing import Optional


def extract_interventions(metadata: Optional[dict]) -> list[dict]:
    """Normalize ``metadata['interventions']`` to a list of dicts.

    Each entry is ``{"name": str, "type": str, "resolved": [str, ...]}`` where
    ``type`` is upper-cased (DRUG / BIOLOGICAL / DEVICE / …, "" if absent) and
    ``resolved`` holds Lever-4 canonical names excluding the primary name.
    Accepts both the dict shape and the legacy bare-string shape.
    """
    out: list[dict] = []
    if not metadata:
        return out
    raw = metadata.get("interventions", [])
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, dict):
            name = (item.get("name") or item.get("intervention_name") or "").strip()
            if not name:
                continue
            resolved: list[str] = []
            for r in (item.get("resolved") or []):
                rs = str(r).strip()
                if rs and rs.lower() != name.lower() and rs not in resolved:
                    resolved.append(rs)
            out.append({
                "name": name,
                "type": (item.get("type") or "").upper(),
                "resolved": resolved,
            })
        elif isinstance(item, str) and item.strip():
            out.append({"name": item.strip(), "type": "", "resolved": []})
    return out


def query_names(interv: dict) -> list[str]:
    """Ordered, de-duplicated query names: raw name first, then resolved names.

    Agents should query these in order and stop at the first that returns
    results, so the raw name is preferred and resolved names are fallbacks.
    """
    names = [interv["name"]]
    seen = {interv["name"].lower()}
    for r in interv.get("resolved", []):
        if r.lower() not in seen:
            names.append(r)
            seen.add(r.lower())
    return names
