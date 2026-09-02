from scripts.a1_memory_model import Q4_EFFECTIVE_BPW, build, kv_gib, weight_gib


def test_q4_weight_model_is_calibrated_to_hw1_effective_bpw():
    assert Q4_EFFECTIVE_BPW == 4.91
    assert round(weight_gib(14.0), 3) == 8.002
    assert round(weight_gib(32.0), 3) == 18.291
    assert round(weight_gib(70.0), 3) == 40.012


def test_kv_formula_scales_linearly_with_context():
    kv_4k = kv_gib(layers=48, kv_heads=8, head_dim=128, tokens=4096, bytes_per_element=2.0)
    kv_8k = kv_gib(layers=48, kv_heads=8, head_dim=128, tokens=8192, bytes_per_element=2.0)
    assert kv_4k == 0.75
    assert kv_8k == 1.5


def test_practical_budget_keeps_14b_and_32b_weights_but_not_70b():
    data = build()
    assert data["practical_model_runtime_budget_gib"] == 21.0
    assert data["models"]["14B_dense"]["fits_practical_budget_weights_only"] is True
    assert data["models"]["32B_dense"]["fits_practical_budget_weights_only"] is True
    assert data["models"]["70B_dense"]["fits_practical_budget_weights_only"] is False
