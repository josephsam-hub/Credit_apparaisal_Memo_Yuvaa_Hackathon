"""
scorer.py — Five Cs of Credit Scorer for Intelli-Credit
Scores a company across Character, Capacity, Capital, Collateral, Conditions
with SHAP-style explainability (rule-based, no ML needed for hackathon).
"""

from dataclasses import dataclass, field
from typing import Any


# ── Data classes ──────────────────────────────────────────────────────────────
@dataclass
class FiveCScore:
    character:   float = 0.0   # Promoter integrity, fraud, litigation
    capacity:    float = 0.0   # Repayment ability, DSCR, NPA history
    capital:     float = 0.0   # Net worth, leverage, MCA compliance
    collateral:  float = 0.0   # Security, asset coverage
    conditions:  float = 0.0   # Sector outlook, macro risk

    # Explanations for each C (SHAP-style: "because...")
    character_reasons:  list = field(default_factory=list)
    capacity_reasons:   list = field(default_factory=list)
    capital_reasons:    list = field(default_factory=list)
    collateral_reasons: list = field(default_factory=list)
    conditions_reasons: list = field(default_factory=list)

    @property
    def overall(self) -> float:
        """Weighted overall score (0-100). Higher = riskier."""
        return round(
            self.character  * 0.30 +   # Character is most important in Indian credit
            self.capacity   * 0.25 +
            self.capital    * 0.20 +
            self.collateral * 0.15 +
            self.conditions * 0.10,
            1
        )

    @property
    def recommendation(self) -> str:
        if self.character >= 70:    return "REJECT"   # Fraud/ED = auto reject
        if self.overall >= 65:      return "REJECT"
        if self.overall >= 45:      return "CAUTION"
        return "APPROVE"

    @property
    def suggested_rate(self) -> str:
        if self.recommendation == "REJECT":  return "N/A"
        if self.overall >= 35:               return "14.5% - 16%"
        if self.overall >= 20:               return "12% - 14%"
        return "10.5% - 12%"

    @property
    def risk_grade(self) -> str:
        if self.overall >= 65:  return "D"
        if self.overall >= 45:  return "C"
        if self.overall >= 25:  return "B"
        return "A"


