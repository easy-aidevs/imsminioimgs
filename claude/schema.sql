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
    violation_type VARCHAR(255) DEFAULT NULL COMMENT '违规类型：直接取 IMS SubLabel（如 Gambling/SexyBehavior/NationalOfficial），无 SubLabel 时取 Label（如 Porn/Terror/Polity）',
    violation_label VARCHAR(128) DEFAULT NULL COMMENT '腾讯IMS一级标签(Label): Polity/Porn/Sexy/Terror/Illegal/Ad/Teenager/Abuse/...',
    violation_label_cn VARCHAR(64) DEFAULT NULL COMMENT '一级标签中文名: 政治/色情/性感/暴恐/违法/广告/未成年识别/...',
    sub_label VARCHAR(128) DEFAULT NULL COMMENT '腾讯IMS二级标签(SubLabel): NationalOfficial/Gambling/SexyBehavior/...',
    sub_label_cn VARCHAR(128) DEFAULT NULL COMMENT '二级标签中文名: 国部级领导人/赌博/性行为画面/...',
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
    quarantine_batch_id VARCHAR(64) DEFAULT NULL COMMENT '隔离批次ID：quarantine 命令写入，支持手动指定（如 gamble_wave1）或自动生成（YYYYMMDD_HHMMSS）；同一批次ID可跨多次 quarantine 操作累积，便于整批还原',
    
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
    INDEX idx_quarantine_batch_id (quarantine_batch_id),  -- 用于按批次查询/还原
    INDEX idx_violation_type (violation_type),
    INDEX idx_scan_status (scan_status),
    INDEX idx_created_at (created_at),
    INDEX idx_last_scanned_at (last_scanned_at),

    -- 复合索引：handle_violations 游标分页专用（百万数据下避免全表扫描）
    -- _fetch_quarantined_page: WHERE blocked=2 AND id>? ORDER BY id ASC
    INDEX idx_blocked_id (blocked, id),
    -- _fetch_violations_page: WHERE is_violation=1 AND blocked IN(0,1) AND id>? ORDER BY id ASC
    INDEX idx_violation_blocked_id (is_violation, blocked, id),
    -- find_similar_scanned: WHERE scan_status='completed' ORDER BY created_at DESC LIMIT 2000
    INDEX idx_scan_status_created (scan_status, created_at)
    
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='图片内容安全扫描记录表';
