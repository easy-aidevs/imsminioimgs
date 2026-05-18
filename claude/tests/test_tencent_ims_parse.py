"""tencent_ims._parse_response 测试：覆盖审计 bug #1（confidence 归一化）。"""

import json
from types import SimpleNamespace

from tencent_ims import TencentIMSScanner


def _make_scanner():
    """绕过 SDK 网络初始化，直接构造一个能用 _parse_response 的实例。"""
    scanner = TencentIMSScanner.__new__(TencentIMSScanner)
    return scanner


def _mock_resp(suggestion="Block", label="Gambling",
               sub_label="Casino", confidence=95.0, description="赌博场景"):
    """构造一个仿真的 IMS 响应对象。"""
    sub = SimpleNamespace(Label=sub_label, Description=description,
                          Confidence=confidence)
    label_obj = SimpleNamespace(Label=label, SubLabels=[sub])
    resp = SimpleNamespace(
        RequestId="req-test-123",
        Suggestion=suggestion,
        Label=label_obj,
        to_json_string=lambda: json.dumps({
            "RequestId": "req-test-123",
            "Suggestion": suggestion,
            "Label": {"Label": label, "SubLabels": [
                {"Label": sub_label, "Description": description,
                 "Confidence": confidence}
            ]},
        }),
    )
    return resp


class TestConfidenceNormalization:
    """审计 bug #1 的回归测试：腾讯云返回 0-100，DB 列 DECIMAL(5,4) 只能存 0-1。"""

    def test_confidence_95_normalized_to_0_95(self):
        result = _make_scanner()._parse_response(_mock_resp(confidence=95.0))
        assert result['confidence'] == 0.95

    def test_confidence_100_normalized_to_1(self):
        result = _make_scanner()._parse_response(_mock_resp(confidence=100.0))
        assert result['confidence'] == 1.0

    def test_confidence_0_stays_0(self):
        result = _make_scanner()._parse_response(_mock_resp(confidence=0.0))
        assert result['confidence'] == 0.0

    def test_confidence_already_0_to_1_kept(self):
        """防御性：如果 SDK 行为变了返回 0-1，不应该再除以 100。"""
        result = _make_scanner()._parse_response(_mock_resp(confidence=0.87))
        assert result['confidence'] == 0.87

    def test_confidence_fits_decimal_5_4(self):
        """所有可能的输入归一化后都必须 <= 1.0，能存入 DECIMAL(5,4)。"""
        for raw in [0.0, 0.5, 1.0, 50.0, 99.99, 100.0]:
            result = _make_scanner()._parse_response(_mock_resp(confidence=raw))
            assert 0 <= result['confidence'] <= 1.0, f"raw={raw} 归一化失败"


class TestSuggestionMapping:
    def test_block_means_violation(self):
        result = _make_scanner()._parse_response(_mock_resp(suggestion="Block"))
        assert result['is_violation'] is True
        assert result['suggestion'] == "Block"

    def test_review_means_violation(self):
        result = _make_scanner()._parse_response(_mock_resp(suggestion="Review"))
        assert result['is_violation'] is True

    def test_pass_means_clean(self):
        result = _make_scanner()._parse_response(_mock_resp(suggestion="Pass"))
        assert result['is_violation'] is False


class TestViolationTypeMapping:
    def test_gambling_label_maps_to_lowercase(self):
        result = _make_scanner()._parse_response(_mock_resp(label="Gambling"))
        assert result['violation_type'] == 'gambling'

    def test_unknown_label_falls_back_to_other(self):
        result = _make_scanner()._parse_response(_mock_resp(label="WeirdNewType"))
        assert result['violation_type'] == 'other'