# ── Main Scorer ───────────────────────────────────────────────────────────────
class FiveCsScorer:
    """
    Rule-based Five Cs scorer with full explainability.
    Each rule produces a score delta AND a human-readable reason.
    This is what judges see when they ask "why did it decide this?"
    """

    def score(
        self,
        financials: dict[str, Any],
        gst_analysis: dict[str, Any],
        research_output: dict[str, Any],
        user_notes: str = "",
    ) -> FiveCScore:
        s = FiveCScore()

        self._score_character(s, research_output, user_notes)
        self._score_capacity(s, financials, gst_analysis)
        self._score_capital(s, financials)
        self._score_collateral(s, financials, user_notes)
        self._score_conditions(s, research_output)

        return s

    # ── C1: Character ─────────────────────────────────────────────────────────
    def _score_character(self, s: FiveCScore, research: dict, notes: str):
        r = research

        # Check promoter risk level from Pillar 2 research
        promoter_risk = str(r.get("promoter_risk_level", "")).upper()
        if promoter_risk == "CRITICAL":
            s.character += 80
            s.character_reasons.append("🔴 CRITICAL: ED/CBI/SFIO investigation found against promoter — automatic red flag")
        elif promoter_risk == "HIGH":
            s.character += 55
            s.character_reasons.append("🟠 HIGH: Serious promoter integrity concerns found in external research")
        elif promoter_risk == "MEDIUM":
            s.character += 30
            s.character_reasons.append("🟡 MEDIUM: Some adverse promoter findings — needs further verification")
        else:
            s.character += 5
            s.character_reasons.append("🟢 No adverse promoter findings in external research")

        # Litigation risk
        litigation_risk = str(r.get("litigation_risk_level", "")).upper()
        if litigation_risk == "HIGH":
            s.character += 20
            s.character_reasons.append("🟠 Active NCLT/DRT litigation found — significant legal risk")
        elif litigation_risk == "MEDIUM":
            s.character += 10
            s.character_reasons.append("🟡 Some litigation found — monitor closely")

        # Regulatory findings
        reg = str(r.get("regulatory_findings", "")).lower()
        if any(k in reg for k in ["gst raid", "it survey", "sebi ban", "rbi action"]):
            s.character += 15
            s.character_reasons.append("🟠 Regulatory action (GST raid/IT survey/SEBI) found in research")

        # NPA/Wilful defaulter
        npa = str(r.get("npa_default_history", "")).lower()
        if "wilful defaulter" in npa:
            s.character += 40
            s.character_reasons.append("🔴 CRITICAL: Wilful defaulter listing found — loan must be rejected per RBI norms")
        elif "npa" in npa and "no adverse" not in npa:
            s.character += 15
            s.character_reasons.append("🟠 NPA history found — repayment character concern")

        # User notes override
        notes_lower = notes.lower()
        if any(k in notes_lower for k in ["fraud", "fake", "bogus", "suspicious"]):
            s.character += 20
            s.character_reasons.append("🟠 Credit officer flagged concerns in site visit notes")
        elif "good" in notes_lower or "clean" in notes_lower:
            s.character -= 5
            s.character_reasons.append("🟢 Credit officer reported positive site visit observations")

        s.character = max(0, min(100, s.character))

    # ── C2: Capacity ──────────────────────────────────────────────────────────
    def _score_capacity(self, s: FiveCScore, fin: dict, gst: dict):
        # DSCR — Debt Service Coverage Ratio (ideal > 1.5)
        dscr = float(fin.get("dscr", 1.5))
        if dscr < 1.0:
            s.capacity += 60
            s.capacity_reasons.append(f"🔴 DSCR {dscr:.2f} < 1.0 — company cannot service debt from operations")
        elif dscr < 1.25:
            s.capacity += 35
            s.capacity_reasons.append(f"🟠 DSCR {dscr:.2f} is weak (Vivriti minimum: 1.25)")
        elif dscr < 1.5:
            s.capacity += 15
            s.capacity_reasons.append(f"🟡 DSCR {dscr:.2f} is acceptable but below ideal 1.5x")
        else:
            s.capacity += 0
            s.capacity_reasons.append(f"🟢 DSCR {dscr:.2f} is healthy (above 1.5x threshold)")

        # Revenue trend
        revenue_growth = float(fin.get("revenue_growth_pct", 0))
        if revenue_growth < -10:
            s.capacity += 25
            s.capacity_reasons.append(f"🔴 Revenue declined {abs(revenue_growth):.0f}% — severe capacity concern")
        elif revenue_growth < 0:
            s.capacity += 15
            s.capacity_reasons.append(f"🟠 Revenue declined {abs(revenue_growth):.0f}% — negative growth trend")
        elif revenue_growth > 15:
            s.capacity -= 5
            s.capacity_reasons.append(f"🟢 Strong revenue growth of {revenue_growth:.0f}%")

        # GST circular trading flag
        if gst:
            gst_risk = str(gst.get("overall_risk_level", "")).upper()
            if gst_risk == "CRITICAL":
                s.capacity += 30
                s.capacity_reasons.append("🔴 GST analysis: CRITICAL circular trading / revenue inflation detected")
            elif gst_risk == "HIGH":
                s.capacity += 20
                s.capacity_reasons.append("🟠 GST analysis: HIGH risk — possible revenue misrepresentation")
            elif gst_risk == "MEDIUM":
                s.capacity += 10
                s.capacity_reasons.append("🟡 GST analysis: MEDIUM risk flags — verify financials independently")
            else:
                s.capacity_reasons.append("🟢 GST reconciliation: No material discrepancies found")

        s.capacity = max(0, min(100, s.capacity))

    # ── C3: Capital ───────────────────────────────────────────────────────────
    def _score_capital(self, s: FiveCScore, fin: dict):
        # Debt-to-Equity ratio
        de_ratio = float(fin.get("debt_to_equity", 1.5))
        if de_ratio > 4.0:
            s.capital += 50
            s.capital_reasons.append(f"🔴 D/E ratio {de_ratio:.1f}x — dangerously over-leveraged")
        elif de_ratio > 2.5:
            s.capital += 30
            s.capital_reasons.append(f"🟠 D/E ratio {de_ratio:.1f}x — high leverage")
        elif de_ratio > 1.5:
            s.capital += 15
            s.capital_reasons.append(f"🟡 D/E ratio {de_ratio:.1f}x — moderate leverage")
        else:
            s.capital_reasons.append(f"🟢 D/E ratio {de_ratio:.1f}x — conservative leverage")

        # Net worth
        net_worth_cr = float(fin.get("net_worth_cr", 50))
        loan_amount_cr = float(fin.get("loan_amount_cr", 25))
        if net_worth_cr < loan_amount_cr:
            s.capital += 25
            s.capital_reasons.append(f"🔴 Net worth ₹{net_worth_cr:.0f}Cr < Loan amount ₹{loan_amount_cr:.0f}Cr — inadequate capital base")
        elif net_worth_cr < loan_amount_cr * 2:
            s.capital += 10
            s.capital_reasons.append(f"🟡 Net worth ₹{net_worth_cr:.0f}Cr — moderate coverage of loan amount")
        else:
            s.capital_reasons.append(f"🟢 Net worth ₹{net_worth_cr:.0f}Cr — adequate capital cushion")

        s.capital = max(0, min(100, s.capital))

    # ── C4: Collateral ────────────────────────────────────────────────────────
    def _score_collateral(self, s: FiveCScore, fin: dict, notes: str):
        collateral_cover = float(fin.get("collateral_coverage", 1.25))
        if collateral_cover < 1.0:
            s.collateral += 50
            s.collateral_reasons.append(f"🔴 Collateral coverage {collateral_cover:.2f}x — insufficient security")
        elif collateral_cover < 1.25:
            s.collateral += 25
            s.collateral_reasons.append(f"🟠 Collateral coverage {collateral_cover:.2f}x — below Vivriti minimum 1.25x")
        elif collateral_cover < 1.5:
            s.collateral += 10
            s.collateral_reasons.append(f"🟡 Collateral coverage {collateral_cover:.2f}x — acceptable")
        else:
            s.collateral_reasons.append(f"🟢 Collateral coverage {collateral_cover:.2f}x — well secured")

        # Personal guarantee
        notes_lower = notes.lower()
        if "personal guarantee" in notes_lower or "pg " in notes_lower:
            s.collateral -= 10
            s.collateral_reasons.append("🟢 Personal guarantee offered by promoter")

        s.collateral = max(0, min(100, s.collateral))

    # ── C5: Conditions ────────────────────────────────────────────────────────
    def _score_conditions(self, s: FiveCScore, research: dict):
        sector_risk = str(research.get("sector_risk_level", "MEDIUM")).upper()
        if sector_risk == "HIGH":
            s.conditions += 40
            s.conditions_reasons.append("🟠 Sector faces HIGH regulatory or market headwinds")
        elif sector_risk == "MEDIUM":
            s.conditions += 20
            s.conditions_reasons.append("🟡 Sector has moderate risk — standard monitoring required")
        else:
            s.conditions += 5
            s.conditions_reasons.append("🟢 Sector outlook is stable")

        outlook = str(research.get("sector_outlook", "")).lower()
        if any(k in outlook for k in ["rbi ban", "ministry action", "import duty", "overcapacity"]):
            s.conditions += 20
            s.conditions_reasons.append("🟠 Specific regulatory/policy risk identified in sector")

        s.conditions = max(0, min(100, s.conditions))


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    scorer = FiveCsScorer()

    # Scenario A: Clean company
    print("=" * 60)
    print("SCENARIO A: Clean Manufacturing Co")
    print("=" * 60)
    score_a = scorer.score(
        financials={"dscr": 1.8, "revenue_growth_pct": 12, "debt_to_equity": 1.2,
                    "net_worth_cr": 80, "loan_amount_cr": 25, "collateral_coverage": 1.6},
        gst_analysis={"overall_risk_level": "LOW"},
        research_output={"promoter_risk_level": "LOW", "litigation_risk_level": "LOW",
                         "npa_default_history": "No adverse findings",
                         "regulatory_findings": "No adverse findings",
                         "sector_risk_level": "LOW", "sector_outlook": "stable"},
        user_notes="Site visit good. Personal guarantee offered."
    )
    print(f"Overall Risk Score : {score_a.overall}/100")
    print(f"Risk Grade         : {score_a.risk_grade}")
    print(f"Recommendation     : {score_a.recommendation}")
    print(f"Suggested Rate     : {score_a.suggested_rate}")
    print(f"\nFive Cs Breakdown:")
    print(f"  Character  (C1): {score_a.character:.0f}/100")
    for r in score_a.character_reasons: print(f"    {r}")
    print(f"  Capacity   (C2): {score_a.capacity:.0f}/100")
    for r in score_a.capacity_reasons: print(f"    {r}")
    print(f"  Capital    (C3): {score_a.capital:.0f}/100")
    print(f"  Collateral (C4): {score_a.collateral:.0f}/100")
    print(f"  Conditions (C5): {score_a.conditions:.0f}/100")

    # Scenario B: Bhushan Steel type
    print("\n" + "=" * 60)
    print("SCENARIO B: Bhushan Steel (WOW Demo)")
    print("=" * 60)
    score_b = scorer.score(
        financials={"dscr": 0.8, "revenue_growth_pct": -5, "debt_to_equity": 3.8,
                    "net_worth_cr": 200, "loan_amount_cr": 500, "collateral_coverage": 1.1},
        gst_analysis={"overall_risk_level": "HIGH"},
        research_output={"promoter_risk_level": "CRITICAL",
                         "litigation_risk_level": "HIGH",
                         "npa_default_history": "NCLT insolvency proceedings. Multiple bank NPAs.",
                         "regulatory_findings": "ED investigation. SFIO probe.",
                         "sector_risk_level": "HIGH",
                         "sector_outlook": "overcapacity and import duty risks"},
        user_notes="Site visit completed. Plant operational."
    )
    print(f"Overall Risk Score : {score_b.overall}/100")
    print(f"Risk Grade         : {score_b.risk_grade}")
    print(f"Recommendation     : {score_b.recommendation}")
    print(f"\nFive Cs Breakdown:")
    print(f"  Character  (C1): {score_b.character:.0f}/100  ← WOW: ED investigation found")
    for r in score_b.character_reasons: print(f"    {r}")
    print(f"  Capacity   (C2): {score_b.capacity:.0f}/100")
    print(f"  Capital    (C3): {score_b.capital:.0f}/100")
    print(f"  Conditions (C5): {score_b.conditions:.0f}/100")