"""Headline -> movement record extraction for CXO transfer tracking.

Patterns are compiled case-SENSITIVE so that the person regex can rely on
capitalisation; verbs/roles/glue words are wrapped in (?i:...) scoped groups.
"""
import re

# ---------------------------------------------------------------- roles
_MOD = r"(?:Group|Global|Interim|Acting|Deputy|Joint|Additional|Executive|Non[- ]Executive|Whole[- ]?Time|Senior|Regional|National|Independent|Vice|In[- ]?Charge)"
_CORE = (
    r"Chief\s+\w+(?:\s+\w+)?\s+Officer"
    r"|Managing\s+Director|Managing\s+Partner|Director\s+General"
    r"|Pro[- ]Vice[- ]Chancellor|Vice[- ]Chancellor|Chancellor"
    r"|Chairperson|Chairwoman|Chairman"
    r"|Executive\s+Vice\s+President|Vice\s+President|President"
    r"|Executive\s+Director|Whole[- ]?Time\s+Director|Director"
    r"|CEO|CFO|CTO|COO|CIO|CMO|CHRO|CISO|CDO|CBO|CRO|CPO|CCO|CTIO"
    r"|CMD|AMD|DMD|MD|VC"
    r"|Dean|Registrar|Principal|Provost"
    r"|Country\s+Head|India\s+Head|Head"
)
_ONE_ROLE = rf"(?:{_MOD}[\s-]+)*(?:{_CORE})"
ROLE = rf"(?i:{_ONE_ROLE}(?:\s*(?:&|and|,)\s*{_ONE_ROLE})*)"

# person: 2-5 capitalised tokens (initials, dots, hyphens, apostrophes ok)
PERSON = r"(?:(?:Dr|Mr|Ms|Mrs|Prof|Justice|Lt|Gen|Col)\.?\s+)?[A-Z][\w.'’-]*(?:\s+[A-Z][\w.'’-]*){1,4}"
COMPANY = r".+?"

_APPOINT = r"(?i:appoints|names|hires|onboards|ropes\s+in|brings\s+in|picks|selects|welcomes)"
_APPOINTED = r"(?i:appointed|named|designated|chosen|selected|elected)"
_WAS = r"(?:(?i:has\s+been|is|was)\s+)?"
# descriptor between verb and name: "insider", "Former IAS Officer", "Seasoned Edtech and Growth Executive"
_DESC = r"(?:(?i:insider|veteran)\s+|(?i:former|ex|seasoned|veteran)[\s-]+(?:[\w&.'’-]+\s+){0,4}?(?i:officer|executive|exec|banker|chief|head|leader)\s+)?"
_PRE = r"(?:(?i:its|the|a|new|next|in[- ]?charge)\s+)*"
_REG = r"(?i:RBI|IRDAI|SEBI|Sebi|Irdai)"

