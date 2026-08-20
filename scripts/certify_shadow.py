from __future__ import annotations

import argparse
import os
from pathlib import Path

from clement_omniroute.certifier import certify_endpoints, to_json, write_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lm-studio", default=os.getenv("CLEMENT_LM_STUDIO_URL", "http://127.0.0.1:1234"))
    parser.add_argument("--omniroute", default=os.getenv("CLEMENT_OMNIROUTE_URL", "http://127.0.0.1:20128"))
    parser.add_argument("--openrouter", default=os.getenv("CLEMENT_OPENROUTER_URL", "https://openrouter.ai/api"))
    parser.add_argument("--report", default="OMNIROUTE_CERTIFICATION.md")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    result = certify_endpoints(
        lm_studio_url=args.lm_studio,
        omniroute_url=args.omniroute,
        openrouter_url=args.openrouter,
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        timeout=args.timeout,
    )
    report = write_report(result, Path(args.report))
    print(to_json(result))
    print(f"REPORT={report.resolve()}")
    print(f"RESULT={result.verdict}")
    return 0 if result.verdict in {"PASS", "PARTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
