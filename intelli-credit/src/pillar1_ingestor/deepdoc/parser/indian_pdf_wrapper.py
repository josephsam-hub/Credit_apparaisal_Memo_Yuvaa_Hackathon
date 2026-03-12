"""
indian_pdf_wrapper.py
=====================
Pillar 1 — PDF Parser for Intelli-Credit

WHAT THIS FILE DOES:
--------------------
1. Accepts any Indian corporate PDF (annual report, bank statement, GST)
2. Detects what type of document it is
3. Extracts text using pdfplumber (works without DeepDoc for now)
4. Sends text to Groq LLM (FREE) to extract financial fields
5. Returns clean structured JSON with all key financial data

HOW TO RUN:
-----------
  python indian_pdf_wrapper.py
  (put a PDF in the same folder first, update PDF_PATH below)

INSTALL (run once):
-------------------
  pip install langchain-groq langchain-core pdfplumber python-dotenv
"""

import os
import sys
import json
import pdfplumber                          # reads PDFs page by page
from dotenv import load_dotenv             # loads your .env file
from langchain_groq import ChatGroq        # FREE Groq LLM (no credit card)

# ── Load your .env keys ────────────────────────────────────────────────────────
load_dotenv()
# This reads GROQ_API_KEY from your .env file automatically
# Make sure your .env has:  GROQ_API_KEY=gsk_xxxxx

# ══════════════════════════════════════════════════════════════════════════════
# HELPER: Simple PDF text extractor (works without DeepDoc)
# ══════════════════════════════════════════════════════════════════════════════

def extract_text_from_pdf(pdf_path: str) -> dict:
    """
    Reads a PDF and returns:
    - full_text : all text joined together (for LLM analysis)
    - tables    : all tables found (for financial statements)
    - page_count: how many pages

    Uses pdfplumber which handles most Indian corporate PDFs well.
    If DeepDoc is installed, you can swap this out later.
    """
    full_text = ""
    all_tables = []

    with pdfplumber.open(pdf_path) as pdf:
        page_count = len(pdf.pages)

        for i, page in enumerate(pdf.pages):
            # ── Extract plain text from this page ──
            page_text = page.extract_text()
            if page_text:
                full_text += f"\n--- Page {i+1} ---\n{page_text}"

            # ── Extract tables from this page (P&L, Balance Sheet etc.) ──
            page_tables = page.extract_tables()
            if page_tables:
                for table in page_tables:
                    # Convert table rows to readable text
                    table_text = "\n".join(
                        [" | ".join(str(cell) for cell in row if cell)
                         for row in table if row]
                    )
                    all_tables.append({
                        "page": i + 1,
                        "content": table_text
                    })

    return {
        "full_text": full_text,
        "tables": all_tables,
        "page_count": page_count,
        "char_count": len(full_text)
    }


# ══════════════════════════════════════════════════════════════════════════════
# HELPER: Detect what type of document this is
# ══════════════════════════════════════════════════════════════════════════════

def detect_document_type(text: str) -> str:
    """
    Looks at the text and figures out what document this is.
    Routes it to the right extractor.

    Returns one of:
      "annual_report"   → extract company financials
      "bank_statement"  → extract credits, debits, cash flow
      "gst_filing"      → extract turnover, ITC, GSTR fields
      "legal_notice"    → extract case details, parties
      "unknown"         → ask user to label manually
    """
    text_lower = text.lower()

    # Keywords that identify each document type
    if any(kw in text_lower for kw in [
        "annual report", "board of directors", "auditor's report",
        "balance sheet", "profit and loss", "notes to accounts",
        "chairman's message", "ind as"
    ]):
        return "annual_report"

    elif any(kw in text_lower for kw in [
        "account statement", "transaction date", "credit", "debit",
        "opening balance", "closing balance", "bank statement",
        "account number", "ifsc", "neft", "rtgs"
    ]):
        return "bank_statement"

    elif any(kw in text_lower for kw in [
        "gstr", "gstin", "input tax credit", "itc", "taxable value",
        "gst return", "outward supplies", "inward supplies", "igst", "cgst", "sgst"
    ]):
        return "gst_filing"

    elif any(kw in text_lower for kw in [
        "court", "plaintiff", "defendant", "petition", "writ",
        "order", "high court", "supreme court", "nclt", "drt",
        "legal notice", "case number"
    ]):
        return "legal_notice"

    else:
        return "unknown"