PATTERNS = [
    # regulator approvals
    ("Re-appointment", rf"{_REG}\s+(?i:approves\s+(?:the\s+)?re-?appointment\s+of)\s+(?P<person>{PERSON})\s+(?i:as)\s+(?P<rest>.+)"),
    ("Appointment", rf"{_REG}\s+(?i:approves\s+(?:the\s+)?appointment\s+of)\s+(?P<person>{PERSON})\s+(?i:as)\s+(?P<rest>.+)"),
    ("Appointment", rf"{_REG}\s+(?i:approves)\s+(?P<person>{PERSON})['’]s\s+(?i:appointment\s+as)\s+(?P<rest>.+)"),
    # C re-appoints P (as) R
    ("Re-appointment", rf"(?P<company>{COMPANY})\s+(?i:re-?appoints)\s+(?P<person>{PERSON})\s+(?:(?i:as)\s+)?{_PRE}(?P<role>{ROLE})"),
    # C appoints/names DESC P as R
    ("Appointment", rf"(?P<company>{COMPANY})\s+{_APPOINT}\s+{_DESC}(?P<person>{PERSON})\s+(?i:as)\s+{_PRE}(?P<role>{ROLE})"),
    # C appoints DESC P R   (no 'as')
    ("Appointment", rf"(?P<company>{COMPANY})\s+{_APPOINT}\s+{_DESC}(?P<person>{PERSON})\s+{_PRE}(?P<role>{ROLE})"),
    # C elevates/promotes DESC P to/as R
    ("Promotion", rf"(?P<company>{COMPANY})\s+(?i:elevates|promotes)\s+{_DESC}(?P<person>{PERSON})\s+(?i:to|as)\s+{_PRE}(?P<role>{ROLE})"),
    # P appointed/named as R of/at C   (anchored)
    ("Appointment", rf"(?P<person>{PERSON})\s+{_WAS}{_APPOINTED}\s+(?:(?i:as)\s+)?{_PRE}(?P<role>{ROLE})\s+(?i:of|at|for)\s+(?P<company>{COMPANY})$"),
    # P appointed C('s) R   ("... appointed Jio Platforms CEO", "named Gujarat University's in-charge VC")
    ("Appointment", rf"(?P<person>{PERSON})\s+{_WAS}{_APPOINTED}\s+(?:(?i:as)\s+)?(?P<company>{COMPANY})(?:['’]s)?\s+{_PRE}(?P<role>{ROLE})$"),
    # P elevated/promoted to R (Role) of/at C  or  "..., C"
    ("Promotion", rf"(?P<person>{PERSON})\s+(?:(?i:has\s+been)\s+)?(?i:elevated|promoted)\s+(?i:to)\s+(?:(?i:the)\s+)?(?:(?i:role\s+of|position\s+of)\s+)?(?P<role>{ROLE})(?:\s+(?i:role|position))?(?:\s+(?i:of|at)\s+|,\s*)(?P<company>{COMPANY})$"),
    # P elevated to R (no company)
    ("Promotion", rf"(?P<person>{PERSON})\s+(?:(?i:has\s+been)\s+)?(?i:elevated|promoted)\s+(?i:to)\s+(?:(?i:the)\s+)?(?P<role>{ROLE})"),
    # P joins C as R
    ("Appointment", rf"(?P<person>{PERSON})\s+(?i:(?:re)?joins)\s+(?P<company>{COMPANY})\s+(?i:as)\s+{_PRE}(?P<role>{ROLE})"),
    # P takes over/charge as R of C
    ("Appointment", rf"(?P<person>{PERSON})\s+(?:(?i:to)\s+)?(?i:takes?\s+(?:over|charge))\s+(?i:as)\s+{_PRE}(?P<role>{ROLE})\s+(?i:of|at)\s+(?P<company>{COMPANY})$"),
    # P takes charge as C('s) R
    ("Appointment", rf"(?P<person>{PERSON})\s+(?:(?i:to)\s+)?(?i:takes?\s+(?:over|charge))\s+(?i:as)\s+(?P<company>{COMPANY})(?:['’]s)?\s+{_PRE}(?P<role>{ROLE})$"),
    # P steps down / resigns / quits as R of C
    ("Resignation", rf"(?P<person>{PERSON})\s+(?:(?i:to)\s+)?(?i:steps?\s+down|resigns?|quits?)\s+(?i:as)\s+(?:(?i:the)\s+)?(?P<role>{ROLE})\s+(?i:of|at)\s+(?P<company>{COMPANY})$"),
    ("Retirement", rf"(?P<person>{PERSON})\s+(?:(?i:to)\s+)?(?i:retires?)\s+(?i:as)\s+(?:(?i:the)\s+)?(?P<role>{ROLE})\s+(?i:of|at)\s+(?P<company>{COMPANY})$"),
    # P steps down as C('s) R   ("Sunil Mittal to step down as Airtel Payments Bank Chairman")
    ("Resignation", rf"(?P<person>{PERSON})\s+(?:(?i:to)\s+)?(?i:steps?\s+down|resigns?|quits?)\s+(?i:as)\s+(?P<company>{COMPANY})(?:['’]s)?\s+(?P<role>{ROLE})"),
    # C('s) R P resigns/steps down/retires   ("Axis Bank CFO Puneet Sharma resigns")
    ("Resignation", rf"(?P<company>{COMPANY})(?:['’]s)?\s+(?P<role>{ROLE})\s+(?P<person>{PERSON})\s+(?:(?i:to)\s+)?(?i:resigns?|steps?\s+down|quits?)"),
    ("Retirement", rf"(?P<company>{COMPANY})(?:['’]s)?\s+(?P<role>{ROLE})\s+(?P<person>{PERSON})\s+(?:(?i:to)\s+)?(?i:retires?)"),
    # P named R at C (loose, unanchored)
    ("Appointment", rf"(?P<person>{PERSON})\s+{_WAS}{_APPOINTED}\s+(?:(?i:as)\s+)?{_PRE}(?P<role>{ROLE})\s+(?i:of|at)\s+(?P<company>{COMPANY})"),
    # P to be/become (the) new R of C
    ("Appointment", rf"(?P<person>{PERSON})\s+(?i:to)\s+(?i:be|become)\s+{_PRE}(?P<role>{ROLE})\s+(?i:of|at)\s+(?P<company>{COMPANY})$"),
]
COMPILED = [(mv, re.compile(rx)) for mv, rx in PATTERNS]

