import { http } from './request'

/**
 * 接口清单：与后端蓝图一一对应，路径不带 /api（baseURL 已含）。
 * 字段含义以后端实际返回为准，页面里用到的关键结构注释在函数上方。
 */

/* ---------------- 总览 /api/overview ---------------- */
export const OverviewApi = {
  /** 指标卡：student_count / total_amount / avg_daily_study_minutes / warning_count / *_peak_hour */
  stats: (params) => http.get('/overview', params),
  /** 汇总指标：含环比 *_delta / 小泡图 spark_* / active_rate，概览页 KPI 卡数据源 */
  summary: (params) => http.get('/overview/summary', params),
  /** 元信息：date_start、date_end、merchant_types、warning_levels、warning_status、weekday_names */
  meta: () => http.get('/overview/meta'),
  /** 群体结构：dim = college | grade | major | gender → items[{name, students, avg_amount, ...}] */
  groups: (dim = 'college') => http.get('/overview/groups', { dim }),
  /** 消费排行：order = desc(高消费) | asc(疑似低消费) */
  rank: (params) => http.get('/overview/rank', params),
}

/* ---------------- 消费 /api/consumption ---------------- */
export const ConsumptionApi = {
  /** dates[] + series{amount, records, students, library_minutes, ...} + summary{weekday/weekend_avg_amount} */
  trend: (params) => http.get('/consumption/trend', params),
  /** 热力图：hours[24]、weekdays[7]、data[[hour, weekday, 笔数]]、amount_data[[hour, weekday, 金额]] */
  heatmap: (params) => http.get('/consumption/heatmap', params),
  /** 类别占比：by_merchant_type / by_meal_period / top_merchants，均含 amount_pct */
  category: (params) => http.get('/consumption/category', params),
}

/* ---------------- 图书馆 /api/library ---------------- */
export const LibraryApi = {
  /** dates[] + series{visits, students, avg_stay_minutes, total_hours} + heatmap + hour_dist + area_dist */
  trend: (params) => http.get('/library/trend', params),
  /** 独立热力图：data[[hour, weekday, 人次]] + max */
  heatmap: (params) => http.get('/library/heatmap', params),
  /** 小时分布 + 馆区分布：hour_dist[{hour, n}]、area_dist[{area_name, n}] */
  hours: (params) => http.get('/library/hours', params),
}

/* ---------------- 学生 /api/student ---------------- */
export const StudentApi = {
  /** 分页列表 / 搜索框：keyword 支持学号前缀与姓名，返回 {total, page, size, items} */
  list: (params) => http.get('/student/list', params),
  /** 个体画像主体：info / kpi / radar / daily / cluster / warnings / hour_dist */
  profile: (sid, params, config) => http.get(`/student/${sid}/profile`, params, config),
  /** 消费流水明细分页 */
  consumption: (sid, params) => http.get(`/student/${sid}/consumption`, params),
  /** 进馆记录明细分页 */
  library: (sid, params) => http.get(`/student/${sid}/library`, params),
}

/* ---------------- 聚类 /api/clustering ---------------- */
export const ClusteringApi = {
  /**
   * K-Means 结果：clusters[{cluster,label,desc,definition,size,pct,features,z_scores,top_students}]
   *            + points[{student_id,features,cluster,label,x,y}]（x/y 为 PCA 降维坐标）
   * features=core 只用总纲 4 特征，full 用 11 特征；后端有 TTL 缓存，refresh=1 强制重算
   */
  result: (params, config) => http.get('/clustering/result', params, config),
  /** 手肘法：k[]、sse[]、silhouette[]、total_ss —— 论文"K 值确定"一节的数据源 */
  elbow: (params, config) => http.get('/clustering/elbow', params, config),
  /** 单簇成员（按日均消费降序） */
  members: (params) => http.get('/clustering/members', params),
  /** 扁平归类表：columns + items[{student_id, ..., cluster, label}]，可直接铺表格 */
  table: (params, config) => http.get('/clustering/table', params, config),
  /**
   * 算法实验（需 clustering:run）：预处理诊断/选 K/稳定性/特征消融/MiniBatch 对照
   * params: {k, features, k_min, k_max, cap, windows}
   */
  experiment: (params, config) => http.get('/clustering/experiment', params, config),
  /** IsolationForest 独立异常实验（需 clustering:run）：仅聚合分数分布，无个人名单 */
  iforest: (params, config) => http.get('/clustering/iforest', params, config),
}

