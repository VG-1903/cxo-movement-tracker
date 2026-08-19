"""Entity-resolution dedupe for movement records.

Layers:
  1. person clusters   — token-subsequence matching ("Sunil Mittal" == "Sunil Bharti
                         Mittal"), initial expansion ("R. Vijay Anandh" == "Vijay Anandh"),
                         same surname required
  2. company clusters  — key-token overlap ignoring generic words (HDFC == HDFC Bank;
                         Axis Bank != HDFC Bank), acronym match (SBI == State Bank of
                         India), subset or Jaccard >= 0.5
  3. junk absorption   — records whose company is noise ("HDFC Bank Row", "Part-time",
                         "first Indian") are folded into the best real cluster
  4. event families    — {Appointment, Promotion, Re-appointment} describing the same
                         person+company merge into one event (label: the most specific);
                         same for {Resignation, Retirement}
"""
import re
from collections import defaultdict

_HONOR = re.compile(r"^(?:dr|mr|ms|mrs|prof|professor|justice|shri|smt)\.?\s+", re.I)


def name_tokens(p):
    p = _HONOR.sub("", p.strip().lower())
    return [t for t in re.sub(r"[^a-z ]", " ", p).split() if t]


def names_compatible(a, b):
    """Same person? exact, or order-preserving token subsequence with same surname."""
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    if ta[-1] != tb[-1] or min(len(ta), len(tb)) < 2:
        return False
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    i = 0
    for tok in big:
        if i < len(small):
            s = small[i]
            if s == tok or (len(s) == 1 and tok.startswith(s)) or (len(tok) == 1 and s.startswith(tok)):
                i += 1
    return i == len(small)


GENERIC = {
    "bank", "banks", "ltd", "limited", "pvt", "india", "indian", "group", "the",
    "of", "and", "an", "a", "its", "company", "co", "inc", "corp", "corporation",
    "university", "institute", "institutes", "hospital", "hospitals", "healthcare",
    "pharma", "pharmaceutical", "pharmaceuticals", "technologies", "technology",
    "solutions", "services", "financial", "finance", "insurance", "capital",
    "motor", "motors", "life", "global", "international", "holdings", "industries",
    "amc", "asset", "management", "mutual", "fund",
}
_JUNK_CO = re.compile(
    r"\b(?:row|why|denies|says|said|reports?|amid|after|part[- ]?time|differences|"
    r"first|arm|board|starts?|search|shareholders?|invest(?:s|ment)?|effect|values|"
    r"ethics|new|creates?|unit|exit|quits?|resign\w*|steps?|down|its|his|her)\b", re.I)


def co_tokens(c):
    return [t for t in re.sub(r"[^a-z0-9& ]", " ", (c or "").lower()).split() if t and t != "&"]


def co_key(c):
    return {t for t in co_tokens(c) if t not in GENERIC}


def acronym(c):
    toks = [t for t in co_tokens(c) if t not in {"of", "the", "and"}]
    return "".join(t[0] for t in toks) if len(toks) >= 2 else ""


def company_is_junk(c):
    return not c or len(c) < 3 or bool(_JUNK_CO.search(c))


def companies_compatible(a, b):
    ka, kb = co_key(a), co_key(b)
    if not ka or not kb:
        return False
    if ka <= kb or kb <= ka:
        return True
    inter = len(ka & kb)
    if inter and inter / len(ka | kb) >= 0.5:
        return True
    ja, jb = "".join(co_tokens(a)), "".join(co_tokens(b))
    return (acronym(a) and acronym(a) == jb) or (acronym(b) and acronym(b) == ja)


A_FAMILY = {"Appointment", "Promotion", "Re-appointment"}
E_FAMILY = {"Resignation", "Retirement"}


def _family(mv):
    return "A" if mv in A_FAMILY else "E"


def _merge_group(group):
    """Collapse a list of records (same person, same family, same company entity)."""
    def best_label(recs):
        mvs = {r["movement"] for r in recs}
        if "Re-appointment" in mvs:
            return "Re-appointment"
        if "Promotion" in mvs:
            return "Promotion"
        if "Retirement" in mvs:
            return "Retirement"
        if "Resignation" in mvs:
            return "Resignation"
        return recs[0]["movement"]

    # base = record with a clean company, longest role, then longest headline
    base = max(group, key=lambda r: (not company_is_junk(r["company"]),
                                     len(r.get("role", "")), len(r.get("headline", ""))))
    out = dict(base)
    out["movement"] = best_label(group)
    out["person"] = max((r["person"] for r in group), key=lambda p: (len(p.split()), len(p)))
    clean = [r["company"] for r in group if not company_is_junk(r["company"])]
    if clean:
        counts = defaultdict(int)
        for c in clean:
            counts[c] += 1
        out["company"] = max(counts, key=lambda c: (counts[c], len(c)))
    dates = [r["date"] for r in group if r["date"]]
    if dates:
        out["date"] = min(dates)
    if any(r["region"] == "India" for r in group):
        out["region"] = "India"
    for r in sorted(group, key=lambda r: r.get("moved_from_source", "") != "headline"):
        if r.get("moved_from"):
            out["moved_from"] = r["moved_from"]
            out["moved_from_source"] = r["moved_from_source"]
            break
    pubs = []
    for r in group:
        for p in [r.get("publisher", "")] + list(r.get("also_reported_by", [])):
            if p and p != out.get("publisher") and p not in pubs:
                pubs.append(p)
    out["also_reported_by"] = pubs
    return out


def dedupe(records):
    """Return (deduped_records, n_merged_away)."""
    # ---- person clustering, bucketed by surname
    by_surname = defaultdict(list)
    for idx, r in enumerate(records):
        toks = name_tokens(r["person"])
        by_surname[toks[-1] if toks else ""].append(idx)

    parent = list(range(len(records)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for idxs in by_surname.values():
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                a, b = idxs[i], idxs[j]
                if names_compatible(records[a]["person"], records[b]["person"]):
                    union(a, b)

    person_clusters = defaultdict(list)
    for idx in range(len(records)):
        person_clusters[find(idx)].append(idx)

    out = []
    for idxs in person_clusters.values():
        for fam in ("A", "E"):
            fam_recs = [records[i] for i in idxs if _family(records[i]["movement"]) == fam]
            if not fam_recs:
                continue
            clean = [r for r in fam_recs if not company_is_junk(r["company"])]
            junk = [r for r in fam_recs if company_is_junk(r["company"])]
            # company subclusters over clean records (union-find for transitivity)
            cp = list(range(len(clean)))

            def cfind(x):
                while cp[x] != x:
                    cp[x] = cp[cp[x]]
                    x = cp[x]
                return x

            for i in range(len(clean)):
                for j in range(i + 1, len(clean)):
                    if companies_compatible(clean[i]["company"], clean[j]["company"]):
                        ri, rj = cfind(i), cfind(j)
                        if ri != rj:
                            cp[rj] = ri
            groups = defaultdict(list)
            for i, r in enumerate(clean):
                groups[cfind(i)].append(r)
            subclusters = list(groups.values())
            # junk records: attach by any key-token overlap, else to the largest
            for r in junk:
                target = None
                rk = co_key(r["company"])
                for sc in subclusters:
                    if rk and any(rk & co_key(o["company"]) for o in sc):
                        target = sc
                        break
                if target is None and subclusters:
                    target = max(subclusters, key=len)
                if target is None:
                    subclusters.append([r])
                else:
                    target.append(r)
            for sc in subclusters:
                out.append(_merge_group(sc))

    out.sort(key=lambda r: r["date"] or "0000", reverse=True)
    return out, len(records) - len(out)
