# india_queries.py
# ─────────────────────────────────────────────────────────────────────
# CREATE this as a NEW file at:
#   intelli-credit/src/pillar2_research/company-researcher/src/agent/india_queries.py
#
# This is your SECRET WEAPON — no other team has these exact queries.
# Every query maps to a specific risk category in the Five Cs framework.
# ─────────────────────────────────────────────────────────────────────

def get_india_credit_queries(company_name: str, promoter_names: list, sector: str) -> list:
    """
    Generates India-specific credit risk search queries.

    WHY THESE QUERIES WIN:
    ─────────────────────
    Generic team query:  "ABC company news"             → useless
    Our query:           "ABC company ED enforcement    → finds actual fraud
                          directorate investigation"

    Each query targets exactly what Indian credit officers care about.
    Maps directly to Five Cs of Credit scoring.
    """

    # Safely get first promoter name (or use company name as fallback)
    promoter1 = promoter_names[0] if promoter_names else company_name
    promoter2 = promoter_names[1] if len(promoter_names) > 1 else promoter1

    queries = [

        # ── CHARACTER (C1): Promoter Integrity ────────────────────────────────
        # Most important for Indian credit — promoter fraud = automatic reject
        f"{company_name} promoter ED enforcement directorate investigation India",
        f"{promoter1} CBI SFIO fraud arrested chargesheet India",
        f"{promoter1} SEBI ban penalty director disqualified MCA",
        f"{promoter2} fraud case court India 2023 2024 2025",

        # ── CHARACTER (C1): Company-level legal trouble ────────────────────────
        f"{company_name} NCLT insolvency resolution proceeding IBC petition",
        f"{company_name} High Court Supreme Court judgment case India",
        f"{company_name} DRT debt recovery tribunal notice",
        f"{company_name} GST raid income tax survey search seizure",
        f"{company_name} fraud scam money laundering hawala India",

        # ── CAPACITY (C2): Loan repayment ability ─────────────────────────────
        f"{company_name} NPA non performing asset bank loan default",
        f"{company_name} wilful defaulter RBI CIBIL list",
        f"{company_name} loan recall notice bank account frozen",
        f"{company_name} revenue decline profit loss financial stress 2024",

        # ── CONDITIONS (C5): Sector & Regulatory risks ─────────────────────────
        f"{sector} India RBI SEBI regulation circular ban restriction 2024 2025",
        f"{sector} India industry slowdown headwind challenge outlook 2025",
        f"{company_name} regulatory notice show cause order penalty",

        # ── CAPITAL (C3): Financial health signals ─────────────────────────────
        f"{company_name} MCA ROC strike off charge creation filing default",
        f"{company_name} annual return default MCA21 ROC filing status",
    ]

    return queries


def classify_risk_signal(text: str) -> dict:
    """
    Scans a block of text for Indian credit risk keywords.
    Returns severity + matched signals + score contribution.

    Called after every web search to build the risk picture.

    Returns:
        severity      : "HIGH" | "MEDIUM" | "LOW" | "NONE"
        signals       : list of matched risk keywords
        risk_score_add: how much to add to the overall risk score
        five_c_impact : which of the Five Cs this affects
    """

    HIGH_RISK_KEYWORDS = [
        # Promoter enforcement (Character)
        "ED investigation", "enforcement directorate", "CBI case",
        "CBI investigation", "SFIO probe", "SFIO investigation",
        "arrested", "chargesheet filed", "money laundering",

        # SEBI/MCA actions (Character)
        "SEBI ban", "SEBI penalty", "SEBI order", "director disqualified",
        "DIN deactivated", "director banned",

        # Insolvency (Capacity + Capital)
        "NCLT insolvency", "insolvency resolution", "IBC proceedings",
        "corporate insolvency resolution", "liquidation order",

        # NPA/Default (Capacity)
        "wilful defaulter", "wilful default", "NPA classification",
        "account classified NPA", "loan recalled", "account frozen",
        "debt recovery tribunal",

        # Raids (Character)
        "GST raid", "income tax raid", "IT raid", "search and seizure",
        "tax evasion", "GST evasion",

        # Fraud (Character)
        "fraud case", "cheating case", "forgery", "misappropriation",
    ]

    MEDIUM_RISK_KEYWORDS = [
        # Legal disputes
        "court case", "litigation pending", "legal dispute",
        "arbitration", "show cause notice", "regulatory notice",

        # Loan stress
        "loan recall", "bank notice", "restructured loan",
        "one time settlement", "OTS", "SARFAESI notice",

        # MCA/Filing issues
        "charge creation", "charge satisfaction", "MCA default",
        "ROC notice", "delayed annual return",

        # Rating/financial stress
        "credit rating downgrade", "negative outlook",
        "rating watch", "profit decline", "revenue fall",

        # Management
        "key management resignation", "auditor resignation",
        "promoter pledge", "promoter shares pledged",
    ]

    LOW_RISK_KEYWORDS = [
        "controversy", "dispute", "complaint", "competition",
        "market share loss", "leadership change", "management change",
        "slow growth", "margin pressure",
    ]

    text_lower = text.lower()

    found_high   = [k for k in HIGH_RISK_KEYWORDS   if k.lower() in text_lower]
    found_medium = [k for k in MEDIUM_RISK_KEYWORDS if k.lower() in text_lower]
    found_low    = [k for k in LOW_RISK_KEYWORDS    if k.lower() in text_lower]

    all_signals = found_high + found_medium + found_low

    # Determine severity and score contribution
    if found_high:
        severity       = "HIGH"
        risk_score_add = 30 + (len(found_high) - 1) * 5   # 30 base + 5 per extra
        five_c_impact  = "Character"
    elif found_medium:
        severity       = "MEDIUM"
        risk_score_add = 15 + (len(found_medium) - 1) * 3
        five_c_impact  = "Capacity"
    elif found_low:
        severity       = "LOW"
        risk_score_add = 5
        five_c_impact  = "Conditions"
    else:
        severity       = "NONE"
        risk_score_add = 0
        five_c_impact  = None

    return {
        "severity":       severity,
        "signals":        all_signals,
        "high_signals":   found_high,
        "medium_signals": found_medium,
        "low_signals":    found_low,
        "risk_score_add": min(risk_score_add, 50),   # cap at 50 per search
        "five_c_impact":  five_c_impact,
    }