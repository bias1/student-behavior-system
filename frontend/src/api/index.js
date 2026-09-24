import { http } from './request'

/**
 * 接口清单：与后端蓝图一一对应，路径不带 /api（baseURL 已含）。
 * 字段含义以后端实际返回为准，页面里用到的关键结构注释在函数上方。
 */

/* ---------------- 总览 /api/overview ---------------- */
export const OverviewApi = {
  /** 指标卡：student_count / total_amount / avg_daily_study_minutes / warning_count / *_peak_hour */
  stats: (params) => http.get('/overview', params),
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
  table: (params) => http.get('/clustering/table', params),
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
  /** 处置：status 0-未处理 1-已处理 2-已忽略 */
  handle: (id, body) => http.post(`/warning/${id}/handle`, body),
}

/* ---------------- 其他 ---------------- */
export const SystemApi = {
  health: () => http.get('/health', null, { silent: true }),
}

/** 预警大类中文映射（后端 warning_type 存英文码） */
export const WARNING_TYPE_TEXT = { consume: '消费异常', study: '学习行为', health: '健康作息' }
/** 消费波动/规律类指标的展示色（饼图、簇柱状图共用，保证同页同义） */
export const PALETTE = ['#37e2f0', '#4ea1ff', '#ffd166', '#7ee787', '#ff6b81', '#b28dff', '#ff9f43']
