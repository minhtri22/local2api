from local2api.routing.router import RuleRouter


def test_short_request_defaults_local():
    decision = RuleRouter().decide({"messages": [{"role": "user", "content": "fix typo"}]})
    assert decision.backend == "local"


def test_architecture_routes_cloud_without_silent_fallback():
    decision = RuleRouter().decide(
        {"messages": [{"role": "user", "content": "review repository architecture"}]}
    )
    assert decision.backend == "cloud"
    assert decision.fallback_mode == "none"


def test_explicit_model_override():
    decision = RuleRouter().decide({"model": "cloud", "messages": []})
    assert decision.backend == "cloud"
    assert decision.reason == "explicit_model_override"
