"""规则注册表测试：加载、唯一性、正反样例即文档。"""
from app.detection.registry import RuleRegistry


def test_registry_loads_and_unique_ids():
    reg = RuleRegistry()
    reg.load()
    ids = [r.id for r in reg.rules]
    assert len(ids) >= 30
    assert len(ids) == len(set(ids)), "规则ID必须唯一"
    for rule in reg.rules:
        assert rule.tests.get("positives"), f"{rule.id} 缺少正例"
        assert rule.tests.get("negatives"), f"{rule.id} 缺少反例"


def test_registry_self_validation():
    reg = RuleRegistry()
    reg.load()
    problems = reg.validate_tests()
    assert problems == [], f"正反样例自检失败: {problems}"


def test_rule_types_distinct():
    reg = RuleRegistry()
    reg.load()
    types = {r.type for r in reg.rules}
    # 规则数多于类型数属正常（同类型拆分上下文规则），但类型数必须真实
    assert len(types) >= 25
