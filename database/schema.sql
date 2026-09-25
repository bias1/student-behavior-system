-- =============================================================================
--  高校学生行为数据采集与可视化系统 —— 数据库表结构设计
--  DB      : MySQL 8.0+ (兼容 5.7，去掉 JSON 类型即可)
--  Engine  : InnoDB      Charset: utf8mb4 / utf8mb4_general_ci
--  说明    : 全部为 faker + numpy 生成的模拟数据，不含任何真实隐私数据
--  执行    : mysql -u root -p < database/schema.sql
-- =============================================================================

CREATE DATABASE IF NOT EXISTS student_behavior
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_general_ci;

USE student_behavior;

-- 重建表时先关闭外键检查，保证 DROP 顺序无关
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS warning;
DROP TABLE IF EXISTS warning_rule;
DROP TABLE IF EXISTS library_record;
DROP TABLE IF EXISTS consumption;
DROP TABLE IF EXISTS student;

-- =============================================================================
-- 1. student —— 学生基础信息表（维度表 / 主表，1 个学生 : N 条行为记录）
-- =============================================================================
CREATE TABLE student
(
    student_id      VARCHAR(20)  NOT NULL COMMENT '学号，业务主键，贯穿全库的关联键',
    name            VARCHAR(50)  NOT NULL COMMENT '姓名（faker 生成的模拟姓名）',
    gender          TINYINT      NOT NULL DEFAULT 0 COMMENT '性别：0-未知 1-男 2-女',
    birth_year      SMALLINT              DEFAULT NULL COMMENT '出生年份，用于计算年龄',
    college         VARCHAR(50)  NOT NULL COMMENT '学院，群体概览分组维度',
    major           VARCHAR(50)  NOT NULL COMMENT '专业',
    class_name      VARCHAR(50)           DEFAULT NULL COMMENT '班级',
    grade_year      SMALLINT     NOT NULL COMMENT '入学年份/年级，如 2022',
    dorm_building   VARCHAR(50)           DEFAULT NULL COMMENT '宿舍楼，用于分析宿舍-食堂-图书馆动线',
    card_no         VARCHAR(32)           DEFAULT NULL COMMENT '校园一卡通号（模拟）',
    enroll_status   TINYINT      NOT NULL DEFAULT 1 COMMENT '在校状态：0-离校 1-在校 2-休学',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (student_id),
    KEY idx_student_college_grade (college, grade_year) COMMENT '群体大屏按学院+年级分组统计',
    KEY idx_student_major (major) COMMENT '按专业维度下钻',
    KEY idx_student_name (name) COMMENT '个体画像页按姓名模糊检索前缀匹配'
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4 COMMENT ='学生基础信息表';

-- =============================================================================
-- 2. consumption —— 消费记录表（事实表，数据量最大）
--    一笔消费 = 一条刷卡流水，来源于食堂 / 超市 / 浴室等场景
-- =============================================================================
CREATE TABLE consumption
(
    id              BIGINT       NOT NULL AUTO_INCREMENT COMMENT '自增主键，避免大批量写入的行锁竞争',
    student_id      VARCHAR(20)  NOT NULL COMMENT '学号，关联 student.student_id',
    merchant_type   TINYINT      NOT NULL DEFAULT 1 COMMENT '消费场景：1-食堂 2-超市 3-浴室 4-机房 5-其他',
    merchant_name   VARCHAR(80)  NOT NULL COMMENT '商户/窗口名称，如“第一食堂三楼窗口5”',
    amount          DECIMAL(10, 2) NOT NULL COMMENT '消费金额（元），DECIMAL 避免浮点误差',
    balance         DECIMAL(10, 2)          DEFAULT NULL COMMENT '消费后卡内余额（元），可用于“余额不足仍消费”类预警',
    terminal_id     VARCHAR(32)           DEFAULT NULL COMMENT '机具编号，模拟数据来源设备',
    consumed_at     DATETIME     NOT NULL COMMENT '消费发生时间，热力分析与高峰识别的核心字段',
    meal_period     VARCHAR(10)  GENERATED ALWAYS AS (
                        CASE
                            WHEN merchant_type <> 1     THEN '非正餐'
                            WHEN HOUR(consumed_at) BETWEEN 6  AND 9   THEN '早餐'
                            WHEN HOUR(consumed_at) BETWEEN 10 AND 13  THEN '午餐'
                            WHEN HOUR(consumed_at) BETWEEN 14 AND 15  THEN '下午'
                            WHEN HOUR(consumed_at) BETWEEN 16 AND 20  THEN '晚餐'
                            ELSE '深夜'
                        END
                    ) STORED COMMENT '餐段（生成列，仅对食堂流水(mtype=1)判餐段，超市/夜宵归入非正餐，避免污染三餐分析）。注：晚餐下界定为 16 点，因数据生成器晚餐时段裁剪下界为 16:30（提早开饭），旧版 17 点会把这批流水错分到“下午”、导致三餐规律性统计漏算晚餐',
    is_valid        TINYINT      NOT NULL DEFAULT 1 COMMENT '清洗标记：0-无效(重复/金额为负/脏数据) 1-有效',
    batch_no        VARCHAR(40)           DEFAULT NULL COMMENT '导入批次号，便于数据生成模块做幂等重跑与回滚',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '入库时间',
    PRIMARY KEY (id),
    KEY idx_cons_student_time (student_id, consumed_at) COMMENT '个体画像：查某学生某时间段流水（联合索引同时服务外键）',
    KEY idx_cons_time (consumed_at) COMMENT '群体统计/热力图：按时间范围全表扫描排序',
    KEY idx_cons_type_time (merchant_type, consumed_at) COMMENT '按消费场景分组的高峰/金额统计',
    KEY idx_cons_batch (batch_no) COMMENT '按批次清洗、校验、回滚',
    -- 学生删除时级联清理其行为数据（ON DELETE CASCADE）
    CONSTRAINT fk_cons_student FOREIGN KEY (student_id) REFERENCES student (student_id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4 COMMENT ='消费记录表（模拟一卡通流水）';

-- =============================================================================
-- 3. library_record —— 图书馆进出记录表（事实表）
--    一条记录 = 一次完整进出（入馆 + 离馆），停留时长由生成列计算
-- =============================================================================
CREATE TABLE library_record
(
    id              BIGINT       NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    student_id      VARCHAR(20)  NOT NULL COMMENT '学号，关联 student.student_id',
    venue           VARCHAR(50)  NOT NULL DEFAULT '中心图书馆' COMMENT '馆舍/分馆名称',
    floor_no        TINYINT               DEFAULT NULL COMMENT '楼层',
    area_name       VARCHAR(50)           DEFAULT NULL COMMENT '区域，如“三号自习区”“报刊阅览室”',
    seat_no         VARCHAR(20)           DEFAULT NULL COMMENT '座位号（模拟，可选字段）',
    gate_in_time    DATETIME     NOT NULL COMMENT '入馆闸机时间',
    gate_out_time   DATETIME              DEFAULT NULL COMMENT '离馆闸机时间，NULL 表示仍在馆内',
    stay_minutes    INT          GENERATED ALWAYS AS (
                        CASE WHEN gate_out_time IS NULL THEN NULL
                             ELSE TIMESTAMPDIFF(MINUTE, gate_in_time, gate_out_time)
                        END
                    ) STORED COMMENT '停留时长（分钟，生成列自动计算，防止 ETL 遗漏）',
    in_meal_flag    TINYINT      NOT NULL DEFAULT 0 COMMENT '是否占座跨餐（离馆-入馆跨越饭点），辅助“不吃饭占座”预警',
    is_valid        TINYINT      NOT NULL DEFAULT 1 COMMENT '清洗标记：0-无效(离馆早于入馆/时长为负) 1-有效',
    batch_no        VARCHAR(40)           DEFAULT NULL COMMENT '导入批次号',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '入库时间',
    PRIMARY KEY (id),
    KEY idx_lib_student_time (student_id, gate_in_time) COMMENT '个体画像：某学生进馆频次/时长趋势',
    KEY idx_lib_in_time (gate_in_time) COMMENT '群体分析：按小时/星期的入馆分布热力图',
    KEY idx_lib_out_time (gate_out_time) COMMENT '统计在馆人数：gate_out_time IS NULL 或未离馆区间',
    KEY idx_lib_batch (batch_no) COMMENT '按批次清洗与回滚',
    CONSTRAINT fk_lib_student FOREIGN KEY (student_id) REFERENCES student (student_id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4 COMMENT ='图书馆进出记录表';

-- =============================================================================
-- 4. warning_rule —— 预警规则配置表（预警模块的阈值外置，避免硬编码）
-- =============================================================================
CREATE TABLE warning_rule
(
    id              INT          NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    rule_code       VARCHAR(40)  NOT NULL COMMENT '规则编码，唯一，如 HIGH_CONSUME / NIGHT_CONSUME / NO_LIBRARY',
    rule_name       VARCHAR(80)  NOT NULL COMMENT '规则名称，前端展示用',
    warning_type    VARCHAR(30)  NOT NULL COMMENT '预警大类：consume-消费类 / study-学习类 / health-生活规律类',
    threshold_value DECIMAL(12, 2)        DEFAULT NULL COMMENT '数值型阈值，如单日消费上限 300.00',
    threshold_json  JSON                  DEFAULT NULL COMMENT '复杂规则参数（时间段区间、连续天数、分位数等）',
    warning_level   TINYINT      NOT NULL DEFAULT 2 COMMENT '默认预警级别：1-低 2-中 3-高',
    enabled         TINYINT      NOT NULL DEFAULT 1 COMMENT '是否启用：0-停用 1-启用',
    description     VARCHAR(255)          DEFAULT NULL COMMENT '规则说明，论文与前端 tooltip 可直接引用',
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '规则更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_rule_code (rule_code)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4 COMMENT ='预警规则阈值配置表';

-- =============================================================================
-- 5. warning —— 预警记录表（规则引擎输出结果，供预警列表页展示与处置）
-- =============================================================================
CREATE TABLE warning
(
    id              BIGINT       NOT NULL AUTO_INCREMENT COMMENT '自增主键',
    student_id      VARCHAR(20)  NOT NULL COMMENT '学号，关联 student.student_id',
    rule_code       VARCHAR(40)  NOT NULL COMMENT '触发的规则编码，关联 warning_rule.rule_code',
    rule_name       VARCHAR(80)  NULL COMMENT '规则名称快照（触发时），事后改名不回溯历史预警',
    warning_type    VARCHAR(30)  NOT NULL COMMENT '预警大类：consume / study / health（冗余存储，便于列表筛选不回表）',
    warning_level   TINYINT      NOT NULL DEFAULT 2 COMMENT '预警级别：1-低 2-中 3-高',
    warning_date    DATE         NOT NULL COMMENT '业务日期（异常发生的日期，非入库时间）',
    metric_value    DECIMAL(12, 2)        DEFAULT NULL COMMENT '触发时的关键指标值，如当日消费总额 458.60',
    detail_json     JSON                  DEFAULT NULL COMMENT '证据快照：{日均值, 偏差率, 连续天数, 关联流水id...}，供个体画像页展示',
    message         VARCHAR(255) NOT NULL COMMENT '预警描述文案，直接用于前端列表',
    status          TINYINT      NOT NULL DEFAULT 0 COMMENT '处置状态：0-未处理 1-已处理 2-已忽略',
    handled_by      VARCHAR(50)           DEFAULT NULL COMMENT '处理人（辅导员/管理员，模拟）',
    handled_at      DATETIME              DEFAULT NULL COMMENT '处理时间',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '生成时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_warn_student_rule_date (student_id, rule_code, warning_date) COMMENT '幂等去重：同一学生同一规则同一天只保留一条，支持定时任务重复执行；其最左前缀同时服务于外键与“查某学生全部预警”',
    KEY idx_warn_status_level (status, warning_level, warning_date) COMMENT '预警列表页默认查询：按状态+级别筛选、按日期倒序分页',
    KEY idx_warn_type_date (warning_type, warning_date) COMMENT '群体大屏：按大类统计当日预警数',
    -- 外键列 student_id 已由 uk_warn_student_rule_date 最左前缀覆盖，无需重复建索引
    CONSTRAINT fk_warn_student FOREIGN KEY (student_id) REFERENCES student (student_id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4 COMMENT ='异常行为预警记录表';

-- 恢复外键检查
SET FOREIGN_KEY_CHECKS = 1;

-- =============================================================================
-- 初始化预警规则示例（与后续预警模块的规则编码严格对应）
-- 阈值取值依据：统计模拟数据的实际分布定阈，保证每条规则"可触发但不泛滥"——
--   距上一次进馆 >= 7 天的学生约 4 人；单日累计在馆 > 6 小时的人日约占 1.5%。
--   （旧值 30 天 / 12 小时在 30 天统计窗口内永远不可能命中，等于规则失效）
-- 两套引擎分工：下面带 level_high_* 的四条是毕设总纲规则（analysis/warning.py，
--   预警等级按严重程度浮动，表里的 warning_level 仅作兜底），其余是扩展细粒度规则
--   （analysis/warning_rules.py，等级取本表静态值）。
-- 已建库的同事不用重跑本文件：analysis/warning.py 启动扫描时会 INSERT IGNORE 补齐新规则。
-- =============================================================================
INSERT INTO warning_rule (rule_code, rule_name, warning_type, threshold_value, threshold_json, warning_level, description)
VALUES
    -- ---- 毕设总纲四大规则 ----
    ('NO_CONSUME',         '连续无消费',       'consume', 3.00,
     '{"days":3,"level_high_days":5}',          2, '连续 3 天无任何消费记录（>=5 天升级为高），疑似离校、经济困难或卡片异常'),
    ('CONSUME_DROP',       '本周消费骤降',     'consume', 0.50,
     '{"ratio":0.5,"level_high_ratio":0.25,"min_last_week_amount":30}', 2,
     '自然周消费额不足上周 50%（降幅 >=75% 升级为高），且上周消费不低于 30 元'),
    ('NO_LIBRARY',         '长期未进图书馆',   'study',   7.00,
     '{"days":7,"level_high_days":14}',         2, '连续 7 天无进馆记录（>=14 天升级为高），学习行为异常'),
    ('NIGHT_WEEK_CONSUME', '夜间消费频发',     'health',  5.00,
     '{"start":"23:00","end":"05:00","times":5,"level_high_times":10}', 2,
     '单个自然周内 23:00-05:00 消费超过 5 次（>=10 次升级为高），作息异常'),
    -- ---- 扩展细粒度规则 ----
    ('HIGH_CONSUME',   '单日消费过高',     'consume', 300.00,
     '{"window_days":7,"multiplier":3.0}',  3, '单日消费额 > 300 元，或超过其近 7 日均值 3 倍'),
    ('LOW_CONSUME',    '疑似节食/低消费',   'consume', NULL,
     '{"window_days":4,"max_meals_per_day":1}', 3,
     '连续 4 天每天交易笔数 ≤1（频次口径；旧版金额<10元 OR 会误抓周末零消费，已改）'),
    ('NIGHT_CONSUME',  '深夜消费异常',      'consume', NULL,
     '{"start":"23:00","end":"05:00","times":3}', 2, '23:00-05:00 时段消费在分析窗口内累计 ≥3 次'),
    ('MEAL_IRREGULAR', '三餐不规律',        'health',  NULL,
     '{"missing_rate":0.5,"window_days":7}', 2, '近 7 天缺餐率超过 50%'),
    ('OVERSTAY',       '在馆时间过长',      'study',   6.00,
     '{"hours":6}',                          1, '单日累计在馆时长超过 6 小时（久坐提醒）');

-- =============================================================================
-- 常用验证语句（数据入库后可用于自检）
-- =============================================================================
-- SELECT COUNT(*) FROM student;
-- SELECT COUNT(*), MIN(consumed_at), MAX(consumed_at) FROM consumption;
-- SELECT meal_period, COUNT(*) FROM consumption GROUP BY meal_period;
-- SELECT student_id, SUM(stay_minutes) FROM library_record GROUP BY student_id ORDER BY 2 DESC LIMIT 10;
-- EXPLAIN SELECT * FROM consumption WHERE student_id='2022010101' AND consumed_at>='2026-01-01';
