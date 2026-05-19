#!/usr/bin/env python3
"""违规图片处置工具：三阶段处理（私密观察 -> 隔离 -> 删除）。

机制：
- mark_private:       原桶 -> 标记私密（无法公开访问，但保留在原桶观察）
- confirm_quarantine: 原桶(private) -> 隔离桶（观察正常，彻底隔离）
- restore_public:     原桶(private) -> 改回公开（观察异常，视为误判）
- delete:             隔离桶 -> 彻底删除

数据库 `blocked` 字段标识当前状态：
  0 = public      （未处理）
  1 = private     （隐藏观察期）
  2 = quarantined （已隔离）
"""

import argparse
import os
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
        self.quarantine = os.getenv('QUARANTINE_BUCKET_NAME', 'quarantine')
        # 隔离桶不存在则建。生产环境建议手工建好并配好不公开的策略。
        self.minio.ensure_bucket(self.quarantine)

    # ------------------------------------------------------------------ 查询

    def list_violations(self, violation_type: str = None,
                        confidence: float = 0.0,
                        only_active: bool = True) -> List[Dict]:
        """列出违规图片。only_active=True 只返回尚未处理的（blocked=0）。"""
        query = """
            SELECT id, bucket_name, object_key, violation_type,
                   violation_label, confidence, blocked
            FROM image_scan_records
            WHERE is_violation = 1
        """
        params = []
        if violation_type:
            query += " AND violation_type = %s"
            params.append(violation_type)
        if confidence > 0:
            query += " AND confidence >= %s"
            params.append(confidence)
        if only_active:
            query += " AND blocked = 0"
        query += " ORDER BY violation_type, confidence DESC"
        return self.db.execute_query(query, tuple(params), fetch=True)

    def list_private(self, violation_type: str = None,
                     confidence: float = 0.0, ids: List[int] = None) -> List[Dict]:
        """列出标记为 private 的图片（观察期）。blocked=1"""
        query = """
            SELECT id, bucket_name, object_key, violation_type, confidence, blocked
            FROM image_scan_records
            WHERE blocked = 1
        """
        params = []
        if ids:
            placeholders = ','.join(['%s'] * len(ids))
            query += f" AND id IN ({placeholders})"
            params.extend(ids)
        if violation_type:
            query += " AND violation_type = %s"
            params.append(violation_type)
        if confidence > 0:
            query += " AND confidence >= %s"
            params.append(confidence)
        query += " ORDER BY updated_at DESC"
        return self.db.execute_query(query, tuple(params), fetch=True)

    def list_quarantined(self, ids: List[int] = None) -> List[Dict]:
        """已被隔离（迁移到隔离桶）的记录。blocked=2"""
        if ids:
            placeholders = ','.join(['%s'] * len(ids))
            query = f"""
                SELECT id, bucket_name, object_key, violation_type, confidence, blocked
                FROM image_scan_records
                WHERE blocked = 2 AND id IN ({placeholders})
            """
            return self.db.execute_query(query, tuple(ids), fetch=True)

        return self.db.execute_query(
            """
            SELECT id, bucket_name, object_key, violation_type, confidence, blocked
            FROM image_scan_records
            WHERE blocked = 2
            ORDER BY updated_at DESC
            """,
            fetch=True,
        )

    # ------------------------------------------------------------------ 操作

    def mark_private(self, records: List[Dict], dry_run: bool = False) -> Dict:
        """第一阶段：标记违规图片为私密（隐藏观察，保留在原桶）。"""
        stats = {'success': 0, 'failed': 0, 'skipped': 0}
        for i, r in enumerate(records, 1):
            bucket = r['bucket_name']
            key = r['object_key']

            if dry_run:
                logger.info(f"[{i}/{len(records)}] DRY-RUN mark-private: "
                            f"{bucket}/{key}")
                stats['success'] += 1
                continue

            try:
                if not self.minio.object_exists(bucket, key):
                    logger.warning(f"[{i}/{len(records)}] 对象不存在，仅标记数据库: "
                                   f"{bucket}/{key}")
                    self._mark_private(r['id'])
                    stats['skipped'] += 1
                    continue

                self.minio.set_object_private(bucket, key)
                self._mark_private(r['id'])
                stats['success'] += 1
                logger.info(f"[{i}/{len(records)}] mark-private 成功: {bucket}/{key}")
            except Exception as e:
                stats['failed'] += 1
                logger.error(f"[{i}/{len(records)}] mark-private 失败 {bucket}/{key}: {e}")
        return stats

    def confirm_quarantine(self, records: List[Dict], dry_run: bool = False) -> Dict:
        """第二阶段-A：观察正常，把 private 图片移到隔离桶。"""
        stats = {'success': 0, 'failed': 0, 'skipped': 0}
        for i, r in enumerate(records, 1):
            src_bucket = r['bucket_name']
            src_key = r['object_key']
            dst_key = _quarantine_key(src_bucket, src_key)

            if dry_run:
                logger.info(f"[{i}/{len(records)}] DRY-RUN confirm-quarantine: "
                            f"{src_bucket}/{src_key} -> {self.quarantine}/{dst_key}")
                stats['success'] += 1
                continue

            try:
                if not self.minio.object_exists(src_bucket, src_key):
                    logger.warning(f"[{i}/{len(records)}] 源对象不存在，仅标记: "
                                   f"{src_bucket}/{src_key}")
                    self._mark_quarantined(r['id'])
                    stats['skipped'] += 1
                    continue

                self.minio.move_object(src_bucket, src_key, self.quarantine, dst_key)
                try:
                    self.minio.set_violation_tag(self.quarantine, dst_key,
                                                 violation_type=r.get('violation_type'))
                except Exception as tag_err:
                    logger.warning(f"  标签写入失败（不影响隔离）: {tag_err}")

                self._mark_quarantined(r['id'])
                stats['success'] += 1
                logger.info(f"[{i}/{len(records)}] confirm-quarantine 成功: {src_bucket}/{src_key}")
            except Exception as e:
                stats['failed'] += 1
                logger.error(f"[{i}/{len(records)}] confirm-quarantine 失败 {src_bucket}/{src_key}: {e}")
        return stats

    def restore_public(self, records: List[Dict], dry_run: bool = False) -> Dict:
        """第二阶段-B：观察异常，把 private 改回 public（视为误判）。"""
        stats = {'success': 0, 'failed': 0, 'skipped': 0}
        for i, r in enumerate(records, 1):
            bucket = r['bucket_name']
            key = r['object_key']

            if dry_run:
                logger.info(f"[{i}/{len(records)}] DRY-RUN restore-public: "
                            f"{bucket}/{key}")
                stats['success'] += 1
                continue

            try:
                if not self.minio.object_exists(bucket, key):
                    logger.warning(f"[{i}/{len(records)}] 对象不存在，仅更新数据库: "
                                   f"{bucket}/{key}")
                    self._restore_public(r['id'])
                    stats['skipped'] += 1
                    continue

                self.minio.set_object_public(bucket, key)
                self._restore_public(r['id'])
                stats['success'] += 1
                logger.info(f"[{i}/{len(records)}] restore-public 成功: {bucket}/{key}")
            except Exception as e:
                stats['failed'] += 1
                logger.error(f"[{i}/{len(records)}] restore-public 失败 {bucket}/{key}: {e}")
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
                            f"{self.quarantine}/{src_key} -> {dst_bucket}/{dst_key}")
                stats['success'] += 1
                continue

            try:
                if not self.minio.object_exists(self.quarantine, src_key):
                    logger.warning(f"[{i}/{len(records)}] 隔离桶中已不存在: "
                                   f"{self.quarantine}/{src_key}")
                    stats['skipped'] += 1
                    continue

                self.minio.move_object(self.quarantine, src_key, dst_bucket, dst_key)
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
        """第三阶段：从隔离桶彻底删除，并清除数据库记录。"""
        stats = {'success': 0, 'failed': 0}
        for i, r in enumerate(records, 1):
            q_key = _quarantine_key(r['bucket_name'], r['object_key'])

            if dry_run:
                logger.info(f"[{i}/{len(records)}] DRY-RUN delete: "
                            f"{self.quarantine}/{q_key}")
                stats['success'] += 1
                continue

            try:
                if self.minio.object_exists(self.quarantine, q_key):
                    self.minio.remove_object(self.quarantine, q_key)
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

    def _mark_private(self, record_id: int):
        """标记为 private（blocked=1）"""
        self.db.execute_query(
            "UPDATE image_scan_records SET blocked = 1, updated_at = NOW() WHERE id = %s",
            (record_id,),
        )

    def _mark_quarantined(self, record_id: int):
        """标记为隔离（blocked=2）"""
        self.db.execute_query(
            "UPDATE image_scan_records SET blocked = 2, updated_at = NOW() WHERE id = %s",
            (record_id,),
        )

    def _restore_public(self, record_id: int):
        """改回 public，视为误判（blocked=0, is_violation=0）"""
        self.db.execute_query(
            "UPDATE image_scan_records SET blocked = 0, is_violation = 0, "
            "updated_at = NOW() WHERE id = %s",
            (record_id,),
        )

    def _mark_restored(self, record_id: int):
        """从隔离桶恢复，视为误判（blocked=0, is_violation=0）"""
        self.db.execute_query(
            "UPDATE image_scan_records SET blocked = 0, is_violation = 0, "
            "updated_at = NOW() WHERE id = %s",
            (record_id,),
        )

    def close(self):
        self.db.close()


