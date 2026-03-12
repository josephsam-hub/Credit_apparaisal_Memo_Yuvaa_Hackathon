"""
gst_reconciler.py
=================
Pillar 1 — GST Fraud Detector for Intelli-Credit

THIS IS YOUR BIGGEST DIFFERENTIATOR.
No open source repo in the world has this logic.
Vivriti Capital judges deal with this every single day.

WHAT THIS FILE DOES:
--------------------
Checks 4 types of fraud signals in Indian GST data:

  CHECK 1: GSTR-2A vs GSTR-3B mismatch
           → Self-declared turnover vs supplier-reported = fraud signal

  CHECK 2: Circular Trading Detection
           → Bank deposits much lower than GST turnover = fake invoices

  CHECK 3: ITC (Input Tax Credit) Overuse
           → Claiming more ITC than purchases justify = tax fraud

  CHECK 4: Filing Regularity
           → Frequent late filings = cash flow stress indicator

HOW TO RUN:
-----------
  python gst_reconciler.py
  (uses mock data built in — no files needed)

UNDERSTANDING GSTR-2A vs GSTR-3B (CRITICAL FOR DEMO):
-------------------------------------------------------
  GSTR-2A = AUTO-POPULATED from your suppliers' filings
            (what suppliers say they sold to you)

  GSTR-3B = SELF-DECLARED by the company
            (what the company says it sold/bought)

  If GSTR-3B turnover >> GSTR-2A:
    → Company is claiming MORE sales than suppliers reported
    → Classic sign of REVENUE INFLATION / CIRCULAR TRADING
    → Big red flag for credit officers
"""

from dataclasses import dataclass, field
from typing import List, Optional
import json

# ══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class GSTFlag:
    """Represents a single detected fraud/risk signal"""
    flag_type: str        # e.g. "GSTR_MISMATCH", "CIRCULAR_TRADING"
    severity: str         # "HIGH", "MEDIUM", "LOW"
    detail: str           # Human-readable explanation for the CAM report
    impact_score: int     # How much this adds to the risk score (0-100)
    evidence: dict = field(default_factory=dict)  # raw numbers that triggered flag


@dataclass
class GSTAnalysisResult:
    """Full result of GST analysis — fed into Five Cs scorer"""
    company_name: str
    fraud_risk_score: int          # 0–100 (higher = more risk)
    risk_level: str                # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    flags: List[GSTFlag]           # all detected risk flags
    summary: str                   # one-line summary for CAM report
    recommendation: str            # what the credit officer should do
    raw_data: dict = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN CLASS: GSTFraudDetector
# ══════════════════════════════════════════════════════════════════════════════

