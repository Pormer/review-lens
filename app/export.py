def markdown_report(report: dict) -> str:
    def clean(value):
        # Export user/model data as text, never active HTML or extra Markdown structure.
        value = str(value).replace("\n", " ").replace("\r", " ")
        for char in ("\\", "`", "*", "_", "[", "]", "<", ">", "#", "!"):
            value = value.replace(char, "\\" + char)
        return value

    n, m = report["narrative"], report["metrics"]
    lines = [f"# {clean(report['product_name'])} · 리뷰렌즈", "",
             f"분석 모드: {'가상 예제' if report['mode'] == 'demo' else '공개 웹 근거 분석'}", "",
             clean(n["headline"]), "", clean(n["summary"]), "",
             f"분석 근거 {m['evidence_count']}건 · 개별 리뷰 {m['review_count']}건 · 출처 {m['source_count']}개", "",
             "## 별점과 본문", "", f"비교 가능한 리뷰: {m['paired_count']}건", "",
             f"표본 평균 별점: {m['average_rating'] if m['average_rating'] is not None else '산출 불가'}", "",
             f"본문 감성 환산: {m['average_text_score'] if m['average_text_score'] is not None else '산출 불가'}", "",
             f"괴리 표시 리뷰: {m['flagged_count']}건", "", m["method"], ""]
    for field, label in (("pros", "장점"), ("cons", "단점"), ("usage", "사용 경험")):
        lines += [f"## {label}", ""]
        for item in n[field]:
            lines += [f"- **{clean(item['title'])}**: {clean(item['detail'])} ({', '.join(clean(x) for x in item['evidence_ids'])})"]
        if not n[field]:
            lines += ["근거 부족으로 판단을 보류했습니다."]
        lines += [""]
    for field, label in (("suitable_for", "이런 분께 적합해요"), ("consider_before_buying", "구매 전 확인")):
        lines += [f"## {label}", ""] + [f"- {clean(x)}" for x in n[field]] + [""]
    lines += ["## 분석의 한계", ""] + [f"- {clean(x)}" for x in report["limitations"]] + ["", "## 근거", ""]
    passage_label = "수집 자료 발췌" if report.get("provider") == "ollama" or report.get("evidence_origin") == "collected" else "연구 메모 발췌"
    for item in report["evidence"]:
        lines += [f"- {clean(item['id'])} / {clean(item['source_id'])}: {clean(item['summary'])}",
                  f"  {passage_label}: {clean(item['passage'])}"]
    lines += ["", "## 출처", ""]
    for source in report["sources"]:
        lines += [f"- {clean(source['id'])}: {clean(source['title'])} — {clean(source['url'])}"]
    return "\n".join(lines) + "\n"