# tokens that disqualify a "person" capture (it grabbed a company/institution)
_NOT_PERSON = re.compile(
    r"\b(?:Bank|Banks|University|Universities|Institute|Hospital|Pharma|Pharmaceuticals?|College|Limited|Ltd|Inc|Corp|Group|Company|Technologies|Solutions|Services|Finance|Financial|Insurance|Capital|Board|Committee|Government|Ministry|Council|Authority|India|Global|International|Healthcare|Health|Labs?|Sciences?|Fund|Holdings?|Industries|Motors|Airlines|Media|Digital|Systems|Partners|Associates|School|Academy|Foundation|Trust|Agency|Department|Commission|Court|Share|Shares|Stock|Price|News|Report|Row|Case|Post|Yahoo|Reuters|Google|Its|The|New|Next|After|Amid|Former|Ex|Says|Say|Industry|Executive|Exec|Officer|Veteran|Vet|Leadership|Provost|Dean|Chancellor|Vice|Chairman|President|Director|As|Who|Will)\b",
    re.IGNORECASE)
_HONORIFIC = re.compile(r"^(?:Dr|Mr|Ms|Mrs|Prof|Justice)\.?\s+", re.IGNORECASE)

_COMPANY_TRIM = re.compile(
    r"^(?:the\s+|india['’]s\s+|indian\s+)|[\s,;:–—-]+$", re.IGNORECASE)
_COMPANY_TAIL = re.compile(
    r"\s+(?:for\s+(?:\d+|three|two|five)\s+years?.*|with\s+effect.*|effective\s+.*|from\s+\w+\s+\d.*|till\s+.*|until\s+.*)$",
    re.IGNORECASE)

ROLE_CANON = {
    "chief executive officer": "CEO", "chief financial officer": "CFO",
    "chief operating officer": "COO", "chief technology officer": "CTO",
    "chief information officer": "CIO", "chief marketing officer": "CMO",
    "chief human resources officer": "CHRO", "chief people officer": "CHRO",
    "chief medical officer": "Chief Medical Officer", "chief business officer": "CBO",
    "chief risk officer": "CRO", "chief digital officer": "CDO",
    "managing director": "MD", "md": "MD", "ceo": "CEO", "cfo": "CFO",
    "cto": "CTO", "coo": "COO", "cio": "CIO", "cmo": "CMO", "chro": "CHRO",
    "ciso": "CISO", "cmd": "CMD", "dmd": "Deputy MD", "amd": "Additional MD",
    "deputy managing director": "Deputy MD", "joint managing director": "Joint MD",
    "additional managing director": "Additional MD",
    "chairman": "Chairman", "chairperson": "Chairman", "chairwoman": "Chairman",
    "vice chancellor": "Vice Chancellor", "vc": "Vice Chancellor",
    "vice-chancellor": "Vice Chancellor", "pro vice chancellor": "Pro Vice Chancellor",
    "pro-vice-chancellor": "Pro Vice Chancellor", "in-charge vc": "Vice Chancellor (In-charge)",
    "executive director": "Executive Director", "whole-time director": "Whole-time Director",
    "whole time director": "Whole-time Director", "director general": "Director General",
    "president": "President", "executive vice president": "EVP",
    "director": "Director", "dean": "Dean", "registrar": "Registrar",
    "principal": "Principal", "provost": "Provost",
}


def canon_role(role):
    role = re.sub(r"\s+", " ", role.strip())
    parts = re.split(r"\s*(?:&|\band\b|,)\s*", role, flags=re.IGNORECASE)
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        c = ROLE_CANON.get(p.lower())
        if c is None:
            # word-wise: short tokens are acronyms (Md -> MD), rest Title Case
            c = " ".join(w.upper() if (len(w) <= 3 or w.isupper()) else w.title() for w in p.split())
        if c not in out:
            out.append(c)
    return " & ".join(out)