class GSTFraudDetector:
    """
    Analyzes GST data for fraud signals and circular trading patterns.

    Usage:
        detector = GSTFraudDetector()
        result = detector.analyze(
            company_name="ABC Pvt Ltd",
            gst_data={...},
            bank_data={...}
        )
        print(result.risk_level)  # "HIGH"
        print(result.flags)       # list of GSTFlag objects
    """

    # ── Risk thresholds ────────────────────────────────────────────────────────
    # These are based on real Indian credit underwriting standards

    GSTR_MISMATCH_MEDIUM = 0.10   # 10% variance = watch carefully
    GSTR_MISMATCH_HIGH   = 0.20   # 20% variance = serious red flag
    BANK_GST_RATIO_WARN  = 0.65   # Bank credits < 65% of GST = suspicious
    BANK_GST_RATIO_CRIT  = 0.45   # Bank credits < 45% of GST = circular trading
    ITC_RATIO_WARN       = 0.35   # ITC > 35% of output tax = overuse
    LATE_FILINGS_WARN    = 3      # more than 3 late filings = cash stress
    LATE_FILINGS_HIGH    = 6      # more than 6 = serious stress


    def analyze(
        self,
        company_name: str,
        gst_data: dict,
        bank_data: dict
    ) -> GSTAnalysisResult:
        """
        Main analysis function. Run all 4 checks and return full result.

        Parameters:
        -----------
        company_name : str  — name of the company (for report)
        gst_data     : dict — must contain keys shown in MOCK DATA below
        bank_data    : dict — must contain bank credit/debit totals

        Returns: GSTAnalysisResult with all flags, score, and recommendation
        """

        flags: List[GSTFlag] = []
        total_risk_score = 0

        print(f"\n🔍 Running GST Fraud Analysis for: {company_name}")
        print("─" * 55)

        # ── Run all 4 checks ──
        flags += self._check_gstr_mismatch(gst_data)
        flags += self._check_circular_trading(gst_data, bank_data)
        flags += self._check_itc_overuse(gst_data)
        flags += self._check_filing_regularity(gst_data)

        # ── Calculate total risk score ──
        total_risk_score = min(sum(f.impact_score for f in flags), 100)

        # ── Determine risk level ──
        if total_risk_score >= 70:
            risk_level = "CRITICAL"
        elif total_risk_score >= 45:
            risk_level = "HIGH"
        elif total_risk_score >= 20:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        # ── Build summary and recommendation ──
        summary = self._build_summary(company_name, flags, total_risk_score)
        recommendation = self._build_recommendation(risk_level, flags)

        return GSTAnalysisResult(
            company_name=company_name,
            fraud_risk_score=total_risk_score,
            risk_level=risk_level,
            flags=flags,
            summary=summary,
            recommendation=recommendation,
            raw_data={"gst_data": gst_data, "bank_data": bank_data}
        )


    # ══════════════════════════════════════════════════════════════════════════
    # CHECK 1: GSTR-2A vs GSTR-3B Mismatch
    # ══════════════════════════════════════════════════════════════════════════

    def _check_gstr_mismatch(self, gst_data: dict) -> List[GSTFlag]:
        """
        WHAT WE'RE CHECKING:
        ─────────────────────
        GSTR-2A = what suppliers REPORTED they sold to this company (auto-populated)
        GSTR-3B = what this company DECLARED as its turnover (self-reported)

        If GSTR-3B >> GSTR-2A by more than 10-20%:
        → Company is inflating its own revenue figures
        → Classic revenue inflation / fake invoice fraud

        REAL EXAMPLE:
        Company says it earned ₹100Cr (GSTR-3B)
        But suppliers only reported ₹60Cr of sales to them (GSTR-2A)
        → Where did the extra ₹40Cr come from?? 🚨
        """
        flags = []

        gstr_2a = gst_data.get("gstr_2a_turnover_cr", 0)
        gstr_3b = gst_data.get("gstr_3b_turnover_cr", 0)

        if gstr_2a <= 0 or gstr_3b <= 0:
            return []  # can't check without both values

        # Calculate variance: how much higher is 3B than 2A?
        variance = (gstr_3b - gstr_2a) / gstr_2a  # e.g. 0.25 = 25% higher

        print(f"  CHECK 1 — GSTR Mismatch:")
        print(f"    GSTR-2A (supplier-reported) : ₹{gstr_2a:.1f} Cr")
        print(f"    GSTR-3B (self-declared)     : ₹{gstr_3b:.1f} Cr")
        print(f"    Variance                    : {variance:+.1%}")

        if variance > self.GSTR_MISMATCH_HIGH:
            flag = GSTFlag(
                flag_type="GSTR_MISMATCH_HIGH",
                severity="HIGH",
                detail=(
                    f"GSTR-3B turnover (₹{gstr_3b:.1f}Cr) is {variance:.0%} higher than "
                    f"GSTR-2A (₹{gstr_2a:.1f}Cr). This significant discrepancy indicates "
                    f"possible revenue inflation or fictitious invoicing. "
                    f"Expected variance for genuine business: <10%."
                ),
                impact_score=35,
                evidence={"gstr_2a": gstr_2a, "gstr_3b": gstr_3b, "variance_pct": round(variance*100, 1)}
            )
            flags.append(flag)
            print(f"    ⚠️  HIGH RISK FLAG → revenue inflation suspected")

        elif variance > self.GSTR_MISMATCH_MEDIUM:
            flag = GSTFlag(
                flag_type="GSTR_MISMATCH_MEDIUM",
                severity="MEDIUM",
                detail=(
                    f"GSTR-3B turnover (₹{gstr_3b:.1f}Cr) is {variance:.0%} higher than "
                    f"GSTR-2A (₹{gstr_2a:.1f}Cr). Moderate variance — may be due to "
                    f"timing differences in supplier filings. Requires verification."
                ),
                impact_score=15,
                evidence={"gstr_2a": gstr_2a, "gstr_3b": gstr_3b, "variance_pct": round(variance*100, 1)}
            )
            flags.append(flag)
            print(f"    ⚠️  MEDIUM RISK FLAG → monitor closely")

        else:
            print(f"    ✅ PASS — variance within acceptable range")

        return flags


    # ══════════════════════════════════════════════════════════════════════════
    # CHECK 2: Circular Trading Detection
    # ══════════════════════════════════════════════════════════════════════════

    def _check_circular_trading(self, gst_data: dict, bank_data: dict) -> List[GSTFlag]:
        """
        WHAT WE'RE CHECKING:
        ─────────────────────
        Circular trading = companies create FAKE invoices between each other
        to artificially inflate their GST turnover (looks like big business)
        but no real money actually changes hands.

        HOW WE DETECT IT:
        In a REAL business: bank credits ≈ GST turnover
        (if you sold ₹100Cr worth of goods, roughly ₹100Cr should come into bank)

        In CIRCULAR TRADING: GST shows ₹100Cr turnover, but bank only gets ₹30Cr
        → The other ₹70Cr was just paper invoices with no real money movement
        → HUGE red flag — this is how companies get fraudulent credit

        REAL WORLD:
        This is exactly what happened in many NBFC/bank frauds in India.
        Vivriti Capital needs this check before every loan sanction.
        """
        flags = []

        gst_turnover = gst_data.get("gstr_3b_turnover_cr", 0)
        bank_credits = bank_data.get("total_annual_credits_cr", 0)

        if gst_turnover <= 0 or bank_credits <= 0:
            return []

        # Ratio: what fraction of GST turnover actually hit the bank?
        ratio = bank_credits / gst_turnover  # e.g. 0.45 = only 45% real

        print(f"\n  CHECK 2 — Circular Trading:")
        print(f"    GST Turnover (declared)   : ₹{gst_turnover:.1f} Cr")
        print(f"    Bank Credits (actual)     : ₹{bank_credits:.1f} Cr")
        print(f"    Bank-to-GST Ratio         : {ratio:.0%}")

        if ratio < self.BANK_GST_RATIO_CRIT:
            flag = GSTFlag(
                flag_type="CIRCULAR_TRADING_CRITICAL",
                severity="HIGH",
                detail=(
                    f"Bank credits (₹{bank_credits:.1f}Cr) are only {ratio:.0%} of "
                    f"GST declared turnover (₹{gst_turnover:.1f}Cr). "
                    f"This extreme divergence strongly suggests circular trading — "
                    f"companies issuing fake invoices to each other to inflate turnover "
                    f"without actual money movement. "
                    f"Genuine businesses typically show 70-100% bank-to-GST ratio."
                ),
                impact_score=45,
                evidence={"gst_turnover": gst_turnover, "bank_credits": bank_credits, "ratio": round(ratio, 2)}
            )
            flags.append(flag)
            print(f"    🚨 CRITICAL — Strong circular trading indicators!")

        elif ratio < self.BANK_GST_RATIO_WARN:
            flag = GSTFlag(
                flag_type="CIRCULAR_TRADING_SUSPECTED",
                severity="MEDIUM",
                detail=(
                    f"Bank credits (₹{bank_credits:.1f}Cr) are {ratio:.0%} of GST turnover "
                    f"(₹{gst_turnover:.1f}Cr). Below expected 65-100% range. "
                    f"Could indicate circular trading or significant cash transactions. "
                    f"Request explanation from management."
                ),
                impact_score=20,
                evidence={"gst_turnover": gst_turnover, "bank_credits": bank_credits, "ratio": round(ratio, 2)}
            )
            flags.append(flag)
            print(f"    ⚠️  MEDIUM — Bank credits below expected range")

        else:
            print(f"    ✅ PASS — Bank credits consistent with GST turnover")

        return flags


    # ══════════════════════════════════════════════════════════════════════════
    # CHECK 3: ITC (Input Tax Credit) Overuse
    # ══════════════════════════════════════════════════════════════════════════

    def _check_itc_overuse(self, gst_data: dict) -> List[GSTFlag]:
        """
        WHAT WE'RE CHECKING:
        ─────────────────────
        ITC = Input Tax Credit = tax you already paid to suppliers,
              which you can claim back (reduces your tax bill)

        FRAUD: Companies claim FAKE ITC by creating fake purchase invoices.
        They show they "bought" from fake suppliers to reduce their tax liability.

        HOW WE DETECT:
        Legitimate businesses: ITC is typically 15-30% of their output tax
        If ITC > 35% of output tax = suspiciously high = possible fake invoices

        NOTE: Industry-specific — manufacturing has high ITC, services have low.
        We flag for investigation, not automatic rejection.
        """
        flags = []

        itc_claimed = gst_data.get("input_tax_credit_cr", 0)
        output_tax = gst_data.get("output_tax_cr", 0)
        tax_paid = gst_data.get("total_tax_paid_cr", 0)

        if output_tax <= 0:
            return []

        itc_ratio = itc_claimed / output_tax if output_tax > 0 else 0

        print(f"\n  CHECK 3 — ITC Utilization:")
        print(f"    ITC Claimed  : ₹{itc_claimed:.2f} Cr")
        print(f"    Output Tax   : ₹{output_tax:.2f} Cr")
        print(f"    ITC Ratio    : {itc_ratio:.0%}")

        if itc_ratio > self.ITC_RATIO_WARN:
            flag = GSTFlag(
                flag_type="ITC_OVERUSE",
                severity="MEDIUM",
                detail=(
                    f"ITC claimed (₹{itc_claimed:.2f}Cr) is {itc_ratio:.0%} of output tax "
                    f"(₹{output_tax:.2f}Cr). Above typical range of 15-30% for this sector. "
                    f"May indicate fake purchase invoices to inflate ITC claims. "
                    f"Verify with GSTR-2A reconciliation and supplier confirmation."
                ),
                impact_score=15,
                evidence={"itc_claimed": itc_claimed, "output_tax": output_tax, "ratio": round(itc_ratio, 2)}
            )
            flags.append(flag)
            print(f"    ⚠️  MEDIUM — ITC utilization above expected range")
        else:
            print(f"    ✅ PASS — ITC utilization within normal range")

        return flags


    # ══════════════════════════════════════════════════════════════════════════
    # CHECK 4: Filing Regularity
    # ══════════════════════════════════════════════════════════════════════════

    def _check_filing_regularity(self, gst_data: dict) -> List[GSTFlag]:
        """
        WHAT WE'RE CHECKING:
        ─────────────────────
        GST returns must be filed monthly. Late filing = penalty.

        WHY THIS MATTERS FOR CREDIT:
        A company that keeps filing returns late = cash flow stress.
        If they can't manage a monthly compliance deadline, they're
        likely struggling to pay their bills on time too.

        This is a softer signal but consistent late filings = yellow flag.
        """
        flags = []

        monthly_filings = gst_data.get("monthly_filing_history", [])
        if not monthly_filings:
            print(f"\n  CHECK 4 — Filing Regularity: No monthly data available")
            return []

        # Count how many months had late filing (>0 days late)
        late_filings = [m for m in monthly_filings if m.get("days_late", 0) > 0]
        nil_returns = [m for m in monthly_filings if m.get("nil_return", False)]
        total_months = len(monthly_filings)

        print(f"\n  CHECK 4 — Filing Regularity:")
        print(f"    Total Months Analyzed : {total_months}")
        print(f"    Late Filings          : {len(late_filings)}")
        print(f"    Nil Returns           : {len(nil_returns)}")

        if len(late_filings) >= self.LATE_FILINGS_HIGH:
            flag = GSTFlag(
                flag_type="FREQUENT_LATE_FILINGS",
                severity="MEDIUM",
                detail=(
                    f"{len(late_filings)} out of {total_months} GST returns were filed late. "
                    f"Persistent late filings indicate chronic cash flow stress — "
                    f"company struggles to meet even statutory deadlines."
                ),
                impact_score=15,
                evidence={"late_count": len(late_filings), "total": total_months}
            )
            flags.append(flag)
            print(f"    ⚠️  MEDIUM — Persistent late filings detected")

        elif len(late_filings) >= self.LATE_FILINGS_WARN:
            flag = GSTFlag(
                flag_type="OCCASIONAL_LATE_FILINGS",
                severity="LOW",
                detail=(
                    f"{len(late_filings)} late GST filings in {total_months} months. "
                    f"Occasional delays — monitor for pattern."
                ),
                impact_score=5,
                evidence={"late_count": len(late_filings), "total": total_months}
            )
            flags.append(flag)
            print(f"    ⚠️  LOW — Some late filings, monitor")

        else:
            print(f"    ✅ PASS — Filing regularity is good")

        if len(nil_returns) >= 3:
            flag = GSTFlag(
                flag_type="MULTIPLE_NIL_RETURNS",
                severity="LOW",
                detail=(
                    f"{len(nil_returns)} nil GST returns filed. "
                    f"Multiple nil returns may indicate seasonal business or business slowdown."
                ),
                impact_score=5,
                evidence={"nil_count": len(nil_returns)}
            )
            flags.append(flag)

        return flags


    # ══════════════════════════════════════════════════════════════════════════
    # REPORT BUILDERS
    # ══════════════════════════════════════════════════════════════════════════

    def _build_summary(self, company_name: str, flags: List[GSTFlag], score: int) -> str:
        if not flags:
            return f"{company_name}: No GST fraud signals detected. Score: {score}/100 (LOW RISK)"

        high_flags = [f for f in flags if f.severity == "HIGH"]
        med_flags  = [f for f in flags if f.severity == "MEDIUM"]

        parts = []
        if high_flags:
            parts.append(f"{len(high_flags)} HIGH severity flag(s)")
        if med_flags:
            parts.append(f"{len(med_flags)} MEDIUM severity flag(s)")

        return (f"{company_name}: {', '.join(parts)} detected. "
                f"GST Fraud Risk Score: {score}/100")


    def _build_recommendation(self, risk_level: str, flags: List[GSTFlag]) -> str:
        recommendations = {
            "LOW":      "Proceed with standard due diligence. GST analysis shows no major concerns.",
            "MEDIUM":   "Request 3 years of GST filings and bank statements for detailed review. "
                        "Conduct management call to explain flagged variances before sanctioning.",
            "HIGH":     "ESCALATE to senior credit manager. Do not sanction without resolution of "
                        "all HIGH severity flags. Require CA-certified financial statements.",
            "CRITICAL": "REJECT or place on HOLD. Multiple critical fraud indicators detected. "
                        "Refer to credit risk committee. Consider filing SAR if applicable."
        }
        return recommendations.get(risk_level, "Review required.")


    def to_cam_text(self, result: GSTAnalysisResult) -> str:
        """
        Converts result to formatted text for the CAM report.
        Call this when generating the Word document.
        """
        lines = [
            f"GST ANALYSIS — {result.company_name}",
            f"{'─' * 50}",
            f"Risk Level    : {result.risk_level}",
            f"Risk Score    : {result.fraud_risk_score}/100",
            f"Flags Found   : {len(result.flags)}",
            f"",
            f"Summary: {result.summary}",
            f"",
            f"Recommendation: {result.recommendation}",
            f"",
        ]
        if result.flags:
            lines.append("DETAILED FLAGS:")
            for i, flag in enumerate(result.flags, 1):
                lines.append(f"  [{i}] [{flag.severity}] {flag.flag_type}")
                lines.append(f"      {flag.detail}")
                lines.append("")

        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# TEST — Run this file directly
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("=" * 60)
    print("  GST FRAUD DETECTOR — TEST RUN")
    print("=" * 60)

    detector = GSTFraudDetector()

    # ── TEST CASE 1: CLEAN company ──────────────────────────────────────────
    print("\n\n🟢 TEST 1: CLEAN COMPANY (should PASS all checks)")
    print("─" * 55)

    clean_gst = {
        "gstr_2a_turnover_cr": 95.0,   # Supplier says ₹95Cr
        "gstr_3b_turnover_cr": 100.0,  # Company says ₹100Cr → only 5% diff, OK
        "output_tax_cr": 18.0,
        "input_tax_credit_cr": 4.5,    # ITC = 25% of output tax, normal
        "total_tax_paid_cr": 13.5,
        "monthly_filing_history": [
            {"month": "Apr", "days_late": 0},
            {"month": "May", "days_late": 2},   # 2 days late, minor
            {"month": "Jun", "days_late": 0},
            {"month": "Jul", "days_late": 0},
            {"month": "Aug", "days_late": 0},
            {"month": "Sep", "days_late": 0},
        ]
    }
    clean_bank = {
        "total_annual_credits_cr": 88.0,  # 88% of GST turnover — looks real
    }

    result1 = detector.analyze("Clean Corp Pvt Ltd", clean_gst, clean_bank)
    print(f"\n  RESULT: {result1.risk_level} | Score: {result1.fraud_risk_score}/100")
    print(f"  Summary: {result1.summary}")

    # ── TEST CASE 2: FRAUD company ──────────────────────────────────────────
    print("\n\n🔴 TEST 2: FRAUD INDICATORS (should FLAG multiple issues)")
    print("─" * 55)

    fraud_gst = {
        "gstr_2a_turnover_cr": 50.0,    # Suppliers only reported ₹50Cr
        "gstr_3b_turnover_cr": 100.0,   # Company claims ₹100Cr → 100% gap! 🚨
        "output_tax_cr": 18.0,
        "input_tax_credit_cr": 9.5,     # ITC = 53% of output tax — suspiciously high
        "total_tax_paid_cr": 8.5,
        "monthly_filing_history": [
            {"month": "Apr", "days_late": 45},
            {"month": "May", "days_late": 60},
            {"month": "Jun", "days_late": 0},
            {"month": "Jul", "days_late": 30},
            {"month": "Aug", "days_late": 90},
            {"month": "Sep", "days_late": 15},
        ]
    }
    fraud_bank = {
        "total_annual_credits_cr": 35.0,  # Only ₹35Cr in bank vs ₹100Cr claimed 🚨
    }

    result2 = detector.analyze("Suspicious Corp Pvt Ltd", fraud_gst, fraud_bank)
    print(f"\n  RESULT: {result2.risk_level} | Score: {result2.fraud_risk_score}/100")
    print(f"\n  FLAGS DETECTED:")
    for flag in result2.flags:
        print(f"    [{flag.severity}] {flag.flag_type}: {flag.detail[:80]}...")

    # Print CAM text
    print("\n\n📋 CAM REPORT TEXT:")
    print("─" * 55)
    print(detector.to_cam_text(result2))

    # Save results to JSON
    output = {
        "test1_clean": {
            "risk_level": result1.risk_level,
            "score": result1.fraud_risk_score,
            "flags": len(result1.flags)
        },
        "test2_fraud": {
            "risk_level": result2.risk_level,
            "score": result2.fraud_risk_score,
            "flags": [{"type": f.flag_type, "severity": f.severity} for f in result2.flags]
        }
    }
    with open("gst_analysis_results.json", "w") as f:
        json.dump(output, f, indent=2)
    print("\n✅ Results saved to: gst_analysis_results.json")