# ---------------------------------------------------------------------- CLI 辅助

def _print_records(records: List[Dict], title: str):
    if not records:
        print(f"\n{title}：无")
        return
    print(f"\n{title}（共 {len(records)} 条）")
    print(f"{'ID':<6} {'类型':<12} {'置信度':<8} 路径")
    print("-" * 80)
    for r in records[:50]:
        conf = r.get('confidence') or 0
        vtype = r.get('violation_type') or '-'
        print(f"{r['id']:<6} {vtype:<12} {conf:<8.2f} "
              f"{r['bucket_name']}/{r['object_key']}")
    if len(records) > 50:
        print(f"... 还有 {len(records) - 50} 条未显示")


def _confirm(prompt: str, expected: str = 'yes') -> bool:
    answer = input(f"{prompt} (输入 {expected} 确认): ").strip()
    return answer == expected


def _parse_ids(s: str) -> List[int]:
    return [int(x.strip()) for x in s.split(',') if x.strip()]


def main():
    parser = argparse.ArgumentParser(
        description="违规图片处置工具（三阶段工作流）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
工作流示例：
  ============ 第一阶段：标记为私密（观察期）============
  python handle_violations.py list                       # 查看新增违规
  python handle_violations.py mark-private --type gambling     # 标记赌博类为私密
  python handle_violations.py list-private               # 查看观察中的图片

  ============ 第二阶段：确认后处理 ============
  python handle_violations.py confirm-quarantine --ids 1,2     # 观察正常 → 隔离
  python handle_violations.py restore-public --ids 3,4         # 观察异常 → 改为公开

  ============ 第三阶段：彻底删除 ============
  python handle_violations.py list-quarantined          # 查看隔离的
  python handle_violations.py delete --ids 5,6          # 从隔离桶彻底删除
""",
    )
    sub = parser.add_subparsers(dest='command')

    p_list = sub.add_parser('list', help='列出未处理的违规图片（blocked=0）')
    p_list.add_argument('--type', help='违规类型过滤')
    p_list.add_argument('--confidence', type=float, default=0.0, help='置信度阈值')

    p_mark_private = sub.add_parser('mark-private', help='标记为私密（第一阶段）')
    p_mark_private.add_argument('--type', help='违规类型过滤')
    p_mark_private.add_argument('--confidence', type=float, default=0.0, help='置信度阈值')
    p_mark_private.add_argument('--ids', help='指定记录 ID，逗号分隔')
    p_mark_private.add_argument('--dry-run', action='store_true')

    p_list_private = sub.add_parser('list-private', help='列出私密观察中的图片（blocked=1）')
    p_list_private.add_argument('--type', help='违规类型过滤')
    p_list_private.add_argument('--confidence', type=float, default=0.0, help='置信度阈值')

    p_confirm = sub.add_parser('confirm-quarantine', help='确认隔离（第二阶段-A：观察正常）')
    p_confirm.add_argument('--ids', help='指定记录 ID，逗号分隔')
    p_confirm.add_argument('--dry-run', action='store_true')

    p_restore = sub.add_parser('restore-public', help='改回公开（第二阶段-B：观察异常）')
    p_restore.add_argument('--ids', help='指定记录 ID，逗号分隔')
    p_restore.add_argument('--dry-run', action='store_true')

    p_list_quarantined = sub.add_parser('list-quarantined', help='列出隔离的图片（blocked=2）')

    p_delete = sub.add_parser('delete', help='彻底删除（第三阶段）')
    p_delete.add_argument('--ids', help='指定记录 ID，逗号分隔；省略则删除全部')
    p_delete.add_argument('--dry-run', action='store_true')

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    handler = ViolationHandler()
    try:
        if args.command == 'list':
            records = handler.list_violations(args.type, args.confidence)
            _print_records(records, "未处理的违规图片（blocked=0）")

        elif args.command == 'mark-private':
            if args.ids:
                placeholders = ','.join(['%s'] * len(_parse_ids(args.ids)))
                records = handler.db.execute_query(
                    f"SELECT id, bucket_name, object_key, violation_type, confidence "
                    f"FROM image_scan_records WHERE id IN ({placeholders}) AND blocked = 0",
                    tuple(_parse_ids(args.ids)),
                    fetch=True,
                )
            else:
                records = handler.list_violations(args.type, args.confidence)

            if not records:
                print("没有符合条件的违规图片")
                return
            _print_records(records, "将要标记为私密的图片")

            if args.dry_run:
                stats = handler.mark_private(records, dry_run=True)
                print(f"\n[DRY-RUN] 预计成功: {stats['success']}")
                return
            if not _confirm(f"\n确认标记 {len(records)} 张图片为私密？"):
                print("已取消")
                return
            stats = handler.mark_private(records)
            print(f"\n完成 - 成功: {stats['success']} 失败: {stats['failed']} "
                  f"跳过: {stats['skipped']}")

        elif args.command == 'list-private':
            records = handler.list_private(args.type, args.confidence)
            _print_records(records, "私密观察中的图片（blocked=1）")

        elif args.command == 'confirm-quarantine':
            ids = _parse_ids(args.ids) if args.ids else None
            records = handler.list_private(ids=ids)
            if not records:
                print("没有可隔离的记录")
                return
            _print_records(records, "将要隔离的图片")

            if args.dry_run:
                stats = handler.confirm_quarantine(records, dry_run=True)
                print(f"\n[DRY-RUN] 预计成功: {stats['success']}")
                return
            if not _confirm(f"\n确认隔离 {len(records)} 张图片？"):
                print("已取消")
                return
            stats = handler.confirm_quarantine(records)
            print(f"\n完成 - 成功: {stats['success']} 失败: {stats['failed']} "
                  f"跳过: {stats['skipped']}")

        elif args.command == 'restore-public':
            ids = _parse_ids(args.ids) if args.ids else None
            records = handler.list_private(ids=ids)
            if not records:
                print("没有可恢复的记录")
                return
            _print_records(records, "将要改为公开的图片")

            if args.dry_run:
                stats = handler.restore_public(records, dry_run=True)
                print(f"\n[DRY-RUN] 预计成功: {stats['success']}")
                return
            if not _confirm(f"\n确认改为公开 {len(records)} 张图片？"):
                print("已取消")
                return
            stats = handler.restore_public(records)
            print(f"\n完成 - 成功: {stats['success']} 失败: {stats['failed']} "
                  f"跳过: {stats['skipped']}")

        elif args.command == 'list-quarantined':
            records = handler.list_quarantined()
            _print_records(records, "隔离中的图片（blocked=2）")

        elif args.command == 'delete':
            ids = _parse_ids(args.ids) if args.ids else None
            records = handler.list_quarantined(ids=ids)
            if not records:
                print("没有可删除的记录")
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