# ══════════════════════════════════════════════════════════════════════════════
# MAIN CLASS: IndianDocumentParser
# ══════════════════════════════════════════════════════════════════════════════

class IndianDocumentParser:
    """
    The main parser class for Intelli-Credit.

    HOW IT WORKS:
    ─────────────
    Step 1: extract_text_from_pdf()  → raw text + tables from PDF
    Step 2: detect_document_type()   → figure out what kind of doc it is
    Step 3: call the right extractor → send text to Groq LLM with the right prompt
    Step 4: return structured JSON   → clean financial data ready for scoring

    SUPPORTED DOCUMENT TYPES:
    ─────────────────────────
    • Annual Reports   (most important)
    • Bank Statements
    • GST Filings
    • Legal Notices    (basic extraction)
    """

    def __init__(self):
        # ── Initialize Groq LLM (FREE — uses your GROQ_API_KEY from .env) ──
        self.llm = ChatGroq(
            model="llama-3.3-70b-versatile",  # Best free model available
            temperature=0,                     # 0 = deterministic, consistent output
            max_tokens=2000                    # enough for JSON financial data
        )
        print("✅ IndianDocumentParser ready | LLM: Groq llama-3.3-70b-versatile")


    # ── PUBLIC METHOD: Parse any document ─────────────────────────────────────

    def parse(self, pdf_path: str) -> dict:
        """
        Main entry point. Give it any PDF path.
        It auto-detects type and returns structured data.

        Usage:
            parser = IndianDocumentParser()
            result = parser.parse("annual_report.pdf")
            print(result["doc_type"])    # "annual_report"
            print(result["financials"])  # {revenue_cr: 450.2, ...}
        """

        print(f"\n📄 Parsing: {pdf_path}")

        # ── Step 1: Extract all text from PDF ──
        print("  → Extracting text from PDF...")
        extracted = extract_text_from_pdf(pdf_path)
        print(f"  → Found {extracted['page_count']} pages, "
              f"{extracted['char_count']:,} characters, "
              f"{len(extracted['tables'])} tables")

        if extracted["char_count"] < 200:
            print("  ⚠️  Very little text extracted — PDF might be scanned image")
            print("     Suggestion: use PaddleOCR for scanned PDFs")
            return {"error": "scanned_pdf", "message": "Install PaddleOCR for scanned documents"}

        # ── Step 2: Detect document type ──
        doc_type = detect_document_type(extracted["full_text"])
        print(f"  → Document type detected: {doc_type.upper()}")

        # ── Step 3: Route to right extractor ──
        if doc_type == "annual_report":
            financials = self._extract_annual_report(extracted)

        elif doc_type == "bank_statement":
            financials = self._extract_bank_statement(extracted)

        elif doc_type == "gst_filing":
            financials = self._extract_gst_filing(extracted)

        elif doc_type == "legal_notice":
            financials = self._extract_legal_notice(extracted)

        else:
            # Unknown doc — still try a generic extraction
            financials = self._extract_generic(extracted)

        print(f"  ✅ Extraction complete!")

        return {
            "doc_type": doc_type,
            "page_count": extracted["page_count"],
            "tables_found": len(extracted["tables"]),
            "raw_text": extracted["full_text"],   # keep full text for RAG/ChromaDB
            "financials": financials              # structured data for scoring
        }


    # ── EXTRACTOR 1: Annual Report ─────────────────────────────────────────────

    def _extract_annual_report(self, extracted: dict) -> dict:
        """
        Sends annual report text to Groq.
        Asks it to pull out all key Indian financial fields.
        """
        # Combine text + first few tables for context
        table_text = "\n".join([t["content"] for t in extracted["tables"][:5]])
        context = extracted["full_text"][:6000] + "\n\nTABLES:\n" + table_text[:2000]

        prompt = f"""You are a senior credit analyst at an Indian NBFC (like Vivriti Capital).
Analyze this Indian corporate Annual Report and extract financial data.

IMPORTANT RULES:
- All monetary values must be in Indian Crores (Cr)
- If a value is not found, use null (not 0)
- Return ONLY valid JSON, no explanation, no markdown

Annual Report Content:
{context}

Return this exact JSON structure:
{{
  "company_name": "",
  "financial_year": "",
  "sector": "",
  "revenue_cr": null,
  "net_profit_cr": null,
  "ebitda_cr": null,
  "total_debt_cr": null,
  "net_worth_cr": null,
  "total_assets_cr": null,
  "cash_cr": null,
  "dscr": null,
  "current_ratio": null,
  "debt_equity_ratio": null,
  "roe_percent": null,
  "promoter_names": [],
  "promoter_holding_percent": null,
  "auditor_name": "",
  "audit_qualifications": [],
  "related_party_txn_cr": null,
  "contingent_liabilities_cr": null,
  "employee_count": null,
  "red_flags": []
}}"""

        return self._call_llm(prompt)


    # ── EXTRACTOR 2: Bank Statement ────────────────────────────────────────────

    def _extract_bank_statement(self, extracted: dict) -> dict:
        """
        Extracts cash flow patterns, EMI obligations,
        and key banking metrics from bank statement.
        """
        context = extracted["full_text"][:5000]

        prompt = f"""You are analyzing an Indian corporate bank statement for credit appraisal.
Extract cash flow data. All values in Indian Crores (Cr). Return ONLY valid JSON.

Bank Statement Content:
{context}

Return this exact JSON:
{{
  "account_holder": "",
  "bank_name": "",
  "account_number_last4": "",
  "period_start": "",
  "period_end": "",
  "total_credits_cr": null,
  "total_debits_cr": null,
  "average_balance_cr": null,
  "min_balance_cr": null,
  "max_balance_cr": null,
  "emi_obligations_cr": null,
  "bounce_count": null,
  "inward_return_count": null,
  "cash_withdrawal_cr": null,
  "upi_transactions_cr": null,
  "red_flags": [],
  "stress_signals": []
}}"""

        return self._call_llm(prompt)


    # ── EXTRACTOR 3: GST Filing ────────────────────────────────────────────────

    def _extract_gst_filing(self, extracted: dict) -> dict:
        """
        Extracts GSTR data — critical for fraud detection.
        The GSTR-2A vs 3B comparison is done in gst_reconciler.py
        """
        context = extracted["full_text"][:5000]

        prompt = f"""You are analyzing Indian GST return filings for credit fraud detection.
Extract GST data. All values in Indian Crores (Cr). Return ONLY valid JSON.

GST Filing Content:
{context}

Return this exact JSON:
{{
  "gstin": "",
  "legal_name": "",
  "period": "",
  "gstr_type": "",
  "gstr3b_turnover_cr": null,
  "gstr2a_turnover_cr": null,
  "total_tax_paid_cr": null,
  "input_tax_credit_cr": null,
  "itc_utilized_cr": null,
  "itc_reversal_cr": null,
  "filing_date": "",
  "late_fee_paid": null,
  "nil_return": false,
  "red_flags": []
}}"""

        return self._call_llm(prompt)


    # ── EXTRACTOR 4: Legal Notice ──────────────────────────────────────────────

    def _extract_legal_notice(self, extracted: dict) -> dict:
        """Extracts basic legal case info from court documents"""
        context = extracted["full_text"][:4000]

        prompt = f"""Extract legal case details from this Indian court document.
Return ONLY valid JSON.

Document Content:
{context}

Return this JSON:
{{
  "case_number": "",
  "court_name": "",
  "plaintiff": "",
  "defendant": "",
  "case_type": "",
  "filing_date": "",
  "amount_disputed_cr": null,
  "current_status": "",
  "next_hearing": "",
  "summary": ""
}}"""

        return self._call_llm(prompt)


    # ── EXTRACTOR 5: Generic (unknown doc) ────────────────────────────────────

    def _extract_generic(self, extracted: dict) -> dict:
        """Fallback for unknown document types"""
        context = extracted["full_text"][:4000]

        prompt = f"""Extract any financial or business information from this Indian corporate document.
Return ONLY valid JSON.

Content:
{context}

Return JSON:
{{
  "document_summary": "",
  "key_entities": [],
  "financial_figures": {{}},
  "dates_mentioned": [],
  "risk_signals": []
}}"""

        return self._call_llm(prompt)


    # ── INTERNAL: Call Groq LLM safely ────────────────────────────────────────

    def _call_llm(self, prompt: str) -> dict:
        """
        Sends prompt to Groq, gets back JSON.
        Handles errors gracefully.
        """
        try:
            response = self.llm.invoke(prompt)
            text = response.content

            # LLM sometimes wraps JSON in markdown code blocks — strip them
            text = text.replace("```json", "").replace("```", "").strip()

            return json.loads(text)

        except json.JSONDecodeError:
            # LLM returned non-JSON — return raw text for debugging
            return {
                "error": "json_parse_failed",
                "raw_response": response.content[:500]
            }
        except Exception as e:
            return {
                "error": str(e),
                "message": "LLM call failed — check your GROQ_API_KEY in .env"
            }


