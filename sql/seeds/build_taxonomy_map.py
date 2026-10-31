"""Build sql/seeds/taxonomy_map.csv: CFPB product/issue labels (2011-2026,
across the 2017-04 and 2023-08 category rebuilds) -> stable buckets.

taxonomy_map columns:
  kind         'product' or 'issue'
  product      CFPB product label
  sub_label    sub-product (kind='product') or issue (kind='issue'); '' = null
  bucket       stable bucket

Product buckets (11) cover every product. Issue buckets (10) cover every issue
filed under a credit product bucket (credit_card, personal_loan,
vehicle_loan, prepaid_card); issues under other products map to 'other'.
`hardship_share` = issue buckets payment_trouble + collections.

Run once against the staged complaints; the CSV is committed and the test
suite fails if a new label appears that the map does not cover.
"""
from __future__ import annotations

import csv
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "sql" / "seeds" / "taxonomy_map.csv"

PREPAID_SUBS = {"General-purpose prepaid card", "Government benefit card", "Gift card",
                "Payroll card", "Student prepaid card"}


def product_bucket(product: str, sub: str) -> str:
    if product in ("Credit card",):
        return "credit_card"
    if product == "Credit card or prepaid card":
        return "prepaid_card" if sub in PREPAID_SUBS else "credit_card"
    if product == "Prepaid card":
        return "prepaid_card"
    if product == "Consumer Loan":
        return "vehicle_loan" if sub in ("Vehicle loan", "Vehicle lease") else "personal_loan"
    if product.startswith("Payday loan"):
        return "personal_loan"
    if product == "Vehicle loan or lease":
        return "vehicle_loan"
    if product == "Mortgage":
        return "mortgage"
    if product == "Student loan":
        return "student_loan"
    if product in ("Bank account or service", "Checking or savings account"):
        return "deposit_account"
    if product.startswith("Credit reporting"):
        return "credit_reporting"
    if product == "Debt collection":
        return "debt_collection"
    if product.startswith("Money transfer") or product in ("Money transfers", "Virtual currency"):
        return "money_services"
    if product in ("Debt or credit management", "Other financial service"):
        return "other_financial"
    raise KeyError(f"unmapped product: {product!r} / {sub!r}")


CREDIT_PRODUCT_BUCKETS = {"credit_card", "personal_loan", "vehicle_loan", "prepaid_card"}

