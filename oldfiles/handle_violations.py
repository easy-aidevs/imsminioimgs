#!/usr/bin/env python3
"""
违规图片处理工具
支持通过MinIO对象标签标记违规图片、恢复和彻底删除

工作流程：
1. 扫描并标记违规图片（设置对象标签为blocked）
2. 被标记的图片无法公开访问（相当于private）
3. 确认无误后，可彻底删除或恢复误判文件
"""

import os
import sys
import argparse
from datetime import datetime
from typing import List, Dict
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 导入日志配置
from logger_config import setup_logger
logger = setup_logger(log_dir="logs")

from database import ImageDatabase
from minio_client import MinIOClient


class ViolationHandler:
    """违规图片处理器"""
    
    def __init__(self):
        """初始化数据库和MinIO客户端"""
        self.db = ImageDatabase(
            host=os.getenv('MYSQL_HOST', 'localhost'),
            port=int(os.getenv('MYSQL_PORT', '3306')),
            user=os.getenv('MYSQL_USER', 'root'),
            password=os.getenv('MYSQL_PASSWORD'),
            database=os.getenv('MYSQL_DATABASE', 'image_security')
        )
        
        self.minio = MinIOClient(
            endpoint=os.getenv('MINIO_ENDPOINT', 'localhost:9000'),
            access_key=os.getenv('MINIO_ACCESS_KEY'),
            secret_key=os.getenv('MINIO_SECRET_KEY'),
            secure=os.getenv('MINIO_SECURE', 'false').lower() == 'true'
        )
        
        # ✅ 自动设置 Bucket Policy，确保 blocked 对象无法访问
        self._setup_bucket_policy()
        
        logger.info("违规图片处理器初始化完成")
    
    def _setup_bucket_policy(self):
        """
        设置 Bucket Policy，拒绝访问带 blocked 标签的对象
        对所有存储桶生效
        """
        try:
            buckets = self.minio.list_buckets()
            for bucket in buckets:
                logger.info(f"为存储桶 {bucket} 设置 Block Policy...")
                self.minio.set_bucket_policy_block_tagged_objects(bucket)
            logger.info("✅ 所有存储桶的 Block Policy 设置完成")
        except Exception as e:
            logger.error(f"⚠️ 设置 Bucket Policy 失败: {e}")
            logger.warning("⚠️ 违规图片可能仍然可以公开访问，请手动配置 Bucket Policy")
    
    def get_violations(self, violation_type: str = None, 
                      confidence_threshold: float = 0.0,
                      exclude_blocked: bool = True) -> List[Dict]:
        """
        获取违规图片列表
        
        Args:
            violation_type: 违规类型过滤，None表示所有类型
            confidence_threshold: 置信度阈值
            exclude_blocked: 是否排除已blocked的文件
            
        Returns:
            违规图片列表
        """
        query = """
            SELECT id, bucket_name, object_key, violation_type, 
                   violation_label, confidence, `key`
            FROM image_scan_records
            WHERE is_violation = 1
        """
        params = []
        
        if violation_type:
            query += " AND violation_type = %s"
            params.append(violation_type)
        
        if confidence_threshold > 0:
            query += " AND confidence >= %s"
            params.append(confidence_threshold)
        
        if exclude_blocked:
            query += " AND blocked = 0"  # ✅ blocked 字段有默认值 0，不会是 NULL
        
        query += " ORDER BY violation_type, confidence DESC"
        
        return self.db.execute_query(query, tuple(params), fetch=True)
    
    def get_blocked_files(self) -> List[Dict]:
        """获取所有被blocked的文件"""
        query = """
            SELECT id, bucket_name, object_key, violation_type, confidence
            FROM image_scan_records
            WHERE blocked = 1
            ORDER BY updated_at DESC
        """
        return self.db.execute_query(query, fetch=True)
    
    def block_violations(self, violations: List[Dict], dry_run: bool = False) -> Dict:
        """
        将违规图片标记为blocked（通过MinIO标签）
        
        Args:
            violations: 违规图片列表
            dry_run: 是否仅预览不执行
            
        Returns:
            操作统计
        """
        stats = {'success': 0, 'failed': 0, 'skipped': 0}
        
        logger.info("="*80)
        logger.info("开始标记违规图片为blocked状态")
        logger.info(f"  - 待处理数量: {len(violations)}")
        logger.info(f"  - Dry Run: {dry_run}")
        logger.info("="*80)
        
        if dry_run:
            logger.warning("⚠️ [DRY RUN] 仅预览，不会实际执行")
        
        for i, v in enumerate(violations, 1):
            object_key = v['object_key']
            bucket = v['bucket_name']
            
            try:
                logger.info(f"[{i}/{len(violations)}] 处理: {object_key}")
                
                # 检查当前状态
                acl_info = self.minio.get_object_acl(bucket, object_key)
                
                if acl_info.get('is_blocked'):
                    logger.debug(f"  ✓ 已标记，跳过")
                    stats['skipped'] += 1
                    continue
                
                if not dry_run:
                    # ✅ 事务保护：先设置 MinIO 标签，再更新数据库
                    try:
                        # 设置对象为blocked状态
                        self.minio.set_object_blocked(bucket, object_key, is_blocked=True)
                        
                        # 更新数据库记录
                        self.db.execute_query(
                            "UPDATE image_scan_records SET blocked = 1, updated_at = NOW() WHERE id = %s",
                            (v['id'],)
                        )
                        self.db.connection.commit()
                        
                    except Exception as e:
                        # ✅ 如果数据库更新失败，回滚 MinIO 操作
                        logger.error(f"    ✗ 数据库更新失败，尝试回滚 MinIO 操作...")
                        try:
                            self.minio.set_object_blocked(bucket, object_key, is_blocked=False)
                        except:
                            logger.error(f"    ✗ MinIO 回滚失败，需要手动处理")
                        raise  # 重新抛出异常
                
                stats['success'] += 1
                logger.info(f"[{i}/{len(violations)}] ✓ {object_key} -> BLOCKED")
                logger.debug(f"  - 违规类型: {v.get('violation_type')}")
                logger.debug(f"  - 置信度: {v.get('confidence')}")
                
            except Exception as e:
                stats['failed'] += 1
                logger.error(f"[{i}/{len(violations)}] ✗ {object_key} - 操作失败")
                logger.error(f"  - 错误类型: {type(e).__name__}")
                logger.error(f"  - 错误信息: {str(e)}")
                logger.exception("  - 详细堆栈:")
        
        return stats
    
    def restore_blocked(self, blocked_files: List[Dict], dry_run: bool = False) -> Dict:
        """
        恢复被block的图片（移除blocked标签）
        
        Args:
            blocked_files: 被block的文件列表
            dry_run: 是否仅预览不执行
            
        Returns:
            操作统计
        """
        stats = {'success': 0, 'failed': 0, 'skipped': 0}
        
        logger.info(f"开始恢复 {len(blocked_files)} 张被block的图片")
        if dry_run:
            logger.warning("[DRY RUN] 仅预览，不会实际执行")
        
        for i, f in enumerate(blocked_files, 1):
            object_key = f['object_key']
            bucket = f['bucket_name']
            
            try:
                # ✅ 恢复前检查 MinIO 状态
                acl_info = self.minio.get_object_acl(bucket, object_key)
                
                if not acl_info.get('is_blocked'):
                    logger.warning(f"[{i}/{len(blocked_files)}] ⚠️ {object_key} - 文件未被标记为blocked，跳过恢复")
                    stats['skipped'] += 1
                    continue
                
                if not dry_run:
                    # ✅ 事务保护：先恢复 MinIO 标签，再更新数据库
                    try:
                        # 恢复对象为正常状态
                        self.minio.set_object_blocked(bucket, object_key, is_blocked=False)
                        
                        # 更新数据库记录（只清除blocked标记，保留违规状态）
                        self.db.execute_query(
                            "UPDATE image_scan_records SET blocked = 0, updated_at = NOW() WHERE id = %s",
                            (f['id'],)
                        )
                        self.db.connection.commit()
                        
                    except Exception as e:
                        # ✅ 如果数据库更新失败，回滚 MinIO 操作
                        logger.error(f"    ✗ 数据库更新失败，尝试回滚 MinIO 操作...")
                        try:
                            self.minio.set_object_blocked(bucket, object_key, is_blocked=True)
                        except:
                            logger.error(f"    ✗ MinIO 回滚失败，需要手动处理")
                        raise  # 重新抛出异常
                
                stats['success'] += 1
                logger.info(f"[{i}/{len(blocked_files)}] ✓ {object_key} -> RESTORED")
                
            except Exception as e:
                stats['failed'] += 1
                logger.error(f"[{i}/{len(blocked_files)}] ✗ {object_key} - {str(e)}")
        
        return stats
    
    def delete_blocked(self, blocked_files: List[Dict], dry_run: bool = False) -> Dict:
        """
        彻底删除被block的图片
        
        Args:
            blocked_files: 被block的文件列表
            dry_run: 是否仅预览不执行
            
        Returns:
            操作统计
        """
        stats = {'success': 0, 'failed': 0}
        
        logger.warning(f"准备彻底删除 {len(blocked_files)} 张被block的图片（不可恢复！）")
        if dry_run:
            logger.warning("[DRY RUN] 仅预览，不会实际执行")
        
        for i, f in enumerate(blocked_files, 1):
            object_key = f['object_key']
            bucket = f['bucket_name']
            
            try:
                # ✅ 删除前再次检查 MinIO 状态
                acl_info = self.minio.get_object_acl(bucket, object_key)
                
                if not acl_info.get('is_blocked'):
                    logger.warning(f"[{i}/{len(blocked_files)}] ⚠️ {object_key} - 文件未被标记为blocked，跳过删除")
                    stats['failed'] += 1
                    continue
                
                if not dry_run:
                    # ✅ 事务保护：先删除 MinIO 文件，再删除数据库记录
                    try:
                        # 从MinIO删除文件
                        self.minio.remove_object(bucket, object_key)
                        
                        # 从数据库删除记录
                        self.db.execute_query(
                            "DELETE FROM image_scan_records WHERE id = %s",
                            (f['id'],)
                        )
                        self.db.connection.commit()
                        
                    except Exception as e:
                        # ✅ 如果数据库删除失败，无法回滚（文件已删除）
                        logger.error(f"    ✗ 数据库删除失败，MinIO文件已删除，需要手动处理")
                        raise  # 重新抛出异常
                
                stats['success'] += 1
                logger.info(f"[{i}/{len(blocked_files)}] ✓ 已删除: {object_key}")
                
            except Exception as e:
                stats['failed'] += 1
                logger.error(f"[{i}/{len(blocked_files)}] ✗ {object_key} - {str(e)}")
        
        return stats
    
    def preview_violations(self, violations: List[Dict]):
        """预览违规图片列表"""
        if not violations:
            print("没有找到符合条件的违规图片")
            return
        
        print(f"\n找到 {len(violations)} 张违规图片:\n")
        print(f"{'ID':<6} {'类型':<12} {'置信度':<8} {'文件路径'}")
        print("-" * 80)
        
        for v in violations[:50]:  # 最多显示50条
            print(f"{v['id']:<6} {v['violation_type']:<12} "
                  f"{v['confidence']:<8.2f} {v['bucket_name']}/{v['object_key']}")
        
        if len(violations) > 50:
            print(f"... 还有 {len(violations) - 50} 条未显示")
        
        print()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='违规图片处理工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 预览所有违规图片
  python handle_violations.py list
  
  # 预览赌博类违规图片
  python handle_violations.py list --type gambling
  
  # 标记违规图片为blocked（预览模式）
  python handle_violations.py block --dry-run
  
  # 标记所有赌博类违规图片为blocked
  python handle_violations.py block --type gambling
  
  # 查看已被blocked的文件
  python handle_violations.py list-blocked
  
  # 恢复被blocked的文件（预览模式）
  python handle_violations.py restore --dry-run
  
  # 恢复指定的被blocked文件
  python handle_violations.py restore --ids 1,2,3
  
  # 彻底删除所有被blocked的文件（危险操作！）
  python handle_violations.py delete-blocked
  
  # 彻底删除指定的被blocked文件
  python handle_violations.py delete-blocked --ids 1,2,3
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # list 命令
    list_parser = subparsers.add_parser('list', help='列出违规图片')
    list_parser.add_argument('--type', help='违规类型过滤')
    list_parser.add_argument('--confidence', type=float, default=0.0, help='置信度阈值')
    
    # block 命令（替代rename）
    block_parser = subparsers.add_parser('block', help='标记违规图片为blocked状态')
    block_parser.add_argument('--type', help='违规类型过滤')
    block_parser.add_argument('--confidence', type=float, default=0.0, help='置信度阈值')
    block_parser.add_argument('--dry-run', action='store_true', help='仅预览不执行')
    
    # list-blocked 命令（替代list-del）
    list_blocked_parser = subparsers.add_parser('list-blocked', help='列出已被blocked的文件')
    
    # restore 命令
    restore_parser = subparsers.add_parser('restore', help='恢复被blocked的文件')
    restore_parser.add_argument('--ids', help='要恢复的记录ID，逗号分隔')
    restore_parser.add_argument('--dry-run', action='store_true', help='仅预览不执行')
    
    # delete-blocked 命令（替代delete-del）
    delete_parser = subparsers.add_parser('delete-blocked', help='彻底删除被blocked的文件')
    delete_parser.add_argument('--ids', help='要删除的记录ID，逗号分隔')
    delete_parser.add_argument('--dry-run', action='store_true', help='仅预览不执行')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    handler = ViolationHandler()
    
    try:
        if args.command == 'list':
            violations = handler.get_violations(
                violation_type=args.type,
                confidence_threshold=args.confidence
            )
            handler.preview_violations(violations)
        
        elif args.command == 'block':
            violations = handler.get_violations(
                violation_type=args.type,
                confidence_threshold=args.confidence
            )
            
            if not violations:
                print("没有找到符合条件的违规图片")
                return
            
            handler.preview_violations(violations)
            
            if args.dry_run:
                print("\n[DRY RUN MODE] 以上为预览，未实际执行\n")
                return
            
            # 确认操作
            confirm = input(f"确认标记 {len(violations)} 张图片为blocked状态？(yes/no): ")
            if confirm.lower() != 'yes':
                print("已取消")
                return
            
            stats = handler.block_violations(violations, dry_run=False)
            print(f"\n标记完成:")
            print(f"  成功: {stats['success']}")
            print(f"  失败: {stats['failed']}")
            print(f"  跳过: {stats['skipped']}")
        
        elif args.command == 'list-blocked':
            blocked_files = handler.get_blocked_files()
            
            if not blocked_files:
                print("没有被blocked的文件")
                return
            
            print(f"\n找到 {len(blocked_files)} 个被blocked的文件:\n")
            print(f"{'ID':<6} {'类型':<12} {'置信度':<8} {'文件路径'}")
            print("-" * 80)
            
            for f in blocked_files:
                print(f"{f['id']:<6} {f['violation_type']:<12} "
                      f"{f['confidence']:<8.2f} {f['bucket_name']}/{f['object_key']}")
            
            print()
        
        elif args.command == 'restore':
            if args.ids:
                ids = [int(x.strip()) for x in args.ids.split(',')]
                placeholders = ','.join(['%s'] * len(ids))
                query = f"""
                    SELECT id, bucket_name, object_key, violation_type, confidence
                    FROM image_scan_records
                    WHERE id IN ({placeholders}) AND blocked = 1
                """
                blocked_files = handler.db.execute_query(query, tuple(ids), fetch=True)
            else:
                blocked_files = handler.get_blocked_files()
            
            if not blocked_files:
                print("没有找到符合条件的被blocked文件")
                return
            
            print(f"\n准备恢复 {len(blocked_files)} 个被blocked的文件:\n")
            for f in blocked_files:
                print(f"  {f['bucket_name']}/{f['object_key']}")
            print()
            
            if args.dry_run:
                print("[DRY RUN MODE] 以上为预览，未实际执行\n")
                return
            
            # 确认操作
            confirm = input(f"确认恢复 {len(blocked_files)} 个文件？(yes/no): ")
            if confirm.lower() != 'yes':
                print("已取消")
                return
            
            stats = handler.restore_blocked(blocked_files, dry_run=False)
            print(f"\n恢复完成:")
            print(f"  成功: {stats['success']}")
            print(f"  失败: {stats['failed']}")
            print(f"  跳过: {stats['skipped']}")
        
        elif args.command == 'delete-blocked':
            if args.ids:
                ids = [int(x.strip()) for x in args.ids.split(',')]
                placeholders = ','.join(['%s'] * len(ids))
                query = f"""
                    SELECT id, bucket_name, object_key, violation_type, confidence
                    FROM image_scan_records
                    WHERE id IN ({placeholders}) AND blocked = 1
                """
                blocked_files = handler.db.execute_query(query, tuple(ids), fetch=True)
            else:
                blocked_files = handler.get_blocked_files()
            
            if not blocked_files:
                print("没有找到符合条件的被blocked文件")
                return
            
            print(f"\n⚠️  警告：即将彻底删除 {len(blocked_files)} 个被blocked的文件（不可恢复！）\n")
            for f in blocked_files:
                print(f"  {f['bucket_name']}/{f['object_key']}")
            print()
            
            if args.dry_run:
                print("[DRY RUN MODE] 以上为预览，未实际执行\n")
                return
            
            # 二次确认
            confirm = input("输入 DELETE 确认彻底删除: ")
            if confirm != 'DELETE':
                print("已取消")
                return
            
            stats = handler.delete_blocked(blocked_files, dry_run=False)
            print(f"\n删除完成:")
            print(f"  成功: {stats['success']}")
            print(f"  失败: {stats['failed']}")
    
    except KeyboardInterrupt:
        print("\n操作已取消")
    except Exception as e:
        logger.error(f"操作失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        handler.db.close()


if __name__ == '__main__':
    main()

