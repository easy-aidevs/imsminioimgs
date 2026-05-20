"""tencent_ims._parse_response 测试：覆盖审计 bug #1（confidence 归一化）。"""

import json
from types import SimpleNamespace

import pytest

from tencent_ims import TencentIMSScanner


def _make_scanner():
    """绕过 SDK 网络初始化，直接构造一个能用 _parse_response 的实例。"""
    scanner = TencentIMSScanner.__new__(TencentIMSScanner)
    return scanner


def _mock_resp(suggestion="Block", label="Illegal", sub_label="Gambling", confidence=95):
    """构造仿真 IMS 响应：Label/SubLabel 是纯字符串，Score 是 0-100 整数。"""
    resp = SimpleNamespace(
        RequestId="req-test-123",
        Suggestion=suggestion,
        Label=label,
        SubLabel=sub_label,
        Score=confidence,
        to_json_string=lambda: json.dumps({
            "RequestId": "req-test-123",
            "Suggestion": suggestion,
            "Label": label,
            "SubLabel": sub_label,
            "Score": confidence,
        }),
    )
    return resp


class TestConfidenceNormalization:
    """审计 bug #1 的回归测试：腾讯云返回 0-100，DB 列 DECIMAL(5,4) 只能存 0-1。"""

    def test_confidence_95_normalized_to_0_95(self):
        result = _make_scanner()._parse_response(_mock_resp(confidence=95))
        assert result['confidence'] == 0.95

    def test_confidence_100_normalized_to_1(self):
        result = _make_scanner()._parse_response(_mock_resp(confidence=100))
        assert result['confidence'] == 1.0

    def test_confidence_0_stays_0(self):
        result = _make_scanner()._parse_response(_mock_resp(confidence=0))
        assert result['confidence'] == 0.0

    def test_confidence_low_score_in_range(self):
        """Score=1 (极低置信度) 归一化后为 0.01，仍在 [0,1] 内。"""
        result = _make_scanner()._parse_response(_mock_resp(confidence=1))
        assert 0 <= result['confidence'] <= 1.0

    def test_confidence_fits_decimal_5_4(self):
        """所有可能的输入归一化后都必须 <= 1.0，能存入 DECIMAL(5,4)。"""
        for raw in [0, 1, 50, 99, 100]:
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
    def test_sub_label_used_as_violation_type(self):
        """有 SubLabel 时，violation_type = SubLabel（原始 IMS 值，保持大小写）。"""
        result = _make_scanner()._parse_response(
            _mock_resp(label="Illegal", sub_label="Gambling")
        )
        assert result['violation_type'] == 'Gambling'
        assert result['violation_label'] == 'Illegal'
        assert result['sub_label'] == 'Gambling'

    def test_label_fallback_when_no_sub_label(self):
        """无 SubLabel 时，violation_type = Label（原始 IMS 值）。"""
        result = _make_scanner()._parse_response(
            _mock_resp(label="Porn", sub_label="")
        )
        assert result['violation_type'] == 'Porn'
        assert result['violation_label'] == 'Porn'
        assert result['sub_label'] is None
