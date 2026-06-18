"""Run the README example end to end, fully offline, with no API key.

python examples/sql_case.py
"""

from __future__ import annotations

from agentic_testing_framework import Case, build_pipeline


def main() -> None:
    case = Case(
        input="Write a SQL query for total revenue per region in 2025.",
        output=(
            "SELECT region, SUM(amount) AS revenue FROM orders WHERE year=2025 GROUP BY region;"
        ),
        expectation="A correct, runnable SQL query answering the question.",
        criteria=[
            "Groups by region",
            "Sums a revenue/amount column",
            "Filters to the year 2025",
            "Is syntactically valid SQL",
        ],
    )

    verdict = build_pipeline().run_case(case)
    print(f"Outcome: {verdict.outcome.value}")
    print(f"Rationale: {verdict.rationale}")
    print(f"Model calls: {verdict.total_llm_calls}")
    for finding in verdict.findings:
        print(f"  [{finding.id}] {finding.source}: {finding.message}")


if __name__ == "__main__":
    main()
