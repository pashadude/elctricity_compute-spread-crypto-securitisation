#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "docs" / "submission" / "final_submission.json"


def main() -> int:
    data = json.loads(PACKET.read_text())
    print(f"Project: {data['project']}")
    print(f"Demo: {data['demo_url']}")
    print(f"Repo: {data['repository_url']}")
    print(f"Arc OSS starter kit: {data['arc_oss_starter_kit_url']}")
    print(f"Video: {data['video_url']}")
    print()
    print("What problem is your project solving?")
    print(data["problem"])
    print()
    print("Why is it compelling?")
    print(data["why_compelling"])
    print()
    print("Arc OSS answer:")
    print(data["arc_oss_answer"])
    print()
    print("Circle / Arc feedback - worked:")
    for item in data["circle_arc_feedback"]["worked"]:
        print(f"- {item}")
    print()
    print("Circle / Arc feedback - improve:")
    for item in data["circle_arc_feedback"]["improve"]:
        print(f"- {item}")
    print()
    print("Arc CLI update:")
    print((ROOT / data["arc_cli_update_file"]).read_text().strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
