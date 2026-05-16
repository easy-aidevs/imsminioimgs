-- 图片内容安全扫描系统数据库表结构

-- 图片扫描记录表
CREATE TABLE IF NOT EXISTS image_scan_records (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    
    -- 图片唯一标识（注意：同一张图片可能有多个路径，所以不加UNIQUE约束）
    `key` VARCHAR(128) NOT NULL COMMENT '图片唯一标识: md5(文件内容)-文件大小',
    
    -- 图片特征码（用于相似图片识别）
    feature_hash VARCHAR(64) NOT NULL COMMENT '图片感知哈希特征码',
    feature_hash_dhash VARCHAR(64) DEFAULT NULL COMMENT '差异哈希特征码',
    feature_hash_ahash VARCHAR(64) DEFAULT NULL COMMENT '平均哈希特征码',
    feature_hash_phash VARCHAR(64) DEFAULT NULL COMMENT '感知哈希特征码',
    
    -- MinIO存储信息
    bucket_name VARCHAR(255) NOT NULL COMMENT 'MinIO存储桶名称',
    object_key VARCHAR(1024) NOT NULL COMMENT 'MinIO对象路径',
    file_size BIGINT NOT NULL COMMENT '文件大小(字节)',
    content_type VARCHAR(128) DEFAULT NULL COMMENT 'MIME类型',
    
    -- 扫描结果
    is_violation TINYINT(1) DEFAULT 0 COMMENT '是否违规: 0-否, 1-是',
    violation_type VARCHAR(255) DEFAULT NULL COMMENT '违规类型: gambling(赌博)/porn(色情)/violence(暴力)/politics(政治)/ads(广告)/terrorism(恐怖主义)/contraband(违禁品)/vulgar(低俗)/other(其他)',
    violation_label VARCHAR(255) DEFAULT NULL COMMENT '违规标签: 具体细分类型',
    violation_description TEXT DEFAULT NULL COMMENT '违规描述: 详细说明',
    confidence DECIMAL(5,4) DEFAULT NULL COMMENT '置信度: 0.0000-1.0000',
    suggestion VARCHAR(50) DEFAULT NULL COMMENT '建议操作: Block(屏蔽)/Review(人工审核)/Pass(通过)',
    
    -- 腾讯云IMS返回的原始数据
    ims_result JSON DEFAULT NULL COMMENT '腾讯云IMS完整返回结果(JSON格式)',
    ims_request_id VARCHAR(128) DEFAULT NULL COMMENT '腾讯云IMS请求ID',
    
    -- 扫描状态
    scan_status VARCHAR(20) DEFAULT 'pending' COMMENT '扫描状态: pending(待扫描)/scanning(扫描中)/completed(已完成)/failed(失败)',
    error_message TEXT DEFAULT NULL COMMENT '错误信息',
    
    -- 对象访问控制
    blocked TINYINT(1) DEFAULT 0 COMMENT '是否被block: 0-正常, 1-已block（通过MinIO标签标记）',
    
    -- 时间戳
    first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '首次发现时间',
    last_scanned_at DATETIME DEFAULT NULL COMMENT '最后扫描时间',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    
    -- 索引
    INDEX idx_key (`key`),  -- 用于查找相同图片的所有路径
    INDEX idx_feature_hash (feature_hash),
    INDEX idx_feature_dhash (feature_hash_dhash),
    INDEX idx_bucket_object (bucket_name, object_key(255)),
    INDEX idx_is_violation (is_violation),
    INDEX idx_blocked (blocked),  -- 用于查询被block的文件
    INDEX idx_violation_type (violation_type),
    INDEX idx_scan_status (scan_status),
    INDEX idx_created_at (created_at),
    INDEX idx_last_scanned_at (last_scanned_at)
    
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='图片内容安全扫描记录表';

-- 相似图片关联表（可选，用于快速查找相似图片）
CREATE TABLE IF NOT EXISTS similar_images (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    source_image_key VARCHAR(128) NOT NULL COMMENT '源图片key',
    similar_image_key VARCHAR(128) NOT NULL COMMENT '相似图片key',
    similarity_score DECIMAL(5,4) NOT NULL COMMENT '相似度分数: 0.0000-1.0000',
    hash_distance INT NOT NULL COMMENT '哈希距离',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    INDEX idx_source_image (source_image_key),
    INDEX idx_similar_image (similar_image_key),
    UNIQUE KEY uk_source_similar (source_image_key, similar_image_key)
    
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='相似图片关联表';

-- 扫描统计汇总表
CREATE TABLE IF NOT EXISTS scan_statistics (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    stat_date DATE NOT NULL COMMENT '统计日期',
    bucket_name VARCHAR(255) DEFAULT NULL COMMENT '存储桶名称(NULL表示全部)',
    total_scanned INT DEFAULT 0 COMMENT '总扫描数',
    total_violations INT DEFAULT 0 COMMENT '违规总数',
    violation_by_type JSON DEFAULT NULL COMMENT '各违规类型统计: {"gambling": 10, "porn": 5, ...}',
    avg_confidence DECIMAL(5,4) DEFAULT NULL COMMENT '平均置信度',
    scan_duration_seconds INT DEFAULT NULL COMMENT '扫描耗时(秒)',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    UNIQUE KEY uk_date_bucket (stat_date, bucket_name),
    INDEX idx_stat_date (stat_date)
    
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='扫描统计汇总表';
