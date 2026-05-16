#!/usr/bin/env python3
"""
违规图片处理工具
支持重命名、恢复和彻底删除违规图片

工作流程：
1. 扫描并标记违规图片
2. 重命名违规图片为 .__del__ 后缀（可恢复）
3. 确认无误后，彻底删除 .__del__ 文件
4. 如有误判，可恢复文件
"""

import os
import sys
import argparse
from datetime import datetime
from typing import List, Dict
from dotenv import load_dotenv
from loguru import logger

# 加载环境变量
load_dotenv()

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
        
        logger.info("违规图片处理器初始化完成")
    
    def get_violations(self, violation_type: str = None, 
                      confidence_threshold: float = 0.0,
                      exclude_del: bool = True) -> List[Dict]:
        """获取违规图片列表"""
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
        
        if exclude_del:
            query += " AND object_key NOT LIKE '%.__del__%'"
        
        query += " ORDER BY violation_type, confidence DESC"
        
        return self.db.execute_query(query, tuple(params), fetch=True)
    
    def get_del_files(self) -> List[Dict]:
        """获取所有已标记为.__del__的文件"""
        query = """
            SELECT id, bucket_name, object_key, violation_type, confidence
            FROM image_scan_records
            WHERE object_key LIKE '%.__del__%'
            ORDER BY updated_at DESC
        """
        return self.db.execute_query(query, fetch=True)
    
    def rename_to_del(self, violations: List[Dict], dry_run: bool = False) -> Dict:
        """将违规图片重命名为 .__del__ 后缀"""
        stats = {'success': 0, 'failed': 0, 'skipped': 0}
        
        logger.info(f"开始重命名 {len(violations)} 张图片为 .__del__ 后缀")
        if dry_run:
            logger.warning("[DRY RUN] 仅预览，不会实际执行")
        
        for i, v in enumerate(violations, 1):
            old_key = v['object_key']
            bucket = v['bucket_name']
            
            # 生成新文件名
            if old_key.endswith('.__del__'):
                logger.debug(f"跳过已标记的文件: {old_key}")
                stats['skipped'] += 1
                continue
            
            new_key = old_key + '.__del__'
            
            try:
                if not dry_run:
                    # 1. 复制文件到新名称
                    data = self.minio.get_object_data(bucket, old_key)
                    self.minio.upload_object(bucket, new_key, data)
                    
                    # 2. 删除原文件
                    self.minio.remove_object(bucket, old_key)
                    
                    # 3. 更新数据库记录
                    self.db.execute_query(
                        "UPDATE image_scan_records SET object_key = %s, updated_at = NOW() WHERE id = %s",
                        (new_key, v['id'])
                    )
                    self.db.connection.commit()
                
                stats['success'] += 1
                logger.info(f"[{i}/{len(violations)}] ✓ {old_key} → {new_key}")
                
            except Exception as e:
                stats['failed'] += 1
                logger.error(f"[{i}/{len(violations)}] ✗ {old_key} - {str(e)}")
        
        return stats
    
    def restore_from_del(self, del_files: List[Dict], dry_run: bool = False) -> Dict:
        """恢复 .__del__ 文件到原始名称"""
        stats = {'success': 0, 'failed': 0, 'skipped': 0}
        
        logger.info(f"开始恢复 {len(del_files)} 张 .__del__ 文件")
        if dry_run:
            logger.warning("[DRY RUN] 仅预览，不会实际执行")
        
        for i, f in enumerate(del_files, 1):
            del_key = f['object_key']
            bucket = f['bucket_name']
            
            # 恢复原始文件名
            if not del_key.endswith('.__del__'):
                logger.debug(f"跳过非.__del__文件: {del_key}")
                stats['skipped'] += 1
                continue
            
            original_key = del_key[:-8]  # 移除 .__del__
            
            try:
                if not dry_run:
                    # 1. 复制文件回原始名称
                    data = self.minio.get_object_data(bucket, del_key)
                    self.minio.upload_object(bucket, original_key, data)
                    
                    # 2. 删除.__del__文件
                    self.minio.remove_object(bucket, del_key)
                    
                    # 3. 更新数据库记录
                    self.db.execute_query(
                        "UPDATE image_scan_records SET object_key = %s, is_violation = 0, updated_at = NOW() WHERE id = %s",
                        (original_key, f['id'])
                    )
                    self.db.connection.commit()
                
                stats['success'] += 1
                logger.info(f"[{i}/{len(del_files)}] ✓ {del_key} → {original_key}")
                
            except Exception as e:
                stats['failed'] += 1
                logger.error(f"[{i}/{len(del_files)}] ✗ {del_key} - {str(e)}")
        
        return stats
    
    def delete_del_files(self, del_files: List[Dict], dry_run: bool = False) -> Dict:
        """彻底删除 .__del__ 文件"""
        stats = {'success': 0, 'failed': 0}
        
        logger.warning(f"准备彻底删除 {len(del_files)} 张 .__del__ 文件（不可恢复！）")
        if dry_run:
            logger.warning("[DRY RUN] 仅预览，不会实际执行")
        
        for i, f in enumerate(del_files, 1):
            del_key = f['object_key']
            bucket = f['bucket_name']
            
            try:
                if not dry_run:
                    # 1. 从MinIO删除文件
                    self.minio.remove_object(bucket, del_key)
                    
                    # 2. 从数据库删除记录
                    self.db.execute_query(
                        "DELETE FROM image_scan_records WHERE id = %s",
                        (f['id'],)
                    )
                    self.db.connection.commit()
                
                stats['success'] += 1
                logger.info(f"[{i}/{len(del_files)}] ✓ 已删除: {del_key}")
                
            except Exception as e:
                stats['failed'] += 1
                logger.error(f"[{i}/{len(del_files)}] ✗ {del_key} - {str(e)}")
        
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
  
  # 重命名违规图片为.__del__（预览模式）
  python handle_violations.py rename --dry-run
  
  # 重命名所有赌博类违规图片
  python handle_violations.py rename --type gambling
  
  # 查看已标记为.__del__的文件
  python handle_violations.py list-del
  
  # 恢复所有.__del__文件（预览模式）
  python handle_violations.py restore --dry-run
  
  # 恢复指定的.__del__文件
  python handle_violations.py restore --ids 1,2,3
  
  # 彻底删除所有.__del__文件（危险操作！）
  python handle_violations.py delete-del
  
  # 彻底删除指定的.__del__文件
  python handle_violations.py delete-del --ids 1,2,3
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # list 命令
    list_parser = subparsers.add_parser('list', help='列出违规图片')
    list_parser.add_argument('--type', help='违规类型过滤')
    list_parser.add_argument('--confidence', type=float, default=0.0, help='置信度阈值')
    
    # rename 命令
    rename_parser = subparsers.add_parser('rename', help='重命名违规图片为.__del__')
    rename_parser.add_argument('--type', help='违规类型过滤')
    rename_parser.add_argument('--confidence', type=float, default=0.0, help='置信度阈值')
    rename_parser.add_argument('--dry-run', action='store_true', help='仅预览不执行')
    
    # list-del 命令
    list_del_parser = subparsers.add_parser('list-del', help='列出已标记为.__del__的文件')
    
    # restore 命令
    restore_parser = subparsers.add_parser('restore', help='恢复.__del__文件')
    restore_parser.add_argument('--ids', help='要恢复的记录ID，逗号分隔')
    restore_parser.add_argument('--dry-run', action='store_true', help='仅预览不执行')
    
    # delete-del 命令
    delete_parser = subparsers.add_parser('delete-del', help='彻底删除.__del__文件')
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
        
        elif args.command == 'rename':
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
            confirm = input(f"确认重命名 {len(violations)} 张图片为 .__del__？(yes/no): ")
            if confirm.lower() != 'yes':
                print("已取消")
                return
            
            stats = handler.rename_to_del(violations, dry_run=False)
            print(f"\n重命名完成:")
            print(f"  成功: {stats['success']}")
            print(f"  失败: {stats['failed']}")
            print(f"  跳过: {stats['skipped']}")
        
        elif args.command == 'list-del':
            del_files = handler.get_del_files()
            
            if not del_files:
                print("没有找到 .__del__ 文件")
                return
            
            print(f"\n找到 {len(del_files)} 个 .__del__ 文件:\n")
            print(f"{'ID':<6} {'类型':<12} {'置信度':<8} {'文件路径'}")
            print("-" * 80)
            
            for f in del_files:
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
                    WHERE id IN ({placeholders}) AND object_key LIKE '%.__del__%'
                """
                del_files = handler.db.execute_query(query, tuple(ids), fetch=True)
            else:
                del_files = handler.get_del_files()
            
            if not del_files:
                print("没有找到符合条件的 .__del__ 文件")
                return
            
            print(f"\n准备恢复 {len(del_files)} 个文件:\n")
            for f in del_files:
                original = f['object_key'][:-8]
                print(f"  {f['object_key']} → {original}")
            print()
            
            if args.dry_run:
                print("[DRY RUN MODE] 以上为预览，未实际执行\n")
                return
            
            # 确认操作
            confirm = input(f"确认恢复 {len(del_files)} 个文件？(yes/no): ")
            if confirm.lower() != 'yes':
                print("已取消")
                return
            
            stats = handler.restore_from_del(del_files, dry_run=False)
            print(f"\n恢复完成:")
            print(f"  成功: {stats['success']}")
            print(f"  失败: {stats['failed']}")
            print(f"  跳过: {stats['skipped']}")
        
        elif args.command == 'delete-del':
            if args.ids:
                ids = [int(x.strip()) for x in args.ids.split(',')]
                placeholders = ','.join(['%s'] * len(ids))
                query = f"""
                    SELECT id, bucket_name, object_key, violation_type, confidence
                    FROM image_scan_records
                    WHERE id IN ({placeholders}) AND object_key LIKE '%.__del__%'
                """
                del_files = handler.db.execute_query(query, tuple(ids), fetch=True)
            else:
                del_files = handler.get_del_files()
            
            if not del_files:
                print("没有找到符合条件的 .__del__ 文件")
                return
            
            print(f"\n⚠️  警告：即将彻底删除 {len(del_files)} 个文件（不可恢复！）\n")
            for f in del_files:
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
            
            stats = handler.delete_del_files(del_files, dry_run=False)
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