# ══════════════════════════════════════════════════════════════════════════════
# QUICK TEST — run this file directly to test
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    # ── Change this to your actual PDF path ──
    PDF_PATH = "sample_annual_report.pdf"

    # ── Check if file exists ──
    if not os.path.exists(PDF_PATH):
        print(f"""
╔══════════════════════════════════════════════════════╗
║  TEST MODE — No PDF found at: {PDF_PATH:<22}║
║                                                      ║
║  To test this properly:                              ║
║  1. Download any annual report PDF from nseindia.com ║
║  2. Put it in the same folder as this file           ║
║  3. Change PDF_PATH above to your filename           ║
║  4. Run: python indian_pdf_wrapper.py                ║
╚══════════════════════════════════════════════════════╝

Running a MOCK TEST instead (no PDF needed)...
""")

        # ── MOCK TEST: test LLM connection without a real PDF ──
        print("Testing Groq LLM connection...")
        try:
            llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
            response = llm.invoke(
                "Say exactly this and nothing else: "
                '{\"status\": \"Groq connected\", \"model\": \"llama-3.3-70b-versatile\"}'
            )
            result = json.loads(response.content)
            print(f"\n✅ LLM CONNECTION SUCCESS!")
            print(f"   Model : {result.get('model')}")
            print(f"   Status: {result.get('status')}")
            print("\n✅ Your GROQ_API_KEY is working correctly.")
            print("   Now add a PDF to test full parsing.")

        except Exception as e:
            print(f"\n❌ LLM CONNECTION FAILED: {e}")
            print("\nCheck:")
            print("  1. Is GROQ_API_KEY set in your .env file?")
            print("  2. Run: pip install langchain-groq")
            print("  3. Get free key at: console.groq.com")

    else:
        # ── REAL TEST with actual PDF ──
        parser = IndianDocumentParser()

        print(f"\nParsing: {PDF_PATH}")
        result = parser.parse(PDF_PATH)

        print("\n" + "="*60)
        print("EXTRACTION RESULTS")
        print("="*60)
        print(f"Document Type : {result.get('doc_type', 'unknown').upper()}")
        print(f"Pages         : {result.get('page_count', 0)}")
        print(f"Tables Found  : {result.get('tables_found', 0)}")
        print(f"Text Length   : {len(result.get('raw_text', '')):,} chars")
        print("\nExtracted Financials:")
        print(json.dumps(result.get("financials", {}), indent=2))

        # Save result to JSON file
        output_file = PDF_PATH.replace(".pdf", "_extracted.json")
        with open(output_file, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\n✅ Saved to: {output_file}")