def clean_person(p):
    p = _HONORIFIC.sub("", p.strip())
    p = re.sub(r"^(?:CEO|CFO|CTO|COO|CIO|CMO|CHRO|CMD|DMD|AMD|MD|VC)\s+", "", p)  # "COO Khorshed Alam"
    p = re.sub(r"^[A-Z][\w.-]*['’]s\s+", "", p)  # "UNSW's Colin Grant" -> "Colin Grant"
    p = re.sub(r"\s+", " ", p)
    words = p.split()
    if not (2 <= len(words) <= 5):
        return None
    if _NOT_PERSON.search(p):
        return None
    if any(not w[0].isupper() for w in words):
        return None
    return p


def clean_company(c):
    if not c:
        return ""
    c = c.split(":")[0]  # "Tata Sons: Reports" -> "Tata Sons"
    c = c.strip().strip("\"'‘’“”")
    c = _COMPANY_TAIL.sub("", c)
    c = re.sub(r"['’]s(\s+new)?$", "", c)          # "HDFC Bank's new" -> "HDFC Bank"
    c = re.sub(r"\s+(?:share\s+price|stock|shares)\b.*$", "", c, flags=re.IGNORECASE)
    c = re.sub(r"\s+(?:faces|reports|announces|posts|sees|amid|after|following|says)\b.*$", "", c, flags=re.IGNORECASE)
    c = re.sub(r"\s+to\s+(?:drive|strengthen|accelerate|lead|boost|fuel|scale|spearhead|expand)\b.*$", "", c, flags=re.IGNORECASE)
    c = re.sub(r"^(?:next|new)\s+", "", c, flags=re.IGNORECASE)
    c = re.sub(r"\s+(?:Officially|Reportedly|Formally)$", "", c, flags=re.IGNORECASE)
    for _ in range(2):
        c = _COMPANY_TRIM.sub("", c)
    c = re.sub(r"\s+(?:Limited|Ltd\.?|Pvt\.?\s*Ltd\.?)$", "", c, flags=re.IGNORECASE)
    c = re.sub(r"\s+", " ", c).strip(" ,;:.-")
    if len(c) < 2 or len(c.split()) > 8:
        return ""
    if re.match(r"^(?:its|the|a|an|new|his|her|their)$", c, re.IGNORECASE):
        return ""
    return c


# for "RBI approves ..." rest-text: try "R of C" first, then "C('s) R"
_REST_ROLE_FIRST = re.compile(rf"^(?P<role>{ROLE})\s+(?i:of|at|in)\s+(?P<company>.+)$")
_REST_CO_FIRST = re.compile(rf"^(?P<company>.+?)(?:['’]s)?\s+(?P<role>{ROLE})$")


def _try_patterns(clause):
    for movement, rx in COMPILED:
        m = rx.search(clause)
        if not m:
            continue
        gd = m.groupdict()
        person = clean_person(gd.get("person") or "")
        if not person:
            continue
        role, company = gd.get("role"), gd.get("company")
        if "rest" in gd and gd["rest"]:
            rest = _COMPANY_TAIL.sub("", gd["rest"].strip())
            m2 = _REST_ROLE_FIRST.match(rest) or _REST_CO_FIRST.match(rest)
            if not m2:
                continue
            company, role = m2.group("company"), m2.group("role")
        company = clean_company(company or "")
        if not role:
            continue
        return {
            "person": person,
            "role": canon_role(role),
            "company": company,
            "movement": movement,
        }
    return None


def extract_all(title):
    """Parse a headline (possibly multi-clause) -> list of movement dicts."""
    t = title.rsplit(" - ", 1)[0].strip() if " - " in title else title.strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"^(?:Breaking|Exclusive|Just\s+in|Watch|Explained)\s*[:|–—-]\s*", "", t, flags=re.IGNORECASE)
    out = []
    for clause in re.split(r"\s*;\s*", t):
        rec = _try_patterns(clause)
        if rec:
            out.append(rec)
    return out


def extract(title):
    recs = extract_all(title)
    return recs[0] if recs else None


