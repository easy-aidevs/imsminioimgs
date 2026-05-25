#!/usr/bin/env python3
"""违规图片处置工具：两阶段处理（直接隔离 -> 删除 / 恢复）。

机制：
- quarantine:  原桶 -> 隔离桶（MinIO 层物理移动，原 URL 立即失效）
- restore:     隔离桶 -> 原桶（误判恢复，标记为非违规）
- delete:      隔离桶 -> 彻底删除（不可恢复）

数据库 `blocked` 字段：
  0 = unhandled  （未处理，在原桶）
  2 = quarantined（已隔离，在隔离桶）

注：旧版本遗留的 blocked=1（私密观察期）记录仍在原桶，
    `list` 命令会一并显示，可直接用 `quarantine` 或标注后忽略。
"""

import argparse
import os
from datetime import datetime
from typing import Dict, Generator, List, Optional

from dotenv import load_dotenv

from logger_config import setup_logger
from database import ImageDatabase
from minio_client import MinIOClient

load_dotenv()
logger = setup_logger(log_dir="logs")

BATCH_SIZE = 1000       # 每批从 DB 读取的记录数
DISPLAY_LIMIT = 200     # list 命令最多显示条数


def _quarantine_key(original_bucket: str, original_key: str) -> str:
    """隔离桶内的对象路径：保留原 bucket 前缀，方便定位和恢复。"""
    return f"{original_bucket}/{original_key}"


