#!/usr/bin/env python3
"""
generate_adr.py

ADR(Architecture Decision Record) 파일을 자동으로 생성하는 스크립트.
다음 번호를 자동 계산하고 템플릿으로 파일을 만든다.

사용법:
    python scripts/generate_adr.py "Python 버전 결정"
    python scripts/generate_adr.py "Knowledge Graph 라이브러리 선택" --status "Draft"
"""

import re
import sys
from datetime import date
from pathlib import Path

ADR_DIR = Path(__file__).parent.parent / "docs" / "adr"


def get_next_adr_number() -> int:
    """현재 ADR 디렉토리에서 다음 번호를 계산한다."""
    ADR_DIR.mkdir(parents=True, exist_ok=True)
    existing = list(ADR_DIR.glob("ADR-*.md"))
    if not existing:
        return 1
    numbers = []
    for f in existing:
        match = re.match(r"ADR-(\d+)", f.name)
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers) + 1 if numbers else 1


def slugify(title: str) -> str:
    """제목을 파일명용 slug로 변환한다."""
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def generate_template(number: int, title: str, status: str = "Draft") -> str:
    """ADR 마크다운 템플릿을 생성한다."""
    today = date.today().strftime("%Y-%m-%d")
    return f"""# ADR-{number:03d}: {title}

- **상태**: {status}
- **날짜**: {today}
- **작성자**: AI Research Lab

---

## 컨텍스트

<!-- 왜 이 결정이 필요한가? 어떤 상황/문제에서 비롯되었는가? -->

## 결정

<!-- 무엇을 하기로 했는가? -->

## 근거

<!-- 왜 이 결정을 했는가? 다른 대안은 무엇이었고, 왜 선택하지 않았는가? -->

### 고려한 대안들

| 대안 | 장점 | 단점 | 선택 여부 |
|------|------|------|-----------|
| (대안 1) | | | ❌ |
| (현재 결정) | | | ✅ |

## 결과

<!-- 이 결정으로 인해 어떤 영향이 생기는가? 트레이드오프는? -->

### 긍정적 결과

-

### 부정적 결과 / 트레이드오프

-

## 관련 ADR

<!-- 관련된 다른 ADR 링크 -->
-

---

*마지막 업데이트: {today}*
"""


def main():
    import argparse

    parser = argparse.ArgumentParser(description="ADR 파일 자동 생성")
    parser.add_argument("title", help="ADR 제목 (예: 'Knowledge Graph 라이브러리 선택')")
    parser.add_argument(
        "--status",
        default="Draft",
        choices=["Draft", "Accepted", "Deprecated", "Superseded"],
        help="ADR 상태 (기본값: Draft)",
    )
    args = parser.parse_args()

    number = get_next_adr_number()
    slug = slugify(args.title)
    filename = f"ADR-{number:03d}-{slug}.md"
    filepath = ADR_DIR / filename

    if filepath.exists():
        print(f"❌ 이미 존재하는 파일: {filepath}")
        sys.exit(1)

    content = generate_template(number, args.title, args.status)
    filepath.write_text(content, encoding="utf-8")

    print(f"✅ ADR 생성 완료!")
    print(f"   파일: docs/adr/{filename}")
    print(f"   번호: ADR-{number:03d}")
    print(f"   상태: {args.status}")
    print(f"\n   👉 다음: {filepath} 파일을 열어서 내용을 채우세요.")


if __name__ == "__main__":
    main()