# ---------------------------------------------------------------- role groups
# A canonical role often names several posts at once ("MD & CEO", "President &
# CHRO"), so the first group that matches wins — the order below is the
# seniority tie-break. Slugs are the API endpoint suffixes.
ROLE_GROUPS = [
    ("CEO", "ceo", r"\bCEO\b|Chief\s+Executive"),
    ("MD", "md", r"\bMD\b|\bCMD\b|Managing\s+Director|Managing\s+Partner"),
    ("CFO", "cfo", r"\bCFO\b|Chief\s+Financial"),
    ("COO", "coo", r"\bCOO\b|Chief\s+Operating"),
    ("CMO", "cmo", r"\bCMO\b|Chief\s+Marketing|Chief\s+Brand"),
    ("CHRO", "chro", r"\bCHRO\b|Chief\s+(?:Human|People|Talent)"),
    ("CTO", "cto", r"\bCTO\b|\bCTIO\b|Chief\s+Techn"),
    ("CIO", "cio", r"\bCIO\b|Chief\s+Information\s+Officer"),
    ("CDO", "cdo", r"\bCDO\b|Chief\s+(?:Digital|Data)"),
    ("CISO", "ciso", r"\bCISO\b|Chief\s+Information\s+Security"),
    ("Other C-suite", "csuite", r"\bChief\b|\bCPO\b|\bCBO\b|\bCRO\b|\bCCO\b|\bCSO\b|\bCXO\b"),
    ("Chairman", "chairman", r"Chair(?:man|person|woman)"),
    ("Academic Leadership", "academic",
     r"\bChancellor\b|\bVC\b|\bDean\b|\bRegistrar\b|\bPrincipal\b|\bProvost\b|\bRector\b"),
    ("Board & Directors", "board", r"\bDirector\b"),
    ("Business Heads", "head",
     r"\bHead\b|Vice\s+President|\bVP\b|\bEVP\b|\bSVP\b|General\s+Manager"),
    ("President", "president", r"\bPresident\b"),
]
_ROLE_GROUPS = [(lbl, slug, re.compile(rx, re.IGNORECASE))
                for lbl, slug, rx in ROLE_GROUPS]
ROLE_GROUP_LABELS = [lbl for lbl, _, _ in ROLE_GROUPS] + ["Other"]
ROLE_GROUP_SLUG = dict([(lbl, slug) for lbl, slug, _ in ROLE_GROUPS] + [("Other", "other")])


def role_group_of(role):
    """Bucket a canonical role into one of ROLE_GROUP_LABELS."""
    for label, _slug, rx in _ROLE_GROUPS:
        if rx.search(role or ""):
            return label
    return "Other"


# ---------------------------------------------------------------- moved-from
_CO_PHRASE = r"[A-Z][\w&.'’-]*(?:\s+(?:of\s+)?[A-Z&][\w&.'’-]*){0,3}?"
_FILLER = r"(?:[a-z][\w&-]*\s+){0,2}"   # "finance", "food delivery", "oncology"
_FROM_ROLE = (r"(?i:executive|exec|officer|veteran|alum|banker|hand|leader|chief|head|"
              r"founder|co-founder|honcho|boss|"
              r"CEO|CFO|COO|CTO|CIO|CMO|CHRO|MD|president|director|chairman)")
_FROM_PATTERNS = [
    # "former Dr Reddy's executive", "ex-Visa finance head", "former Zomato food delivery CEO"
    re.compile(rf"(?i:\bformer|\bex)[-\s]+(?P<co>{_CO_PHRASE})(?:['’]s)?\s+{_FILLER}{_FROM_ROLE}"),
    # "joins X from Y", "moves from Y", "switches from Y"
    re.compile(rf"(?i:joins?\s+[^,;]*?\s+from|moves?\s+from|switches?\s+from|"
               rf"crosses\s+over\s+from)\s+(?P<co>{_CO_PHRASE})"),
    # "quits Y to join X", "leaves Y for X"
    re.compile(rf"(?i:quits|leaves|exits)\s+(?P<co>{_CO_PHRASE})\s+(?i:to\s+join|for)\b"),
    # "AstraZeneca oncology veteran Alan Barge"
    re.compile(rf"(?P<co>{_CO_PHRASE})\s+{_FILLER}(?i:veteran|alum|alumnus)\s+[A-Z]"),
]
_FROM_JUNK = re.compile(
    r"^(?:The|A|An|New|Its|His|Her|Their|India|Indian|Global|Group|Board|Company|"
    r"Former|Ex|Veteran|Senior|Chief|Executive|Managing|Deputy|Director|President|"
    r"CEO|CFO|COO|CTO|MD|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|"
    r"March|April|May|June|July|August|September|October|"
    r"November|December|January|February|Monday|Tuesday|Wednesday|Thursday|Friday)"
    r"(?:\s+\d.*)?$",
    re.IGNORECASE)