class ViolationHandler:
    """违规图片处置：基于隔离桶迁移。"""

    def __init__(self):
        self.db = ImageDatabase(
            host=os.getenv('MYSQL_HOST', 'localhost'),
            port=int(os.getenv('MYSQL_PORT', '3306')),
            user=os.getenv('MYSQL_USER', 'root'),
            password=os.getenv('MYSQL_PASSWORD'),
            database=os.getenv('MYSQL_DATABASE', 'image_security'),
        )
        self.minio = MinIOClient(
            endpoint=os.getenv('MINIO_ENDPOINT', 'localhost:9000'),
            access_key=os.getenv('MINIO_ACCESS_KEY'),
            secret_key=os.getenv('MINIO_SECRET_KEY'),
            secure=os.getenv('MINIO_SECURE', 'false').lower() == 'true',
        )
        self.quarantine_bucket = os.getenv('QUARANTINE_BUCKET_NAME', 'quarantine')
        self.minio.ensure_bucket(self.quarantine_bucket)

    # ------------------------------------------------------------------ 查询（展示用）

    def list_violations(self, violation_type: str = None,
                        sub_label: str = None,
                        violation_label: str = None,
                        confidence: float = 0.0,
                        suggestion: str = None,
                        ids: List[int] = None,
                        prefix: str = None,
                        bucket: str = None,
                        limit: int = None) -> List[Dict]:
        """列出原桶中的违规图片（blocked=0 或旧版 blocked=1，均在原桶未被隔离）。

        limit: 最多返回条数，None 表示不限（慎用于大数据集，改用 _iter_violations 流式处理）。
        """
        query = """
            SELECT id, bucket_name, object_key, violation_type,
                   violation_label, violation_label_cn, sub_label,
                   sub_label_cn, confidence, suggestion, blocked
            FROM image_scan_records
            WHERE is_violation = 1 AND blocked IN (0, 1)
        """
        params = []
        if ids:
            placeholders = ','.join(['%s'] * len(ids))
            query += f" AND id IN ({placeholders})"
            params.extend(ids)
        if violation_type:
            query += " AND violation_type = %s"
            params.append(violation_type)
        if sub_label:
            query += " AND sub_label = %s"
            params.append(sub_label)
        if violation_label:
            query += " AND violation_label = %s"
            params.append(violation_label)
        if suggestion:
            query += " AND suggestion = %s"
            params.append(suggestion)
        if confidence > 0:
            query += " AND confidence >= %s"
            params.append(confidence)
        if prefix:
            query += " AND object_key LIKE %s"
            params.append(prefix + '%')
        if bucket:
            query += " AND bucket_name = %s"
            params.append(bucket)
        query += " ORDER BY violation_label, sub_label, confidence DESC"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        return self.db.execute_query(query, tuple(params) if params else None, fetch=True)

    def count_violations(self, violation_type: str = None,
                         sub_label: str = None,
                         violation_label: str = None,
                         confidence: float = 0.0,
                         suggestion: str = None,
                         ids: List[int] = None,
                         prefix: str = None,
                         bucket: str = None) -> int:
        """返回符合条件的违规记录总数。"""
        query = """
            SELECT COUNT(*) AS c FROM image_scan_records
            WHERE is_violation = 1 AND blocked IN (0, 1)
        """
        params = []
        if ids:
            placeholders = ','.join(['%s'] * len(ids))
            query += f" AND id IN ({placeholders})"
            params.extend(ids)
        if violation_type:
            query += " AND violation_type = %s"
            params.append(violation_type)
        if sub_label:
            query += " AND sub_label = %s"
            params.append(sub_label)
        if violation_label:
            query += " AND violation_label = %s"
            params.append(violation_label)
        if suggestion:
            query += " AND suggestion = %s"
            params.append(suggestion)
        if confidence > 0:
            query += " AND confidence >= %s"
            params.append(confidence)
        if prefix:
            query += " AND object_key LIKE %s"
            params.append(prefix + '%')
        if bucket:
            query += " AND bucket_name = %s"
            params.append(bucket)
        result = self.db.execute_query(query, tuple(params) if params else None, fetch=True)
        return result[0]['c'] if result else 0

    def list_quarantined(self, ids: List[int] = None, batch_id: str = None,
                         limit: int = None) -> List[Dict]:
        """已被隔离（迁移到隔离桶）的记录。blocked=2"""
        conditions = ["blocked = 2"]
        params: list = []

        if ids:
            placeholders = ','.join(['%s'] * len(ids))
            conditions.append(f"id IN ({placeholders})")
            params.extend(ids)
        if batch_id:
            conditions.append("quarantine_batch_id = %s")
            params.append(batch_id)

        where = " AND ".join(conditions)
        query = f"""
            SELECT id, bucket_name, object_key, violation_type,
                   violation_label_cn, sub_label_cn, confidence, suggestion, blocked,
                   quarantine_batch_id
            FROM image_scan_records
            WHERE {where}
            ORDER BY updated_at DESC
        """
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        return self.db.execute_query(query, tuple(params) if params else None, fetch=True)

    def count_quarantined(self, ids: List[int] = None, batch_id: str = None) -> int:
        """返回已隔离记录总数。"""
        conditions = ["blocked = 2"]
        params: list = []
        if ids:
            placeholders = ','.join(['%s'] * len(ids))
            conditions.append(f"id IN ({placeholders})")
            params.extend(ids)
        if batch_id:
            conditions.append("quarantine_batch_id = %s")
            params.append(batch_id)
        where = " AND ".join(conditions)
        result = self.db.execute_query(
            f"SELECT COUNT(*) AS c FROM image_scan_records WHERE {where}",
            tuple(params) if params else None, fetch=True,
        )
        return result[0]['c'] if result else 0

    # ------------------------------------------------------------------ 流式生成器（大批量操作用）

    def _fetch_violations_page(self, after_id: int,
                               violation_type: str = None, sub_label: str = None,
                               violation_label: str = None, confidence: float = 0.0,
                               suggestion: str = None, prefix: str = None,
                               bucket: str = None) -> List[Dict]:
        """用游标方式取一页违规记录（id > after_id），供流式迭代使用。"""
        query = """
            SELECT id, bucket_name, object_key, violation_type,
                   violation_label, violation_label_cn, sub_label,
                   sub_label_cn, confidence, suggestion, blocked
            FROM image_scan_records
            WHERE is_violation = 1 AND blocked IN (0, 1) AND id > %s
        """
        params: list = [after_id]
        if violation_type:
            query += " AND violation_type = %s"
            params.append(violation_type)
        if sub_label:
            query += " AND sub_label = %s"
            params.append(sub_label)
        if violation_label:
            query += " AND violation_label = %s"
            params.append(violation_label)
        if suggestion:
            query += " AND suggestion = %s"
            params.append(suggestion)
        if confidence > 0:
            query += " AND confidence >= %s"
            params.append(confidence)
        if prefix:
            query += " AND object_key LIKE %s"
            params.append(prefix + '%')
        if bucket:
            query += " AND bucket_name = %s"
            params.append(bucket)
        query += " ORDER BY id ASC LIMIT %s"
        params.append(BATCH_SIZE)
        return self.db.execute_query(query, tuple(params), fetch=True)

    def _iter_violations(self, violation_type: str = None, sub_label: str = None,
                         violation_label: str = None, confidence: float = 0.0,
                         suggestion: str = None,
                         ids: List[int] = None,
                         prefix: str = None,
                         bucket: str = None) -> Generator[Dict, None, None]:
        """流式生成违规记录，每批 BATCH_SIZE 条，不将全量加载到内存。

        ids 指定时（有限集合）直接一次性加载；过滤条件查询时使用游标分页。
        已处理记录的 blocked 状态改变，不会再出现在后续批次中。
        """
        if ids:
            yield from self.list_violations(violation_type, sub_label, violation_label,
                                            confidence, suggestion, ids, prefix=prefix,
                                            bucket=bucket)
            return
        after_id = 0
        while True:
            batch = self._fetch_violations_page(after_id, violation_type, sub_label,
                                                violation_label, confidence, suggestion,
                                                prefix=prefix, bucket=bucket)
            if not batch:
                break
            yield from batch
            after_id = batch[-1]['id']

    def _fetch_quarantined_page(self, after_id: int,
                                batch_id: str = None) -> List[Dict]:
        """用游标方式取一页已隔离记录（id > after_id）。"""
        conditions = ["blocked = 2", "id > %s"]
        params: list = [after_id]
        if batch_id:
            conditions.append("quarantine_batch_id = %s")
            params.append(batch_id)
        where = " AND ".join(conditions)
        query = f"""
            SELECT id, bucket_name, object_key, violation_type,
                   violation_label_cn, sub_label_cn, confidence, suggestion, blocked,
                   quarantine_batch_id
            FROM image_scan_records
            WHERE {where}
            ORDER BY id ASC LIMIT %s
        """
        params.append(BATCH_SIZE)
        return self.db.execute_query(query, tuple(params), fetch=True)

    def _iter_quarantined(self, ids: List[int] = None,
                          batch_id: str = None) -> Generator[Dict, None, None]:
        """流式生成已隔离记录，每批 BATCH_SIZE 条。"""
        if ids:
            yield from self.list_quarantined(ids=ids, batch_id=batch_id)
            return
        after_id = 0
        while True:
            batch = self._fetch_quarantined_page(after_id, batch_id=batch_id)
            if not batch:
                break
            yield from batch
            after_id = batch[-1]['id']

    # ------------------------------------------------------------------ 操作

    def quarantine(self, records, dry_run: bool = False,
                   batch_id: str = None, total: Optional[int] = None) -> Dict:
        """将违规图片从原桶移入隔离桶（MinIO 层物理隔离，原 URL 立即失效）。

        records 可以是 List[Dict] 或生成器（大批量时用 _iter_violations 流式传入）。
        batch_id 由调用方传入（手动指定）或留空（自动生成时间戳）。
        """
        if batch_id is None:
            batch_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        stats = {'success': 0, 'failed': 0, 'skipped': 0, 'batch_id': batch_id, 'failed_ids': []}
        total_str = f"/{total}" if total else ""

        for i, r in enumerate(records, 1):
            src_bucket = r['bucket_name']
            src_key = r['object_key']
            dst_key = _quarantine_key(src_bucket, src_key)

            if dry_run:
                logger.info(f"[{i}{total_str}] DRY-RUN quarantine: "
                            f"{src_bucket}/{src_key} -> {self.quarantine_bucket}/{dst_key}")
                stats['success'] += 1
                continue

            try:
                if not self.minio.object_exists(src_bucket, src_key):
                    logger.warning(f"[{i}{total_str}] 源对象不存在，仅标记: "
                                   f"{src_bucket}/{src_key}")
                    self._mark_quarantined(r['id'], batch_id)
                    stats['skipped'] += 1
                    continue

                self.minio.move_object(src_bucket, src_key, self.quarantine_bucket, dst_key)
                try:
                    self.minio.set_violation_tag(self.quarantine_bucket, dst_key,
                                                 violation_type=r.get('violation_type'))
                except Exception as tag_err:
                    logger.warning(f"  标签写入失败（不影响隔离）: {tag_err}")

                self._mark_quarantined(r['id'], batch_id)
                stats['success'] += 1
                logger.info(f"[{i}{total_str}] quarantine 成功: {src_bucket}/{src_key}")
            except Exception as e:
                stats['failed'] += 1
                stats['failed_ids'].append(r['id'])
                logger.error(f"[{i}{total_str}] quarantine 失败 {src_bucket}/{src_key}: {e}")

            if i % BATCH_SIZE == 0:
                logger.info(f"进度: 已处理 {i}{total_str} 条 | "
                            f"成功={stats['success']} 跳过={stats['skipped']} 失败={stats['failed']}")

        return stats

    def restore(self, records, dry_run: bool = False,
                total: Optional[int] = None) -> Dict:
        """从隔离桶移回原桶，标记 blocked=0、is_violation=0（视为误判）。"""
        stats = {'success': 0, 'failed': 0, 'skipped': 0, 'failed_ids': []}
        total_str = f"/{total}" if total else ""

        for i, r in enumerate(records, 1):
            dst_bucket = r['bucket_name']
            dst_key = r['object_key']
            src_key = _quarantine_key(dst_bucket, dst_key)

            if dry_run:
                logger.info(f"[{i}{total_str}] DRY-RUN restore: "
                            f"{self.quarantine_bucket}/{src_key} -> {dst_bucket}/{dst_key}")
                stats['success'] += 1
                continue

            try:
                if not self.minio.object_exists(self.quarantine_bucket, src_key):
                    logger.warning(f"[{i}{total_str}] 隔离桶中已不存在: "
                                   f"{self.quarantine_bucket}/{src_key}")
                    stats['skipped'] += 1
                    continue

                self.minio.move_object(self.quarantine_bucket, src_key, dst_bucket, dst_key)
                try:
                    self.minio.clear_tags(dst_bucket, dst_key)
                except Exception as tag_err:
                    logger.warning(f"  标签清理失败（不影响访问）: {tag_err}")

                self._mark_restored(r['id'])
                stats['success'] += 1
                logger.info(f"[{i}{total_str}] restore 成功: {dst_bucket}/{dst_key}")
            except Exception as e:
                stats['failed'] += 1
                stats['failed_ids'].append(r['id'])
                logger.error(f"[{i}{total_str}] restore 失败: {e}")

            if i % BATCH_SIZE == 0:
                logger.info(f"进度: 已处理 {i}{total_str} 条 | "
                            f"成功={stats['success']} 跳过={stats['skipped']} 失败={stats['failed']}")

        return stats

    def delete(self, records, dry_run: bool = False,
               total: Optional[int] = None) -> Dict:
        """从隔离桶彻底删除，并清除数据库记录。"""
        stats = {'success': 0, 'failed': 0, 'failed_ids': []}
        total_str = f"/{total}" if total else ""

        for i, r in enumerate(records, 1):
            q_key = _quarantine_key(r['bucket_name'], r['object_key'])

            if dry_run:
                logger.info(f"[{i}{total_str}] DRY-RUN delete: "
                            f"{self.quarantine_bucket}/{q_key}")
                stats['success'] += 1
                continue

            try:
                if self.minio.object_exists(self.quarantine_bucket, q_key):
                    self.minio.remove_object(self.quarantine_bucket, q_key)
                else:
                    logger.warning(f"[{i}{total_str}] 隔离桶中已不存在，"
                                   f"仅删数据库记录: {q_key}")

                self.db.execute_query(
                    "DELETE FROM image_scan_records WHERE id = %s",
                    (r['id'],),
                )
                stats['success'] += 1
                logger.info(f"[{i}{total_str}] delete 成功: {q_key}")
            except Exception as e:
                stats['failed'] += 1
                stats['failed_ids'].append(r['id'])
                logger.error(f"[{i}{total_str}] delete 失败: {e}")

            if i % BATCH_SIZE == 0:
                logger.info(f"进度: 已处理 {i}{total_str} 条 | "
                            f"成功={stats['success']} 失败={stats['failed']}")

        return stats

    # ------------------------------------------------------------------ 数据库小工具

    def _mark_quarantined(self, record_id: int, batch_id: str = None):
        self.db.execute_query(
            "UPDATE image_scan_records SET blocked = 2, quarantine_batch_id = %s, updated_at = NOW() WHERE id = %s",
            (batch_id, record_id),
        )

    def _mark_restored(self, record_id: int):
        """从隔离桶恢复，视为误判（blocked=0, is_violation=0，清除违规字段）。"""
        self.db.execute_query(
            "UPDATE image_scan_records "
            "SET blocked = 0, is_violation = 0, "
            "    violation_type = NULL, violation_label = NULL, "
            "    sub_label = NULL, confidence = NULL, "
            "    updated_at = NOW() "
            "WHERE id = %s",
            (record_id,),
        )

    def close(self):
        self.db.close()


