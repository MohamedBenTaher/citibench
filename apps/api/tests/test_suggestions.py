from suggestions import parse_questions


def test_parse_questions_plain_json() -> None:
    content = '{"questions": ["What is a Pod?", "Compare Service and Ingress"]}'
    assert parse_questions(content, 5) == [
        "What is a Pod?",
        "Compare Service and Ingress?",
    ]


def test_parse_questions_code_fence() -> None:
    content = '```json\n{"questions": ["How does scheduling work?"]}\n```'
    assert parse_questions(content, 5) == ["How does scheduling work?"]


def test_parse_questions_invalid_and_empty() -> None:
    assert parse_questions("not json", 5) == []
    assert parse_questions('{"questions": []}', 5) == []
    assert parse_questions('{"other": ["x"]}', 5) == []


def test_parse_questions_normalizes_trailing_period() -> None:
    content = '{"questions": ["Describe the role of the Cloud Controller Manager."]}'
    assert parse_questions(content, 5) == [
        "Describe the role of the Cloud Controller Manager?"
    ]


def test_parse_questions_dedupes_and_limits() -> None:
    content = '{"questions": ["What is alpha?", "What is alpha?", "What is beta?", "What is gamma?"]}'
    assert parse_questions(content, 2) == ["What is alpha?", "What is beta?"]