ISSUE_BUCKETS: dict[str, list[str]] = {
    # Consumer cannot pay: the core hardship signal.
    "payment_trouble": [
        "Struggling to pay your bill", "Struggling to pay your loan",
        "Problems when you are unable to pay", "Delinquent account",
        "Forbearance / Workout plans", "Bankruptcy", "Issues with repayment",
    ],
    # Collection activity by the lender, repossession, debt sale.
    "collections": [
        "Collection practices", "Collection debt dispute", "Sale of account",
        "Vehicle was repossessed or sold the vehicle",
        "Lender repossessed or sold the vehicle", "Repossession", "Property was sold",
        "Lender sold the property",
    ],
    "billing_transactions": [
        "Problem with a purchase shown on your statement", "Billing disputes",
        "Transaction issue", "Billing statement", "Problem with a purchase or transfer",
        "Unauthorized transactions/trans. issues", "Can't stop charges to bank account",
        "Can't stop withdrawals from your bank account",
        "Money was taken from your bank account on the wrong day or for the wrong amount",
        "Charged bank acct wrong day or amt", "Lost or stolen refund",
    ],
    "fees_interest": [
        "Fees or interest", "Charged fees or interest you didn't expect",
        "Charged fees or interest I didn't expect", "APR or interest rate", "Late fee",
        "Other fee", "Overlimit fee", "Cash advance fee", "Balance transfer fee",
        "Unexpected or other fees", "Unexpected fees", "Fees", "Problem with overdraft",
        "Problem with an overdraft",
    ],
    "fraud_identity": [
        "Identity theft / Fraud / Embezzlement", "Fraud or scam",
        "Received a loan you didn't apply for", "Received a loan I didn't apply for",
        "Unsolicited issuance of credit card", "Privacy",
        "Problem with fraud alerts or security freezes",
    ],
    # Application, origination, credit lines, opening/closing.
    "account_lifecycle": [
        "Getting a credit card", "Closing your account", "Closing/Cancelling account",
        "Application processing delay", "Credit determination", "Getting the loan",
        "Getting a line of credit", "Shopping for a loan or lease",
        "Shopping for a line of credit", "Taking out the loan or lease",
        "Getting a loan or lease",
        "Problem getting a card or closing an account",
        "Managing, opening, or closing account",
        "Managing, opening, or closing your mobile wallet account",
        "Credit limit changed", "Credit line increase/decrease",
        "Was approved for a loan, but didn't receive the money",
        "Was approved for a loan, but didn't receive money",
        "Applied for loan/did not receive money", "Problems receiving the advance",
    ],
    # Routine servicing: payments posting, payoff, using the card.
    "servicing": [
        "Problem when making payments", "Loan payment wasn't credited to your account",
        "Payment to acct not credited", "Payoff process",
        "Problem with the payoff process at the end of the loan",
        "Managing the loan or lease", "Managing the line of credit",
        "Problems at the end of the loan or lease",
        "Can't contact lender or servicer", "Can't contact lender",
        "Trouble using your card", "Trouble using the card",
        "Problem with cash advance", "Cash advance", "Balance transfer",
        "Convenience checks", "Adding money",
        "Vehicle was damaged or destroyed the vehicle",
        "Lender damaged or destroyed vehicle",
        "Property was damaged or destroyed property",
        "Lender damaged or destroyed property",
    ],
    "credit_reporting": [
        "Incorrect information on your report", "Credit reporting",
        "Problem with a credit reporting company's investigation into an existing problem",
        "Improper use of your report", "Unable to get your credit report or credit score",
        "Credit monitoring or identity theft protection services",
        "Problem with credit report or credit score",
    ],
    "terms_marketing": [
        "Other features, terms, or problems",
        "Advertising and marketing, including promotional offers",
        "Advertising and marketing", "Advertising", "Rewards",
        "Account terms and changes", "Problem with additional add-on products or services",
        "Credit card protection / Debt protection", "Arbitration",
        "Confusing or misleading advertising or marketing",
        "Confusing or missing disclosures", "Advertising, marketing or disclosures",
        "Overdraft, savings or rewards features",
    ],
    "other": [
        "Other", "Customer service / Customer relations", "Problem with customer service",
        "Problem with a company's investigation into an existing problem",
    ],
}
ISSUE_TO_BUCKET = {i: b for b, issues in ISSUE_BUCKETS.items() for i in issues}


def main() -> None:
    con = duckdb.connect(str(ROOT / "data" / "warehouse.duckdb"), read_only=True)
    prods = con.sql("""SELECT DISTINCT product, COALESCE(sub_product, '') FROM stg_complaints
                       ORDER BY 1, 2""").fetchall()
    issues = con.sql("""SELECT DISTINCT product, COALESCE(sub_product, ''), COALESCE(issue, '')
                        FROM stg_complaints""").fetchall()
    rows = [("product", p, s, product_bucket(p, s)) for p, s in prods]
    issue_rows = set()
    unmapped = set()
    for p, s, i in issues:
        if product_bucket(p, s) in CREDIT_PRODUCT_BUCKETS:
            b = ISSUE_TO_BUCKET.get(i)
            if b is None:
                unmapped.add(i)
                continue
        else:
            b = "other"
        issue_rows.add(("issue", p, i, b))
    if unmapped:
        raise SystemExit(f"unmapped credit issues: {sorted(unmapped)}")
    rows += sorted(issue_rows)
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["kind", "product", "sub_label", "bucket"])
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT}")


if __name__ == "__main__":
    main()
