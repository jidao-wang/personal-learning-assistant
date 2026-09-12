import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.nodes import classify_task


def main() -> None:
    path = Path(__file__).with_name("golden_questions.jsonl")
    passed = 0
    total = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        total += 1
        knowledge_base_id = None if case["expected_task_type"] == "chat" else "kb-1"
        actual = classify_task(case["question"], knowledge_base_id)
        ok = actual == case["expected_task_type"]
        passed += int(ok)
        print(f"{case['id']}: {'PASS' if ok else 'FAIL'} actual={actual}")
    print(f"passed={passed}/{total}")
    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
