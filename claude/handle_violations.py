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
from typing import Dict, List

from dotenv import load_dotenv

from logger_config import setup_logger
from database import ImageDatabase
from minio_client import MinIOClient

load_dotenv()
logger = setup_logger(log_dir="logs")


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

    # ------------------------------------------------------------------ 查询

    def list_violations(self, violation_type: str = None,
                        sub_label: str = None,
                        violation_label: str = None,
                        confidence: float = 0.0,
                        suggestion: str = None,
                        ids: List[int] = None) -> List[Dict]:
        """列出原桶中的违规图片（blocked=0 或旧版 blocked=1，均在原桶未被隔离）。

        violation_type:  SubLabel 值过滤（如 Gamble/SexyBehavior）
        sub_label:       IMS 原始 SubLabel 过滤
        violation_label: IMS 一级 Label 过滤（Illegal/Polity/Porn/Ad/…）
        suggestion:      IMS 建议过滤（Block/Review/Pass）
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
        query += " ORDER BY violation_label, sub_label, confidence DESC"
        return self.db.execute_query(query, tuple(params), fetch=True)

    def list_quarantined(self, ids: List[int] = None, batch_id: str = None) -> List[Dict]:
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
        return self.db.execute_query(query, tuple(params) if params else None, fetch=True)

    # ------------------------------------------------------------------ 操作

    def quarantine(self, records: List[Dict], dry_run: bool = False,
                   batch_id: str = None) -> Dict:
        """将违规图片从原桶移入隔离桶（MinIO 层物理隔离，原 URL 立即失效）。

        适用于 blocked=0 或旧版 blocked=1 的记录（两者均在原桶）。
        batch_id 由调用方传入（手动指定）或留空（自动生成时间戳）。
        """
        if batch_id is None:
            batch_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        stats = {'success': 0, 'failed': 0, 'skipped': 0, 'batch_id': batch_id}
        for i, r in enumerate(records, 1):
            src_bucket = r['bucket_name']
            src_key = r['object_key']
            dst_key = _quarantine_key(src_bucket, src_key)

            if dry_run:
                logger.info(f"[{i}/{len(records)}] DRY-RUN quarantine: "
                            f"{src_bucket}/{src_key} -> {self.quarantine_bucket}/{dst_key}")
                stats['success'] += 1
                continue

            try:
                if not self.minio.object_exists(src_bucket, src_key):
                    logger.warning(f"[{i}/{len(records)}] 源对象不存在，仅标记: "
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
                logger.info(f"[{i}/{len(records)}] quarantine 成功: {src_bucket}/{src_key}")
            except Exception as e:
                stats['failed'] += 1
                logger.error(f"[{i}/{len(records)}] quarantine 失败 {src_bucket}/{src_key}: {e}")
        return stats

    def restore(self, records: List[Dict], dry_run: bool = False) -> Dict:
        """从隔离桶移回原桶，标记 blocked=0、is_violation=0（视为误判）。"""
        stats = {'success': 0, 'failed': 0, 'skipped': 0}
        for i, r in enumerate(records, 1):
            dst_bucket = r['bucket_name']
            dst_key = r['object_key']
            src_key = _quarantine_key(dst_bucket, dst_key)

            if dry_run:
                logger.info(f"[{i}/{len(records)}] DRY-RUN restore: "
                            f"{self.quarantine_bucket}/{src_key} -> {dst_bucket}/{dst_key}")
                stats['success'] += 1
                continue

            try:
                if not self.minio.object_exists(self.quarantine_bucket, src_key):
                    logger.warning(f"[{i}/{len(records)}] 隔离桶中已不存在: "
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
                logger.info(f"[{i}/{len(records)}] restore 成功: {dst_bucket}/{dst_key}")
            except Exception as e:
                stats['failed'] += 1
                logger.error(f"[{i}/{len(records)}] restore 失败: {e}")
        return stats

    def delete(self, records: List[Dict], dry_run: bool = False) -> Dict:
        """从隔离桶彻底删除，并清除数据库记录。"""
        stats = {'success': 0, 'failed': 0}
        for i, r in enumerate(records, 1):
            q_key = _quarantine_key(r['bucket_name'], r['object_key'])

            if dry_run:
                logger.info(f"[{i}/{len(records)}] DRY-RUN delete: "
                            f"{self.quarantine_bucket}/{q_key}")
                stats['success'] += 1
                continue

            try:
                if self.minio.object_exists(self.quarantine_bucket, q_key):
                    self.minio.remove_object(self.quarantine_bucket, q_key)
                else:
                    logger.warning(f"[{i}/{len(records)}] 隔离桶中已不存在，"
                                   f"仅删数据库记录: {q_key}")

                self.db.execute_query(
                    "DELETE FROM image_scan_records WHERE id = %s",
                    (r['id'],),
                )
                stats['success'] += 1
                logger.info(f"[{i}/{len(records)}] delete 成功: {q_key}")
            except Exception as e:
                stats['failed'] += 1
                logger.error(f"[{i}/{len(records)}] delete 失败: {e}")
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

def _print_records(records: List[Dict], title: str):
    if not records:
        print(f"\n{title}：无")
        return
    has_batch = any(r.get('quarantine_batch_id') for r in records)
    print(f"\n{title}（共 {len(records)} 条）")
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

  ============ 第二步：隔离（MinIO 物理移入隔离桶）============
  python handle_violations.py quarantine --suggestion Block            # 自动批次ID
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

    # quarantine
    p_quarantine = sub.add_parser('quarantine', help='隔离违规图片（MinIO 物理移入隔离桶）')
    p_quarantine.add_argument('--ids', help='指定记录 ID，逗号分隔')
    p_quarantine.add_argument('--suggestion', help='IMS 建议过滤（Block/Review/Pass）')
    p_quarantine.add_argument('--type', dest='violation_type', help='violation_type 字段过滤')
    p_quarantine.add_argument('--sub-label', dest='sub_label', help='IMS 原始 SubLabel 过滤')
    p_quarantine.add_argument('--label', dest='violation_label', help='IMS 一级 Label 过滤')
    p_quarantine.add_argument('--confidence', type=float, default=0.0, help='置信度阈值')
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
            records = handler.list_violations(
                args.violation_type, args.sub_label, args.violation_label,
                args.confidence, args.suggestion, ids,
            )
            _print_records(records, "待处理的违规图片（原桶）")

        elif args.command == 'quarantine':
            ids = _parse_ids(args.ids) if args.ids else None
            records = handler.list_violations(
                getattr(args, 'violation_type', None),
                getattr(args, 'sub_label', None),
                getattr(args, 'violation_label', None),
                getattr(args, 'confidence', 0.0),
                args.suggestion,
                ids,
            )
            if not records:
                print("没有符合条件的违规图片")
                return
            _print_records(records, "将要隔离的图片")

            # 批次ID：手动指定或自动生成（预演时展示预览值）
            manual_batch = getattr(args, 'batch_id', None)
            if manual_batch:
                print(f"\n批次ID（手动指定）：{manual_batch}")
            else:
                print(f"\n批次ID：自动生成（执行后打印实际值）")

            if args.dry_run:
                preview_batch = manual_batch or datetime.now().strftime('%Y%m%d_%H%M%S') + '_preview'
                stats = handler.quarantine(records, dry_run=True, batch_id=preview_batch)
                print(f"\n[DRY-RUN] 预计成功: {stats['success']}  批次ID预览: {stats['batch_id']}")
                return

            if manual_batch:
                if not _confirm(f"\n确认以批次ID [{manual_batch}] 隔离 {len(records)} 张图片"
                                f"（MinIO 层物理移动，原 URL 失效）"):
                    print("已取消")
                    return
            else:
                if not _confirm(f"\n确认隔离 {len(records)} 张图片（MinIO 层物理移动，原 URL 失效）"):
                    print("已取消")
                    return

            stats = handler.quarantine(records, batch_id=manual_batch)
            print(f"\n完成 - 成功: {stats['success']} 失败: {stats['failed']} "
                  f"跳过: {stats['skipped']}  批次ID: {stats['batch_id']}")

        elif args.command == 'list-quarantined':
            records = handler.list_quarantined(batch_id=args.batch if args.batch else None)
            _print_records(records, "已隔离的图片（隔离桶）")

        elif args.command == 'restore':
            if not args.ids and not args.batch and not args.restore_all:
                print("请指定 --ids <ID列表>、--batch <批次ID> 或 --all 之一")
                return
            ids = _parse_ids(args.ids) if args.ids else None
            records = handler.list_quarantined(ids=ids, batch_id=args.batch if args.batch else None)
            if not records:
                print("没有可恢复的记录（请确认 ID/批次ID 且状态为已隔离）")
                return

            if args.batch:
                _print_records(records, f"将要恢复到原桶的图片（视为误判）— 批次 {args.batch}")
                if args.dry_run:
                    stats = handler.restore(records, dry_run=True)
                    print(f"\n[DRY-RUN] 预计成功: {stats['success']}")
                    return
                print(f"\n⚠  即将恢复批次 [{args.batch}] 的 {len(records)} 张图片到原桶（不可撤销）")
                if not _confirm("请输入批次ID确认", args.batch):
                    print("批次ID不匹配，已取消")
                    return

            elif args.restore_all:
                _print_records(records, f"将要恢复到原桶的图片（视为误判）— 全部已隔离 {len(records)} 条")
                if args.dry_run:
                    stats = handler.restore(records, dry_run=True)
                    print(f"\n[DRY-RUN] 预计成功: {stats['success']}")
                    return
                print(f"\n⚠  即将恢复全部 {len(records)} 条已隔离记录到原桶（不可撤销）")
                if not _confirm("确认恢复全部已隔离记录", "RESTORE-ALL"):
                    print("已取消")
                    return

            else:  # --ids
                _print_records(records, "将要恢复到原桶的图片（视为误判）")
                if args.dry_run:
                    stats = handler.restore(records, dry_run=True)
                    print(f"\n[DRY-RUN] 预计成功: {stats['success']}")
                    return
                if not _confirm(f"\n确认恢复 {len(records)} 张图片到原桶"):
                    print("已取消")
                    return

            stats = handler.restore(records)
            print(f"\n完成 - 成功: {stats['success']} 失败: {stats['failed']} "
                  f"跳过: {stats['skipped']}")

        elif args.command == 'delete':
            ids = _parse_ids(args.ids)
            records = handler.list_quarantined(ids=ids)
            if not records:
                print("没有可删除的记录（请确认 ID 且状态为已隔离）")
                return
            _print_records(records, "将要彻底删除的图片（不可恢复）")

            if args.dry_run:
                stats = handler.delete(records, dry_run=True)
                print(f"\n[DRY-RUN] 预计成功: {stats['success']}")
                return
            if not _confirm(f"\n确认彻底删除 {len(records)} 张？", expected='DELETE'):
                print("已取消")
                return
            stats = handler.delete(records)
            print(f"\n完成 - 成功: {stats['success']} 失败: {stats['failed']}")

    except KeyboardInterrupt:
        print("\n已中断")
    finally:
        handler.close()


if __name__ == '__main__':
    main()
