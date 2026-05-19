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
    
    -- 对象访问控制（三阶段处置状态）
    blocked TINYINT(1) DEFAULT 0 COMMENT '处置状态: 0-public(未处理), 1-private(隐藏观察期), 2-quarantined(已隔离)',
    
    -- 时间戳
    first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '首次发现时间',
    last_scanned_at DATETIME DEFAULT NULL COMMENT '最后扫描时间',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    
    -- 索引
    UNIQUE KEY uk_bucket_object (bucket_name, object_key(255)),  -- ✅ 唯一约束：同一MinIO路径只有一条记录
    INDEX idx_key (`key`),  -- 用于查找相同图片的不同路径
    INDEX idx_feature_hash (feature_hash),
    INDEX idx_feature_dhash (feature_hash_dhash),
    INDEX idx_is_violation (is_violation),
    INDEX idx_blocked (blocked),  -- 用于查询被block的文件
    INDEX idx_violation_type (violation_type),
    INDEX idx_scan_status (scan_status),
    INDEX idx_created_at (created_at),
    INDEX idx_last_scanned_at (last_scanned_at)
    
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='图片内容安全扫描记录表';