# ---------------------------------------------------------------------- CLI 辅助

def _print_records(records: List[Dict], title: str, total: int = None):
    display_total = total if total is not None else len(records)
    if not display_total and not records:
        print(f"\n{title}：无")
        return
    has_batch = any(r.get('quarantine_batch_id') for r in records)
    print(f"\n{title}（共 {display_total} 条）")
    if total is not None and len(records) < total:
        print(f"（仅显示前 {len(records)} 条，使用 --ids 精确操作）")
    header = f"{'ID':<6} {'violation_type':<16} {'suggestion':<10} {'label_cn':<10} {'sub_label_cn':<20} {'置信度':<8}"
    if has_batch:
        header += f" {'批次ID':<18}"
    header += " 路径"
    print(header)
    print("-" * (140 if has_batch else 120))
    for r in records[:50]:
        conf = r.get('confidence') or 0
        vtype = r.get('violation_type') or '-'
        suggestion = r.get('suggestion') or '-'
        label_cn = r.get('violation_label_cn') or r.get('violation_label') or '-'
        sub_cn = r.get('sub_label_cn') or r.get('sub_label') or '-'
        line = f"{r['id']:<6} {vtype:<16} {suggestion:<10} {label_cn:<10} {sub_cn:<20} {conf:<8.2f}"
        if has_batch:
            line += f" {(r.get('quarantine_batch_id') or '-'):<18}"
        line += f" {r['bucket_name']}/{r['object_key']}"
        print(line)
    if len(records) > 50:
        print(f"... 还有 {len(records) - 50} 条未显示")