/* ---------------- 预警 /api/warning ---------------- */
export const WarningApi = {
  /** 列表：type=consume|study|health，level=最低级别，status=0|1|2，keyword=学号/姓名 */
  list: (params) => http.get('/warning/list', params),
  /** 统计：total、by_type、by_level、by_status、by_rule、trend */
  stats: (params) => http.get('/warning/stats', params),
  /** 规则配置（筛选器与规则说明弹窗） */
  rules: () => http.get('/warning/rules'),
  /** 触发阈值扫描（幂等，可反复点击）—— 只跑扩展细粒度规则 */
  scan: (body) => http.post('/warning/scan', body || {}),
  /**
   * 重新计算预警：先清除窗口内已失效的预警再重算。
   * scope: syllabus(总纲四大规则，默认) | extended(细粒度) | all
   * persist=0 只实时计算不落库；rule_code 只重算单条
   */
  refresh: (body) => http.post('/warning/refresh', body || {}),
  /** 处置（兼容旧接口）：status 0-未处理 1-已处理 2-已忽略 */
  handle: (id, body) => http.post(`/warning/${id}/handle`, body),
  /**
   * 人工核实工作流（需 warning:handle）：
   * body: { action: 'assign'|'start'|'verify'|'close'|'reopen'|'appeal',
   *         assigned_to?, verify_result?, verify_note? }
   * verify_result: need_support | false_positive | data_issue | other
   */
  workflow: (id, body) => http.post(`/warning/${id}/workflow`, body),
  /** 规则级统计：triggered/verified/false_positive/duplicates/data_gap_ratio 等 + 免责（不宣称准确率） */
  ruleStats: (params) => http.get('/warning/rule-stats', params),
}

/* ---------------- 认证 /api/auth（Cookie 会话，阶段 1 生产化） ---------------- */
export const AuthApi = {
  /** 登录开关探测（匿名可访问）：enabled=false 时前端不拦路由，进入演示模式 */
  status: () => http.get('/auth/status', null, { silent: true }),
  /**
   * 登录：成功时后端通过 Set-Cookie 下发 httpOnly 会话 Cookie，
   * 响应体仅含身份信息（username/display_name/roles/permissions），不含令牌。
   * 失败 401（错误口令）/ 429（账号锁定）/ 403（账号禁用）
   */
  login: (username, password) => http.post('/auth/login', { username, password }, { silent: true }),
  /**
   * 登出：吊销当前会话并清除 httpOnly Cookie。
   * 须带 X-CSRF-Token（request.js 自动处理），无权限时 401。
   */
  logout: () => http.post('/auth/logout', {}, { silent: true }),
  /** 回显当前身份：刷新页面时 useSession.bootstrap() 调用此接口恢复登录态 */
  me: () => http.get('/auth/me', null, { silent: true }),
}

/* ---------------- 其他 ---------------- */
export const SystemApi = {
  health: () => http.get('/health', null, { silent: true }),
}

/** 预警大类中文映射（后端 warning_type 存英文码）*/
export const WARNING_TYPE_TEXT = { consume: '消费异常', study: '学习行为', health: '健康作息' }

/** 工作流五态（阶段 4）：预警只是待核实信号，不是结论 */
export const WORKFLOW_STATE_TEXT = { 0: '待核实', 1: '已分配', 2: '核实中', 3: '已核实', 4: '已关闭' }
export const WORKFLOW_STATE_TONE = { 0: 'warning', 1: 'cyan', 2: 'primary', 3: 'success', 4: 'neutral' }
/** 信号五分类（阶段 4） */
export const SIGNAL_KIND_TEXT = {
  objective_record: '客观行为记录', personal_change: '相对个人历史变化',
  data_quality: '数据质量问题', need_verification: '待人工核实信号', confirmed_support: '经核实支持需求',
}
/** 核实结论 */
export const VERIFY_RESULT_TEXT = {
  need_support: '确认需支持', false_positive: '误报', data_issue: '数据问题', other: '其它',
}