def extract_moved_from(title, dest_company):
    """Previous employer, if the headline names one. '' otherwise."""
    t = title.rsplit(" - ", 1)[0] if " - " in title else title
    dest = re.sub(r"[^a-z0-9]", "", (dest_company or "").lower())
    for rx in _FROM_PATTERNS:
        m = rx.search(t)
        if not m:
            continue
        co = clean_company(m.group("co"))
        if not co or _FROM_JUNK.match(co):
            continue
        if co.split()[0].lower() in ("adds", "names", "appoints", "taps", "welcomes",
                                     "hires", "elevates", "promotes", "and", "with", "as"):
            continue
        key = re.sub(r"[^a-z0-9]", "", co.lower())
        # must not be the destination itself (or a prefix of it)
        if dest and (key == dest or dest.startswith(key) or key.startswith(dest)):
            continue
        return co
    return ""


# ---------------------------------------------------------------- region + sector
INDIA_PUBS = {
    "moneycontrol", "economic times", "economictimes", "livemint", "mint",
    "business standard", "businessline", "the hindu", "hindustan times", "ndtv",
    "fortune india", "hr katha", "banking frontiers", "afaqs", "exchange4media",
    "medical dialogues", "deccan herald", "deccanherald", "indian express",
    "outlookbusiness", "outlook", "business outreach", "adgully", "ciol",
    "indian pharma post", "times of india", "timesofindia", "telegraph india",
    "free press journal", "zee", "abp", "psu watch", "cnbctv18", "cnbc tv18",
    "financial express", "business today", "india today", "et now", "news18",
    "firstpost", "the print", "theprint", "scroll", "the wire", "tribune",
    "pharmabiz", "express pharma", "express healthcare", "biospectrum",
    "careers360", "shiksha", "edexlive", "impact magazine", "storyboard18",
    "medianews4u", "elets", "businessworld", "inc42", "entrackr", "yourstory",
    "vccircle", "the ken", "morning context", "scanx", "angel one", "5paisa",
    "upstox", "groww", "dalal street", "equitymaster", "capital market",
    "people matters", "ani news", "pti", "ians", "devdiscourse", "swarajya",
    "oneindia", "republic", "wion", "dd news", "the week", "frontline",
    "sakshi", "eenadu", "mathrubhumi", "lokmat", "amar ujala", "jagran",
    "patrika", "navbharat", "dainik",
}
INDIA_SIGNALS = re.compile(
    r"\b(?:India|Indian|RBI|SEBI|IRDAI|NABARD|SIDBI|UGC|AICTE|NITI|IIT|IIM|NIT|AIIMS|IGNOU|"
    r"Mumbai|Delhi|Bengaluru|Bangalore|Chennai|Kolkata|Hyderabad|Pune|Ahmedabad|Gurugram|Gurgaon|Noida|Lucknow|Jaipur|Chandigarh|Kochi|Indore|Nagpur|Bhopal|Patna|"
    r"Kerala|Karnataka|Maharashtra|Gujarat|Rajasthan|Punjab|Haryana|Assam|Bihar|Odisha|Telangana|Tamil\s*Nadu|Uttar\s*Pradesh|Madhya\s*Pradesh|West\s*Bengal|Andhra|Jharkhand|Chhattisgarh|Uttarakhand|Himachal|Goa|Manipur|Meghalaya|Tripura|Nagaland|Mizoram|Sikkim|Kashmir|Ladakh|"
    r"SBI|HDFC|ICICI|Axis|Kotak|IndusInd|Yes\s+Bank|PNB|Canara|Bank\s+of\s+Baroda|Union\s+Bank|LIC|Bajaj|Tata|Reliance|Adani|Birla|Mahindra|Infosys|Wipro|TCS|HCL|Jio|Airtel|Vedanta|ITC|Maruti|Hero|Godrej|Dabur|Cipla|Lupin|Biocon|Zydus|Glenmark|Torrent|Sun\s+Pharma|Dr\.?\s*Reddy|Apollo|Fortis|Max\s+Healthcare|Manipal|Narayana|NIMHANS|Paytm|PhonePe|Razorpay|Zerodha|Byju|Unacademy|UPSC|NEET|CBSE|ICSE|Manappuram|Muthoot|Shriram|Chola|IDFC|RBL|Federal\s+Bank|South\s+Indian\s+Bank|Karur|Tamilnad|Ujjivan|Equitas|Fincare|Jana|AU\s+Small|Utkarsh|Suryoday|ESAF)\b")