def _confirm(prompt: str, expected: str = 'yes') -> bool:
    answer = input(f"{prompt} (输入 {expected} 确认): ").strip()
    return answer == expected


def _parse_ids(s: str) -> List[int]:
    return [int(x.strip()) for x in s.split(',') if x.strip()]


def main():
    parser = argparse.ArgumentParser(
        description="违规图片处置工具（两阶段工作流：隔离 / 恢复 / 删除）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
工作流示例：
  ============ 第一步：查看违规 ============
  python handle_violations.py list                                     # 查看所有待处理违规
  python handle_violations.py list --suggestion Block                  # 只看 IMS 建议拦截的
  python handle_violations.py list --label Illegal                     # 只看违法类（含赌博/毒品等）
  python handle_violations.py list --sub-label Gamble                  # 只看赌博 SubLabel
  python handle_violations.py list --confidence 0.9                    # 只看高置信度
  python handle_violations.py list --prefix uploads/2026/             # 只看指定路径前缀

  ============ 第二步：隔离（MinIO 物理移入隔离桶）============
  python handle_violations.py quarantine --suggestion Block            # 自动批次ID
  python handle_violations.py quarantine --prefix uploads/2026/ --suggestion Block  # 只隔离指定前缀
  python handle_violations.py quarantine --suggestion Block --batch gamble_20260520  # 手动批次ID
  python handle_violations.py quarantine --ids 1,2,3                   # 按 ID 隔离
  python handle_violations.py quarantine --ids 1,2,3 --dry-run         # 预演（不实际执行）

  ============ 查看隔离 / 误判恢复 / 彻底删除 ============
  python handle_violations.py list-quarantined                         # 查看已隔离的（含批次ID）
  python handle_violations.py list-quarantined --batch 20260520_143022 # 查看某批次
  python handle_violations.py restore --ids 3,4                        # 按 ID 恢复（输入 yes 确认）
  python handle_violations.py restore --batch 20260520_143022          # 按批次恢复（输入批次ID二次确认）
  python handle_violations.py restore --all                            # 恢复全部（输入 RESTORE-ALL 确认）
  python handle_violations.py restore --batch 20260520_143022 --dry-run  # 预演批次恢复
  python handle_violations.py delete --ids 1,2 --dry-run               # 预演删除
  python handle_violations.py delete --ids 1,2                         # 彻底删除（输入 DELETE 确认）
""",
    )
    sub = parser.add_subparsers(dest='command')

    # list
    p_list = sub.add_parser('list', help='列出原桶中的待处理违规图片（blocked=0/1）')
    p_list.add_argument('--type', dest='violation_type', help='violation_type 字段过滤（如 Gamble/SexyBehavior）')
    p_list.add_argument('--sub-label', dest='sub_label', help='IMS 原始 SubLabel 过滤（如 Gamble/Drug/Blood）')
    p_list.add_argument('--label', dest='violation_label', help='IMS 一级 Label 过滤（如 Illegal/Polity/Porn）')
    p_list.add_argument('--suggestion', help='IMS 建议过滤（Block/Review/Pass）')
    p_list.add_argument('--confidence', type=float, default=0.0, help='置信度阈值（0–1）')
    p_list.add_argument('--ids', help='指定记录 ID，逗号分隔')
    p_list.add_argument('--prefix', help='按 object_key 路径前缀过滤（如 uploads/2026/）')
    p_list.add_argument('--bucket', help='按桶名过滤（如 images）')

    # quarantine
    p_quarantine = sub.add_parser('quarantine', help='隔离违规图片（MinIO 物理移入隔离桶）')
    p_quarantine.add_argument('--ids', help='指定记录 ID，逗号分隔')
    p_quarantine.add_argument('--suggestion', help='IMS 建议过滤（Block/Review/Pass）')
    p_quarantine.add_argument('--type', dest='violation_type', help='violation_type 字段过滤')
    p_quarantine.add_argument('--sub-label', dest='sub_label', help='IMS 原始 SubLabel 过滤')
    p_quarantine.add_argument('--label', dest='violation_label', help='IMS 一级 Label 过滤')
    p_quarantine.add_argument('--confidence', type=float, default=0.0, help='置信度阈值')
    p_quarantine.add_argument('--prefix', help='按 object_key 路径前缀过滤（如 uploads/2026/）')
    p_quarantine.add_argument('--bucket', help='按桶名过滤（如 images）')
    p_quarantine.add_argument('--batch', dest='batch_id',
                              help='手动指定批次ID（留空则自动生成时间戳，如 20260520_143022）')
    p_quarantine.add_argument('--dry-run', action='store_true', help='预演，不实际执行')

    # list-quarantined
    p_lq = sub.add_parser('list-quarantined', help='列出已隔离的图片（blocked=2）')
    p_lq.add_argument('--batch', help='按批次ID过滤')

    # restore
    p_restore = sub.add_parser('restore', help='误判恢复：从隔离桶移回原桶，标记为非违规')
    p_restore.add_argument('--ids', help='指定记录 ID，逗号分隔')
    p_restore.add_argument('--batch', help='按批次ID恢复（quarantine 时打印的批次ID）')
    p_restore.add_argument('--all', dest='restore_all', action='store_true', help='恢复全部已隔离记录')
    p_restore.add_argument('--dry-run', action='store_true', help='预演，不实际执行')

    # delete
    p_delete = sub.add_parser('delete', help='彻底删除（从隔离桶删除，不可恢复）')
    p_delete.add_argument('--ids', required=True, help='指定记录 ID，逗号分隔（必填）')
    p_delete.add_argument('--dry-run', action='store_true', help='预演，不实际执行')

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    handler = ViolationHandler()
    try:
        if args.command == 'list':
            ids = _parse_ids(args.ids) if args.ids else None
            filter_kwargs = dict(
                violation_type=args.violation_type,
                sub_label=args.sub_label,
                violation_label=args.violation_label,
                confidence=args.confidence,
                suggestion=args.suggestion,
                ids=ids,
                prefix=args.prefix or None,
                bucket=args.bucket or None,
            )
            total = handler.count_violations(**filter_kwargs)
            preview = handler.list_violations(**filter_kwargs, limit=DISPLAY_LIMIT)
            _print_records(preview, "待处理的违规图片（原桶）", total=total)

        elif args.command == 'quarantine':
            ids = _parse_ids(args.ids) if args.ids else None
            filter_kwargs = dict(
                violation_type=getattr(args, 'violation_type', None),
                sub_label=getattr(args, 'sub_label', None),
                violation_label=getattr(args, 'violation_label', None),
                confidence=getattr(args, 'confidence', 0.0),
                suggestion=args.suggestion,
                ids=ids,
                prefix=getattr(args, 'prefix', None) or None,
                bucket=getattr(args, 'bucket', None) or None,
            )

            total = handler.count_violations(**filter_kwargs)
            if not total:
                print("没有符合条件的违规图片")
                return

            preview = handler.list_violations(**filter_kwargs, limit=DISPLAY_LIMIT)
            _print_records(preview, "将要隔离的图片", total=total)

            manual_batch = getattr(args, 'batch_id', None)
            if manual_batch:
                print(f"\n批次ID（手动指定）：{manual_batch}")
            else:
                print(f"\n批次ID：自动生成（执行后打印实际值）")

            if args.dry_run:
                preview_batch = manual_batch or datetime.now().strftime('%Y%m%d_%H%M%S') + '_preview'
                # 预演只处理第一批，估算结果
                first_batch = handler.list_violations(**filter_kwargs, limit=BATCH_SIZE)
                stats = handler.quarantine(iter(first_batch), dry_run=True,
                                           batch_id=preview_batch, total=total)
                print(f"\n[DRY-RUN] 预演前 {len(first_batch)} 条（共 {total} 条）"
                      f"  批次ID预览: {stats['batch_id']}")
                return

            if manual_batch:
                if not _confirm(f"\n确认以批次ID [{manual_batch}] 隔离 {total} 张图片"
                                f"（MinIO 层物理移动，原 URL 失效）"):
                    print("已取消")
                    return
            else:
                if not _confirm(f"\n确认隔离 {total} 张图片（MinIO 层物理移动，原 URL 失效）"):
                    print("已取消")
                    return

            # 流式处理，不将全量记录加载到内存
            stats = handler.quarantine(
                handler._iter_violations(**filter_kwargs),
                batch_id=manual_batch, total=total,
            )
            print(f"\n完成 - 成功: {stats['success']} 失败: {stats['failed']} "
                  f"跳过: {stats['skipped']}  批次ID: {stats['batch_id']}")
            if stats['failed_ids']:
                print(f"失败 ID（可用 --ids 重试）: {','.join(map(str, stats['failed_ids']))}")

        elif args.command == 'list-quarantined':
            batch_id = args.batch if args.batch else None
            total = handler.count_quarantined(batch_id=batch_id)
            preview = handler.list_quarantined(batch_id=batch_id, limit=DISPLAY_LIMIT)
            _print_records(preview, "已隔离的图片（隔离桶）", total=total)

        elif args.command == 'restore':
            if not args.ids and not args.batch and not args.restore_all:
                print("请指定 --ids <ID列表>、--batch <批次ID> 或 --all 之一")
                return
            ids = _parse_ids(args.ids) if args.ids else None
            batch_id = args.batch if args.batch else None

            total = handler.count_quarantined(ids=ids, batch_id=batch_id)
            if not total:
                print("没有可恢复的记录（请确认 ID/批次ID 且状态为已隔离）")
                return

            preview = handler.list_quarantined(ids=ids, batch_id=batch_id, limit=DISPLAY_LIMIT)

            if batch_id:
                _print_records(preview, f"将要恢复到原桶的图片（视为误判）— 批次 {batch_id}", total=total)
                if args.dry_run:
                    stats = handler.restore(iter(preview), dry_run=True, total=total)
                    print(f"\n[DRY-RUN] 预计成功: {stats['success']}（共 {total} 条）")
                    return
                print(f"\n⚠  即将恢复批次 [{batch_id}] 的 {total} 张图片到原桶（不可撤销）")
                if not _confirm("请输入批次ID确认", batch_id):
                    print("批次ID不匹配，已取消")
                    return

            elif args.restore_all:
                _print_records(preview, f"将要恢复到原桶的图片（视为误判）— 全部已隔离", total=total)
                if args.dry_run:
                    stats = handler.restore(iter(preview), dry_run=True, total=total)
                    print(f"\n[DRY-RUN] 预计成功: {stats['success']}（共 {total} 条）")
                    return
                print(f"\n⚠  即将恢复全部 {total} 条已隔离记录到原桶（不可撤销）")
                if not _confirm("确认恢复全部已隔离记录", "RESTORE-ALL"):
                    print("已取消")
                    return

            else:  # --ids
                _print_records(preview, "将要恢复到原桶的图片（视为误判）", total=total)
                if args.dry_run:
                    stats = handler.restore(iter(preview), dry_run=True, total=total)
                    print(f"\n[DRY-RUN] 预计成功: {stats['success']}")
                    return
                if not _confirm(f"\n确认恢复 {total} 张图片到原桶"):
                    print("已取消")
                    return

            # 流式处理
            stats = handler.restore(
                handler._iter_quarantined(ids=ids, batch_id=batch_id),
                total=total,
            )
            print(f"\n完成 - 成功: {stats['success']} 失败: {stats['failed']} "
                  f"跳过: {stats['skipped']}")
            if stats['failed_ids']:
                print(f"失败 ID（可用 --ids 重试）: {','.join(map(str, stats['failed_ids']))}")

        elif args.command == 'delete':
            ids = _parse_ids(args.ids)
            total = handler.count_quarantined(ids=ids)
            if not total:
                print("没有可删除的记录（请确认 ID 且状态为已隔离）")
                return
            preview = handler.list_quarantined(ids=ids, limit=DISPLAY_LIMIT)
            _print_records(preview, "将要彻底删除的图片（不可恢复）", total=total)

            if args.dry_run:
                stats = handler.delete(iter(preview), dry_run=True, total=total)
                print(f"\n[DRY-RUN] 预计成功: {stats['success']}")
                return
            if not _confirm(f"\n确认彻底删除 {total} 张？", expected='DELETE'):
                print("已取消")
                return
            # 用流式迭代器确保所有指定 IDs 都被删除，不受 DISPLAY_LIMIT 限制
            stats = handler.delete(handler._iter_quarantined(ids=ids), total=total)
            print(f"\n完成 - 成功: {stats['success']} 失败: {stats['failed']}")
            if stats['failed_ids']:
                print(f"失败 ID（可用 --ids 重试）: {','.join(map(str, stats['failed_ids']))}")

    except KeyboardInterrupt:
        print("\n已中断")
    finally:
        handler.close()


if __name__ == '__main__':
    main()
