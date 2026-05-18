"""image_feature.py 纯函数测试：Key 确定性、汉明距离、相似判定。"""

import io
from PIL import Image

from image_feature import ImageFeatureExtractor


def _make_png(color=(255, 0, 0), size=(32, 32)) -> bytes:
    """生成一张纯色 PNG 的字节。"""
    img = Image.new('RGB', size, color)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


class TestCalculateKey:
    def test_key_is_deterministic(self):
        """同样的字节必须算出同样的 Key。"""
        extractor = ImageFeatureExtractor()
        data = _make_png()
        assert extractor.calculate_key(data) == extractor.calculate_key(data)

    def test_key_format_md5_dash_size(self):
        """Key 格式必须是 md5-size。"""
        extractor = ImageFeatureExtractor()
        data = b"hello"
        key = extractor.calculate_key(data)
        # md5("hello") = 5d41402abc4b2a76b9719d911017c592
        assert key == "5d41402abc4b2a76b9719d911017c592-5"

    def test_different_content_different_key(self):
        extractor = ImageFeatureExtractor()
        assert extractor.calculate_key(b"a") != extractor.calculate_key(b"b")


class TestExtractFeatures:
    def test_returns_phash_dhash_ahash(self):
        extractor = ImageFeatureExtractor()
        feats = extractor.extract_features(_make_png())
        assert 'phash' in feats and 'dhash' in feats and 'ahash' in feats
        assert all(isinstance(v, str) and v for v in
                   (feats['phash'], feats['dhash'], feats['ahash']))

    def test_same_image_same_features(self):
        """同一张图片，特征值必须可复现。"""
        extractor = ImageFeatureExtractor()
        data = _make_png()
        f1 = extractor.extract_features(data)
        f2 = extractor.extract_features(data)
        assert f1['phash'] == f2['phash']


class TestHashDistance:
    def test_identical_hash_distance_zero(self):
        h = "ffffffffffffffff"
        assert ImageFeatureExtractor.calculate_hash_distance(h, h) == 0

    def test_known_distance(self):
        # 0x00 vs 0xff = 8 bits 不同
        assert ImageFeatureExtractor.calculate_hash_distance("00", "ff") == 8

    def test_empty_string_returns_negative(self):
        """空字符串无法解析为 16 进制，应返回 -1（在 except 分支）。"""
        assert ImageFeatureExtractor.calculate_hash_distance("", "ff") == -1
        assert ImageFeatureExtractor.calculate_hash_distance("ff", "") == -1

    def test_is_similar_with_negative_distance_returns_false(self):
        """异常情况返回 -1，is_similar 不能误判为相似。"""
        assert ImageFeatureExtractor.is_similar("", "ff", threshold=5) is False