# explicitly non-Indian entities that Indian-named publishers report on
# ("The Business Standard" / "The Financial Express" are also Bangladeshi papers)
FOREIGN_SIGNALS = re.compile(
    r"\b(?:Dhaka|Bangladesh|Chattogram|Sonali\s+Bank|Meghna\s+Bank|Janata\s+Bank|"
    r"Agrani\s+Bank|Rupali\s+Bank|Pubali\s+Bank|Krishi\s+Bank|Islami\s+Bank|"
    r"Shahjalal|NCC\s+Bank|ONE\s+Bank|United\s+Commercial\s+Bank|Mutual\s+Trust\s+Bank|"
    r"Modhumoti|BRAC\s+Bank|Pakistan|Karachi|Lahore|Sri\s+Lanka|Colombo|Nepal|"
    r"Kathmandu|Tribhuvan|Nabil\s+Bank|Bhutan|Maldives)\b")


def region_of(title, publisher, company=""):
    if FOREIGN_SIGNALS.search(title) or (company and FOREIGN_SIGNALS.search(company)):
        return "Global"
    pub = (publisher or "").lower()
    if any(p in pub for p in INDIA_PUBS) or pub.endswith(".in"):
        return "India"
    if INDIA_SIGNALS.search(title):
        return "India"
    return "Global"


_SECT = [
    ("Pharma", re.compile(r"\b(?:pharma|pharmaceuticals?|biotech|bio\s?sciences?|life\s+sciences|vaccines?|drugs?|therapeutics|biosimilars?|generics|Cipla|Lupin|Biocon|Zydus|Glenmark|Novartis|Pfizer|AstraZeneca|GSK|Sanofi)\b", re.IGNORECASE)),
    ("Healthcare", re.compile(r"\b(?:diagnostics|hospitals?|healthcare|health\s*tech|health\s+system|medtech|medical|medicine|clinics?|wellness|oncology|cardiology|telemedicine|Apollo|Fortis|Medanta|Manipal|Narayana|NIMHANS)\b", re.IGNORECASE)),
    ("Education", re.compile(r"\b(?:university|universities|college|school|edtech|ed-tech|education|academic|learning|vice[- ]chancellor|chancellor|dean|registrar|provost|IIT|IIM|NIT|AIIMS|campus|institute\s+of|UGC|AICTE|academy)\b", re.IGNORECASE)),
    ("BFSI", re.compile(r"\b(?:bank|banking|banks|NBFC|insurance|insurer|reinsurance|mutual\s+fund|AMC|asset\s+management|fintech|finance|financial|lender|micro\s?finance|payments?|securities|broking|brokerage|wealth|credit\s+(?:card|union)|RBI|SEBI|IRDAI|stock\s+exchange|life\s+insurance)\b", re.IGNORECASE)),
]
_SECT_MAP = dict(_SECT)
# feeds that mix pharma and hospital stories (and all pre-split raw items)
# carry this hint; it resolves per headline below
_MIXED_PH = "Pharma & Healthcare"


def sector_of(title, hint, company=""):
    # the company name is the most specific signal ("Keck Medicine", "Webster Bank")
    if company:
        for name, rx in _SECT:
            if rx.search(company):
                return name
    if hint == _MIXED_PH:
        # Pharma and Healthcare lead _SECT, so they win when the title is
        # ambiguous; a clearly-BFSI/Education title still escapes the bucket
        for name, rx in _SECT:
            if rx.search(title):
                return name
        return "Healthcare"
    # if the feed's own sector is confirmed anywhere in the title, trust it
    if hint in _SECT_MAP and _SECT_MAP[hint].search(title):
        return hint
    for name, rx in _SECT:
        if rx.search(title):
            return name
    return hint
