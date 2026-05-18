#!/usr/bin/env python3
"""违规图片处置工具：把违规图片从业务桶移到隔离桶，确认后再彻底删除。

机制：
- block:   原桶 -> 隔离桶（URL 失效，用户无法访问）+ 打 violation 标签做标记
- restore: 隔离桶 -> 原桶（恢复访问）+ 清除标签
- delete:  从隔离桶彻底删除

数据库 `blocked` 字段标识当前状态：0=在原桶，1=已移至隔离桶。
原始 bucket_name/object_key 始终保留在记录中，作为"应在的位置"。
"""

import argparse
import os
import sys
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
        """列出违规图片。only_active=True 只返回尚未 block 的。"""
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

    def list_blocked(self, ids: List[int] = None) -> List[Dict]:
        """已被 block（迁移到隔离桶）的记录。"""
        if ids:
            placeholders = ','.join(['%s'] * len(ids))
            query = f"""
                SELECT id, bucket_name, object_key, violation_type, confidence
                FROM image_scan_records
                WHERE blocked = 1 AND id IN ({placeholders})
            """
            return self.db.execute_query(query, tuple(ids), fetch=True)

        return self.db.execute_query(
            """
            SELECT id, bucket_name, object_key, violation_type, confidence
            FROM image_scan_records
            WHERE blocked = 1
            ORDER BY updated_at DESC
            """,
            fetch=True,
        )

    # ------------------------------------------------------------------ 操作

    def block(self, records: List[Dict], dry_run: bool = False) -> Dict:
        """把违规图片从原桶移到隔离桶。"""
        stats = {'success': 0, 'failed': 0, 'skipped': 0}
        for i, r in enumerate(records, 1):
            src_bucket = r['bucket_name']
            src_key = r['object_key']
            dst_key = _quarantine_key(src_bucket, src_key)

            if dry_run:
                logger.info(f"[{i}/{len(records)}] DRY-RUN block: "
                            f"{src_bucket}/{src_key} -> {self.quarantine}/{dst_key}")
                stats['success'] += 1
                continue

            try:
                # 源文件已经不存在（之前被人删过）则只更新数据库即可。
                if not self.minio.object_exists(src_bucket, src_key):
                    logger.warning(f"[{i}/{len(records)}] 源对象不存在，仅标记: "
                                   f"{src_bucket}/{src_key}")
                    self._mark_blocked(r['id'])
                    stats['skipped'] += 1
                    continue

                self.minio.move_object(src_bucket, src_key, self.quarantine, dst_key)
                # 在隔离桶里打个标签做标记（不参与权限控制）。
                try:
                    self.minio.set_violation_tag(self.quarantine, dst_key,
                                                 violation_type=r.get('violation_type'))
                except Exception as tag_err:
                    logger.warning(f"  标签写入失败（不影响隔离）: {tag_err}")

                self._mark_blocked(r['id'])
                stats['success'] += 1
                logger.info(f"[{i}/{len(records)}] block 成功: {src_bucket}/{src_key}")
            except Exception as e:
                stats['failed'] += 1
                logger.error(f"[{i}/{len(records)}] block 失败 {src_bucket}/{src_key}: {e}")
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
        """从隔离桶彻底删除，并清除数据库记录。"""
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

    def _mark_blocked(self, record_id: int):
        self.db.execute_query(
            "UPDATE image_scan_records SET blocked = 1, updated_at = NOW() WHERE id = %s",
            (record_id,),
        )

    def _mark_restored(self, record_id: int):
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
        description="违规图片处置工具（隔离桶迁移）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
工作流示例：
  python handle_violations.py list                       # 查看所有违规图片
  python handle_violations.py list --type gambling       # 仅看赌博类
  python handle_violations.py block --type gambling      # 把赌博类移到隔离桶
  python handle_violations.py list-blocked               # 查看已隔离清单
  python handle_violations.py restore --ids 1,2          # 把指定记录移回原桶
  python handle_violations.py delete --ids 3,4           # 从隔离桶彻底删除
""",
    )
    sub = parser.add_subparsers(dest='command')

    p_list = sub.add_parser('list', help='列出违规图片（尚未隔离的）')
    p_list.add_argument('--type', help='违规类型过滤')
    p_list.add_argument('--confidence', type=float, default=0.0, help='置信度阈值')

    p_block = sub.add_parser('block', help='把违规图片移到隔离桶')
    p_block.add_argument('--type', help='违规类型过滤')
    p_block.add_argument('--confidence', type=float, default=0.0, help='置信度阈值')
    p_block.add_argument('--ids', help='指定记录 ID，逗号分隔')
    p_block.add_argument('--dry-run', action='store_true')

    sub.add_parser('list-blocked', help='列出已隔离的图片')

    p_restore = sub.add_parser('restore', help='从隔离桶恢复到原桶')
    p_restore.add_argument('--ids', help='指定记录 ID，逗号分隔；省略则恢复全部')
    p_restore.add_argument('--dry-run', action='store_true')

    p_delete = sub.add_parser('delete', help='从隔离桶彻底删除')
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
            _print_records(records, "违规图片（未隔离）")

        elif args.command == 'list-blocked':
            records = handler.list_blocked()
            _print_records(records, "已隔离图片")

        elif args.command == 'block':
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
            _print_records(records, "将要隔离的图片")

            if args.dry_run:
                stats = handler.block(records, dry_run=True)
                print(f"\n[DRY-RUN] 预计成功: {stats['success']}")
                return
            if not _confirm(f"\n确认隔离 {len(records)} 张图片？"):
                print("已取消")
                return
            stats = handler.block(records)
            print(f"\n完成 - 成功: {stats['success']} 失败: {stats['failed']} "
                  f"跳过: {stats['skipped']}")

        elif args.command == 'restore':
            ids = _parse_ids(args.ids) if args.ids else None
            records = handler.list_blocked(ids=ids)
            if not records:
                print("没有可恢复的记录")
                return
            _print_records(records, "将要恢复的图片")

            if args.dry_run:
                stats = handler.restore(records, dry_run=True)
                print(f"\n[DRY-RUN] 预计成功: {stats['success']}")
                return
            if not _confirm(f"\n确认恢复 {len(records)} 张图片到原桶？"):
                print("已取消")
                return
            stats = handler.restore(records)
            print(f"\n完成 - 成功: {stats['success']} 失败: {stats['failed']} "
                  f"跳过: {stats['skipped']}")

        elif args.command == 'delete':
            ids = _parse_ids(args.ids) if args.ids else None
            records = handler.list_blocked(ids=ids)
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
