import pytest
from app.models import ArsenalRecord, TargetRecord
from app.rag import GeminiRAG, narrative
from app.synthetic import generate_synthetic_data


def test_narrative_omits_target_identity():
    target = TargetRecord(id="t", age=30, zip_code="1", occupation="teacher", gender="woman")
    assert "Name:" not in narrative(target)


def test_narrative_includes_arsenal_identity():
    record = ArsenalRecord(id="a", name="Synthetic Person", age=30, zip_code="1", occupation="teacher", gender="woman")
    assert "Name: Synthetic Person" in narrative(record)


def test_uniqueness_discount_penalizes_ties():
    tied = [{"similarity": .8}, {"similarity": .8}]
    distinct = [{"similarity": .95}, {"similarity": .7}]
    assert GeminiRAG._uniqueness_discount(tied) == 0
    assert GeminiRAG._uniqueness_discount(distinct) == 1


def test_tiers_are_bounded():
    assert GeminiRAG._tier(.8) == "Critical"
    assert GeminiRAG._tier(.1) == "Low"


def test_assessment_parser_accepts_fenced_json():
    result = GeminiRAG._parse_assessment('```json\n{"predicted_identity":"Asha Raman","confidence":0.8,"evidence":["ZIP match"],"rationale":"Rare combination."}\n```')
    assert result.predicted_identity == "Asha Raman"
    assert result.confidence == .8


def test_local_embeddings_ignore_arsenal_name():
    arsenal = "Name: Asha Raman. Profile: 34-year-old woman; occupation: teacher; ZIP code: 560001; medical flag: asthma."
    target = "Profile: 34-year-old woman; occupation: teacher; ZIP code: 560001; medical flag: asthma."
    assert GeminiRAG._local_embeddings([arsenal])[0] == GeminiRAG._local_embeddings([target])[0]


def test_synthetic_generator_creates_known_fraction_of_links():
    data = generate_synthetic_data(record_count=10, planted_match_rate=.4, seed=7)
    assert len(data["arsenal_records"]) == len(data["target_records"]) == 10
    assert sum(value is not None for value in data["ground_truth"].values()) == 4


def test_gemini_requests_and_usage(tmp_path):
    import httpx
    from openai import OpenAI
    from app.config import Settings
    from app.demo import TARGETS

    requests = []
    def handler(request):
        import json
        body = json.loads(request.content)
        requests.append(body)
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.headers["authorization"] == "Bearer test-key"
        assert "extra_body" not in body
        assert "chat_template_kwargs" not in body
        if request.url.path.endswith("/embeddings"):
            assert body["model"] == "gemini-embedding-001"
            assert body["encoding_format"] == "float"
            assert "input_type" not in body and "truncate" not in body
            return httpx.Response(200, json={"data": [{"index": 1, "embedding": [0., 1.]}, {"index": 0, "embedding": [1., 0.]}]})
        assert body["model"] == "gemini-3.5-flash-lite"
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"predicted_identity":"NO_MATCH","confidence":0,"evidence":[],"rationale":"No candidates."}'}}], "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}})

    settings = Settings(_env_file=None, gemini_api_key="test-key", chroma_path=tmp_path)
    rag = GeminiRAG(settings)
    rag.llm.close()
    rag.llm = OpenAI(api_key=settings.gemini_api_key, base_url=settings.gemini_base_url, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert rag._embed(["first", "second"], "passage") == [[1., 0.], [0., 1.]]
    assessment, tokens, raw, mode = rag._assess(TARGETS[0], [])
    assert tokens == 20 and mode == "gemini"
    assert assessment.predicted_identity == "NO_MATCH"
    assert len(requests) == 2
    rag.llm.close()


def test_missing_key_and_isolated_indexes(tmp_path):
    import pytest
    from app.config import Settings
    from app.demo import ARSENAL, TARGETS

    cloud = GeminiRAG(Settings(_env_file=None, gemini_api_key="", chroma_path=tmp_path))
    with pytest.raises(ValueError, match="GEMINI_API_KEY is missing"):
        cloud._embed(["test"], "query")
    local = GeminiRAG(Settings(_env_file=None, gemini_api_key="", rag_mode="local", chroma_path=tmp_path))
    assert cloud.collection_name != local.collection_name
    assert local.index(ARSENAL) == len(ARSENAL)
    assert local.retrieve(TARGETS[0], 2)
    assert local.index(ARSENAL) == len(ARSENAL)
    assert cloud._collection().count() == 0
    cloud.llm.close()
    local.llm.close()


@pytest.mark.parametrize("data, expected", [
    ([{"embedding": [1., 0.]}, {"index": 1, "embedding": [0., 1.]}], [[1., 0.], [0., 1.]]),
    ([{"index": None, "embedding": [1., 0.]}, {"index": 1, "embedding": [0., 1.]}], [[1., 0.], [0., 1.]]),
    ([{"embedding": [1., 0.]}, {"embedding": [0., 1.]}], [[1., 0.], [0., 1.]]),
    ([{"index": 1, "embedding": [0., 1.]}, {"index": 0, "embedding": [1., 0.]}], [[1., 0.], [0., 1.]]),
    ([{"index": 0, "embedding": [1., 0.]}], None),
    ([{"index": 1, "embedding": [1., 0.]}, {"embedding": [0., 1.]}], None),
])
def test_embedding_response_indexes(data, expected):
    import httpx
    from openai import OpenAI
    from app.config import Settings

    # Exercise the actual SDK decoding, including absent and null index fields.
    rag = GeminiRAG.__new__(GeminiRAG)
    rag.settings = Settings(_env_file=None, gemini_api_key="test-key")
    rag.mode = "gemini"
    with OpenAI(api_key="test-key", base_url=rag.settings.gemini_base_url,
                http_client=httpx.Client(transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"data": data})))) as client:
        rag.llm = client
        if expected is None:
            with pytest.raises(ValueError, match="Gemini returned"):
                rag._embed(["first", "second"], "passage")
        else:
            assert rag._embed(["first", "second"], "passage") == expected
