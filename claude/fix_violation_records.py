"""前置修复脚本：修复历史记录中 violation_type=NULL / confidence=NULL 的问题。

根因：旧版 _parse_response 把 resp.Label（字符串）当对象处理，导致
violation_type / violation_label / confidence 全部为 NULL。

修复策略（两轮）：
  第一轮：matched_by=ims_api  → 从 ims_result.raw_result 重新解析 Label/Score/SubLabel
  第二轮：matched_by=content/similar → 从来源记录（已在第一轮修好）复制 violation_type 等字段
"""

import json
import os
import sys

import mysql.connector
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

VIOLATION_TYPE_MAP = {
    'Porn': 'porn',
    'Gambling': 'gambling',
    'Violence': 'violence',
    'Politics': 'politics',
    'Ad': 'ads',
    'Ads': 'ads',
    'Terrorism': 'terrorism',
    'Terror': 'terrorism',
    'Contraband': 'contraband',
    'Illegal': 'contraband',
    'Vulgar': 'vulgar',
    'Abuse': 'vulgar',
    'Qrcode': 'qrcode',
    'Others': 'other',
    'Other': 'other',
    'Spam': 'other',
}


def connect():
    return mysql.connector.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        port=int(os.getenv('MYSQL_PORT', '3306')),
        user=os.getenv('MYSQL_USER', 'root'),
        password=os.getenv('MYSQL_PASSWORD'),
        database=os.getenv('MYSQL_DATABASE', 'image_security'),
        charset='utf8mb4',
        use_pure=True,
        autocommit=False,
    )


def fetch_all(conn, sql, params=()):
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def execute(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    cur.close()


def parse_from_raw(raw: dict) -> dict:
    """从 IMS 原始 JSON 重新提取 violation_type / label / description / confidence。"""
    label = raw.get('Label') or raw.get('label')
    score = raw.get('Score') if raw.get('Score') is not None else raw.get('score')
    sub_label = raw.get('SubLabel') or raw.get('subLabel') or raw.get('sub_label')

    violation_type = VIOLATION_TYPE_MAP.get(label, 'other') if label else None
    confidence = round(score / 100.0, 4) if score is not None else None

    return {
        'violation_type': violation_type,
        'violation_label': label,
        'violation_description': sub_label,
        'confidence': confidence,
    }


def fix_ims_api_records(conn) -> int:
    """第一轮：修复 matched_by=ims_api 的记录（有原始 raw_result 可重新解析）。"""
    rows = fetch_all(conn, """
        SELECT id, ims_result
        FROM image_scan_records
        WHERE is_violation = 1
          AND violation_type IS NULL
          AND ims_result IS NOT NULL
          AND JSON_UNQUOTE(JSON_EXTRACT(ims_result, '$.matched_by')) = 'ims_api'
    """)

    fixed = 0
    for row in rows:
        try:
            ims = row['ims_result']
            if isinstance(ims, str):
                ims = json.loads(ims)
            raw = ims.get('raw_result', {})
            if not raw:
                logger.warning(f"id={row['id']} raw_result 为空，跳过")
                continue

            parsed = parse_from_raw(raw)
            if not parsed['violation_type']:
                logger.warning(f"id={row['id']} Label 字段缺失，raw={raw}")
                continue

            execute(conn, """
                UPDATE image_scan_records
                SET violation_type = %s,
                    violation_label = %s,
                    violation_description = %s,
                    confidence = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (
                parsed['violation_type'],
                parsed['violation_label'],
                parsed['violation_description'],
                parsed['confidence'],
                row['id'],
            ))
            fixed += 1
        except Exception as e:
            logger.error(f"id={row['id']} 修复失败: {e}")

    return fixed


def fix_derived_records(conn) -> int:
    """第二轮：修复 matched_by=content/similar 的记录（从来源记录复制 violation 信息）。"""
    rows = fetch_all(conn, """
        SELECT id, ims_result
        FROM image_scan_records
        WHERE is_violation = 1
          AND violation_type IS NULL
          AND ims_result IS NOT NULL
          AND JSON_UNQUOTE(JSON_EXTRACT(ims_result, '$.matched_by')) IN ('content', 'similar')
    """)

    fixed = 0
    for row in rows:
        try:
            ims = row['ims_result']
            if isinstance(ims, str):
                ims = json.loads(ims)

            src_bucket = ims.get('source_bucket')
            src_key = ims.get('source_object_key')
            if not src_bucket or not src_key:
                logger.warning(f"id={row['id']} 来源信息缺失，跳过")
                continue

            sources = fetch_all(conn, """
                SELECT violation_type, violation_label, violation_description, confidence
                FROM image_scan_records
                WHERE bucket_name = %s AND object_key = %s
                  AND violation_type IS NOT NULL
                LIMIT 1
            """, (src_bucket, src_key))

            if not sources:
                logger.warning(f"id={row['id']} 来源记录未找到或仍为 NULL: "
                               f"{src_bucket}/{src_key}")
                continue

            src = sources[0]
            execute(conn, """
                UPDATE image_scan_records
                SET violation_type = %s,
                    violation_label = %s,
                    violation_description = %s,
                    confidence = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (
                src['violation_type'],
                src['violation_label'],
                src['violation_description'],
                src['confidence'],
                row['id'],
            ))
            fixed += 1
        except Exception as e:
            logger.error(f"id={row['id']} 修复失败: {e}")

    return fixed


def count_remaining(conn) -> int:
    rows = fetch_all(conn, """
        SELECT COUNT(*) AS c FROM image_scan_records
        WHERE is_violation = 1 AND violation_type IS NULL
    """)
    return rows[0]['c'] if rows else 0


def main():
    logger.info("=== 开始修复历史违规记录 ===")
    conn = connect()

    total_null = count_remaining(conn)
    logger.info(f"待修复记录数: {total_null}")
    if total_null == 0:
        logger.info("无需修复，退出")
        conn.close()
        return

    logger.info("第一轮：修复 ims_api 直接扫描记录...")
    n1 = fix_ims_api_records(conn)
    logger.info(f"  修复 {n1} 条")

    logger.info("第二轮：修复 content/similar 复用记录...")
    n2 = fix_derived_records(conn)
    logger.info(f"  修复 {n2} 条")

    remaining = count_remaining(conn)
    logger.info(f"=== 修复完成：共修复 {n1 + n2} 条，剩余无法修复 {remaining} 条 ===")
    if remaining:
        logger.warning(f"  {remaining} 条记录缺少 raw_result 或来源已丢失，需人工处理")

    conn.close()


if __name__ == '__main__':
    main()
