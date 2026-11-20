"""接口出入参模型：列表分页、动作结果与各模块的明细结构。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    """登记或修改一条业务记录时提交的字段集合。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class ActionPayload(BaseModel):
    """状态动作使用独立契约，避免与登记的 values 载荷混用。"""

    action: str
    remark: str | None = None


# ========== 属性字典 ==========
class AttrDictEntry(BaseModel):
    """属性定义：描述用户属性字段的元数据。"""

    id: int
    status: str = "草稿"
    pending: bool = True
    abnormal: bool = False
    attr_id: str = Field(..., description="属性编号")
    attr_name: str = Field(..., description="属性名称")
    data_type: str = Field(..., description="数据类型：string/int/float/bool/datetime/enum")
    enum_values: list[str] = Field(default_factory=list, description="枚举值集")
    source: str = Field(..., description="数据来源：event/derived/import")
    update_freq: str = Field(..., description="更新频率：realtime/hourly/daily/weekly")
    attribution: str = Field(..., description="归因方式：first/last/linear")
    version: str = Field(..., description="属性版本")


# ========== 标签定义 ==========
class TagDefineEntry(BaseModel):
    """标签规则：定义标签的计算逻辑与数据依赖。"""

    id: int
    status: str = "草稿"
    pending: bool = True
    abnormal: bool = False
    tag_id: str = Field(..., description="标签编号")
    tag_name: str = Field(..., description="标签名称")
    tag_level: str = Field(..., description="标签层级：basic/derived/composite")
    compute_logic: str = Field(..., description="计算逻辑表达式")
    source_attrs: list[str] = Field(default_factory=list, description="依赖的属性编号列表")
    update_cycle: str = Field(..., description="更新周期")
    coverage_threshold: float = Field(0.0, description="覆盖阈值")
    version: str = Field(..., description="标签版本")


# ========== 标签计算 ==========
class TagComputeEntry(BaseModel):
    """标签计算任务：执行标签规则的批量计算。"""

    id: int
    status: str = "草稿"
    pending: bool = True
    abnormal: bool = False
    task_id: str = Field(..., description="任务编号")
    tag_id: str = Field(..., description="关联标签编号")
    compute_scope: str = Field(..., description="计算范围：all/incremental/delta")
    engine: str = Field(..., description="计算引擎：sql/python/spark")
    input_partitions: list[str] = Field(default_factory=list, description="输入分区")
    output_partition: str = Field(..., description="输出分区")
    parallelism: int = Field(1, description="并行度")
    exec_state: str = Field(..., description="执行状态")
    result_count: int = Field(0, description="计算结果条数")
    error_log: str = Field("", description="错误日志")


# ========== 画像卡片 ==========
class ProfileCardEntry(BaseModel):
    """画像卡片：展示用户标签计算结果的配置。"""

    id: int
    status: str = "草稿"
    pending: bool = True
    abnormal: bool = False
    card_id: str = Field(..., description="卡片编号")
    card_name: str = Field(..., description="卡片名称")
    display_tags: list[str] = Field(default_factory=list, description="展示标签编号列表")
    data_source: str = Field(..., description="数据来源：tag_compute/user_segment")
    display_style: str = Field(..., description="展示样式：list/grid/chart")
    refresh_strategy: str = Field(..., description="刷新策略：manual/auto/schedule")
    segment_id: str = Field("", description="关联分群编号")
    version: str = Field(..., description="卡片版本")


# ========== 埋点事件 ==========
class EventTrackEntry(BaseModel):
    """事件埋点：定义需要采集的用户行为事件。"""

    id: int
    status: str = "草稿"
    pending: bool = True
    abnormal: bool = False
    event_id: str = Field(..., description="事件编号")
    event_name: str = Field(..., description="事件名称")
    category: str = Field(..., description="事件分类：page/click/expose/custom")
    attr_schema: list[str] = Field(default_factory=list, description="属性定义编号列表")
    report_freq: str = Field(..., description="上报频率：realtime/batch")
    sample_rate: float = Field(1.0, description="采样比例")
    table_name: str = Field(..., description="数据表名")
    version: str = Field(..., description="事件版本")


# ========== 事件清洗 ==========
class EventCleanseEntry(BaseModel):
    """清洗规则：定义事件数据的校验与清洗策略。"""

    id: int
    status: str = "草稿"
    pending: bool = True
    abnormal: bool = False
    rule_id: str = Field(..., description="规则编号")
    event_id: str = Field(..., description="关联事件编号")
    check_fields: list[str] = Field(default_factory=list, description="校验字段列表")
    valid_range: dict[str, Any] = Field(default_factory=dict, description="合法范围")
    anomaly_action: str = Field(..., description="异常处理：discard/quarantine/flag")
    bot_detect: bool = Field(False, description="刷量检测")
    dedup_window: int = Field(0, description="去重窗口（秒）")
    version: str = Field(..., description="规则版本")


# ========== 事件聚合 ==========
class EventAggregateEntry(BaseModel):
    """聚合配置：定义事件数据的聚合计算规则。"""

    id: int
    status: str = "草稿"
    pending: bool = True
    abnormal: bool = False
    config_id: str = Field(..., description="配置编号")
    event_id: str = Field(..., description="关联事件编号")
    agg_dimensions: list[str] = Field(default_factory=list, description="聚合维度")
    agg_function: str = Field(..., description="聚合函数：count/sum/avg/max/min/uv")
    time_grain: str = Field(..., description="时间粒度：minute/hour/day/week/month")
    filter_expr: str = Field("", description="过滤条件")
    output_table: str = Field(..., description="输出表名")
    update_cycle: str = Field(..., description="更新周期")


# ========== 行为路径 ==========
class BehaviorPathEntry(BaseModel):
    """路径模型：定义用户行为路径分析的配置。"""

    id: int
    status: str = "草稿"
    pending: bool = True
    abnormal: bool = False
    model_id: str = Field(..., description="模型编号")
    start_event: str = Field(..., description="起始事件编号")
    target_event: str = Field(..., description="目标事件编号")
    time_window: int = Field(86400, description="时间窗口（秒）")
    path_depth: int = Field(5, description="路径深度")
    session_split_rule: str = Field(..., description="会话切割规则编号")
    path_filter: str = Field("", description="路径过滤条件")
    analysis_range: str = Field(..., description="分析区间")
    funnel_id: str = Field("", description="关联漏斗编号")
    funnel_result_version: str = Field(
        "", description="固定的漏斗结果数据版本；为空时不读取漏斗归因"
    )
    funnel_step_id: str = Field("", description="归因步骤的稳定步骤标识")


# ========== 漏斗分析 ==========
class FunnelAnalyzeEntry(BaseModel):
    """漏斗定义：定义用户转化漏斗分析的配置。"""

    id: int
    status: str = "草稿"
    pending: bool = True
    abnormal: bool = False
    funnel_id: str = Field(..., description="漏斗编号")
    funnel_name: str = Field(..., description="漏斗名称")
    step_events: list[str] = Field(default_factory=list, description="步骤事件编号序列")
    step_defs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="步骤定义：每步携带稳定 step_id，顺序即当前步序；为空时按事件+出现序号推导",
    )
    conversion_window: int = Field(86400, description="转化窗口（秒）")
    step_window: int = Field(3600, description="步骤窗口（秒）")
    related_event: str = Field("", description="关联事件编号")
    group_dimension: str = Field("", description="分组维度")
    data_range: str = Field(..., description="数据范围")


# ========== 会话切割 ==========
class SessionSplitEntry(BaseModel):
    """切割策略：定义用户会话的切割规则。"""

    id: int
    status: str = "草稿"
    pending: bool = True
    abnormal: bool = False
    strategy_id: str = Field(..., description="策略编号")
    strategy_name: str = Field(..., description="策略名称")
    timeout_sec: int = Field(1800, description="超时阈值（秒）")
    cross_day_policy: str = Field(..., description="跨天策略：split/merge/keep")
    cross_channel_policy: str = Field(..., description="跨渠道策略：split/merge")
    attribution_window: int = Field(604800, description="归因窗口（秒）")
    session_key: str = Field(..., description="会话标识字段")
    version: str = Field(..., description="策略版本")


# ========== 用户分群 ==========
class UserSegmentEntry(BaseModel):
    """分群定义：定义用户分群的规则与配置。"""

    id: int
    status: str = "草稿"
    pending: bool = True
    abnormal: bool = False
    segment_id: str = Field(..., description="分群编号")
    segment_name: str = Field(..., description="分群名称")
    base_behavior: str = Field(..., description="基准行为事件编号")
    tier_rules: list[dict[str, Any]] = Field(default_factory=list, description="分层规则")
    time_range: str = Field(..., description="时间范围")
    size_estimate: int = Field(0, description="分群规模估计")
    update_mode: str = Field(..., description="更新方式：manual/schedule/stream")
    version: str = Field(..., description="分群版本")


# ========== 人群圈选 ==========
class CrowdSelectEntry(BaseModel):
    """圈选条件：定义基于标签的人群圈选规则。"""

    id: int
    status: str = "草稿"
    pending: bool = True
    abnormal: bool = False
    condition_id: str = Field(..., description="条件编号")
    condition_name: str = Field(..., description="条件名称")
    tag_combination: list[dict[str, Any]] = Field(default_factory=list, description="标签组合条件")
    logic_expr: str = Field(..., description="逻辑表达式")
    size_estimate: int = Field(0, description="预计规模")
    refresh_freq: str = Field(..., description="刷新频率")
    output_set: str = Field(..., description="输出集合标识")
    version: str = Field(..., description="条件版本")


# ========== 交集分析 ==========
class OverlapAnalysisEntry(BaseModel):
    """交集任务：定义两个人群交集分析的配置。"""

    id: int
    status: str = "草稿"
    pending: bool = True
    abnormal: bool = False
    task_id: str = Field(..., description="任务编号")
    crowd_a: str = Field(..., description="人群A条件编号")
    crowd_b: str = Field(..., description="人群B条件编号")
    intersect_mode: str = Field(..., description="交集方式：intersect/union/diff/a_only/b_only")
    analysis_dims: list[str] = Field(default_factory=list, description="分析维度")
    output_metrics: list[str] = Field(default_factory=list, description="输出指标")
    result_table: str = Field(..., description="结果表名")
    analysis_time: str = Field(..., description="分析时间")


# ========== 标签下钻 ==========
class TagDrillEntry(BaseModel):
    """下钻配置：定义标签维度下钻分析的配置。"""

    id: int
    status: str = "草稿"
    pending: bool = True
    abnormal: bool = False
    config_id: str = Field(..., description="配置编号")
    parent_tag: str = Field(..., description="父标签编号")
    child_tags: list[str] = Field(default_factory=list, description="子标签集")
    drill_dimensions: list[str] = Field(default_factory=list, description="下钻维度")
    data_range: str = Field(..., description="数据范围")
    stat_method: str = Field(..., description="统计方式：count/dist/sum/avg")
    output_format: str = Field(..., description="输出格式：table/chart/csv")
    refresh_interval: str = Field(..., description="刷新间隔")


# ========== 留存计算 ==========
class RetentionCalcEntry(BaseModel):
    """留存配置：定义用户留存分析的计算规则。"""

    id: int
    status: str = "草稿"
    pending: bool = True
    abnormal: bool = False
    config_id: str = Field(..., description="配置编号")
    init_event: str = Field(..., description="初始行为事件编号")
    return_event: str = Field(..., description="回访行为事件编号")
    calc_period: str = Field(..., description="计算周期：day/week/month")
    segment_dim: str = Field("", description="分段维度")
    base_date: str = Field(..., description="基准日期")
    retention_window: int = Field(30, description="留存窗口（天）")
    result_table: str = Field(..., description="结果表名")


# ========== 生命周期价值 ==========
class LifetimeValueEntry(BaseModel):
    """LTV模型：定义用户生命周期价值预测的配置。"""

    id: int
    status: str = "草稿"
    pending: bool = True
    abnormal: bool = False
    model_id: str = Field(..., description="模型编号")
    segment_id: str = Field(..., description="用户分群编号")
    value_metric: str = Field(..., description="价值指标：revenue/order_count/active_days")
    predict_window: int = Field(180, description="预测窗口（天）")
    decay_factor: float = Field(0.95, description="衰减因子")
    history_baseline: str = Field(..., description="历史基线日期范围")
    calibrate_period: str = Field(..., description="校准周期")
    version: str = Field(..., description="模型版本")


# ========== 标签快照 ==========
class TagSnapshotEntry(BaseModel):
    """快照记录：标签与分群的全量快照。"""

    id: int
    status: str = "草稿"
    pending: bool = True
    abnormal: bool = False
    snapshot_id: str = Field(..., description="快照编号")
    snapshot_date: str = Field(..., description="快照日期")
    user_count: int = Field(0, description="用户基数")
    tag_count: int = Field(0, description="标签数量")
    segment_count: int = Field(0, description="分群数量")
    snapshot_path: str = Field(..., description="快照路径")
    storage_format: str = Field(..., description="存储格式：json/parquet/csv")
    retention_days: int = Field(30, description="保留天数")


# ========== 行为热力 ==========
class BehaviorHeatmapEntry(BaseModel):
    """热力配置：定义行为热力图分析的配置。"""

    id: int
    status: str = "草稿"
    pending: bool = True
    abnormal: bool = False
    config_id: str = Field(..., description="配置编号")
    event_id: str = Field(..., description="行为事件编号")
    time_range: str = Field(..., description="时间范围")
    spatial_dim: str = Field(..., description="空间维度：page/region/element")
    agg_grain: str = Field(..., description="聚合粒度")
    color_scale: str = Field(..., description="色阶规则")
    output_image: str = Field("", description="输出图片路径")
    refresh_freq: str = Field(..., description="刷新频率")


# ========== 数据链路产物 ==========
class CleanseResult(BaseModel):
    """清洗结果产物。"""

    rule_id: str
    event_id: str
    total_records: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    deduped_records: int = 0
    output_table: str = ""
    snapshot_path: str = ""


class AggResult(BaseModel):
    """聚合结果产物。"""

    config_id: str
    event_id: str
    agg_dimensions: list[str]
    time_grain: str
    result_rows: list[dict[str, Any]] = Field(default_factory=list)
    total_count: int = 0
    output_table: str = ""


class TagComputeResult(BaseModel):
    """标签计算结果产物。"""

    task_id: str
    tag_id: str
    compute_scope: str
    result_count: int = 0
    user_tag_values: list[dict[str, Any]] = Field(default_factory=list)
    output_partition: str = ""
    compute_time_ms: int = 0


class SegmentResult(BaseModel):
    """分群计算结果产物。"""

    segment_id: str
    segment_name: str
    user_count: int = 0
    tier_distribution: dict[str, int] = Field(default_factory=dict)
    output_set: str = ""


class FunnelResult(BaseModel):
    """漏斗分析结果产物（第 1 版本，按数组位置表达步骤，仅保留读取兼容）。"""

    funnel_id: str
    funnel_name: str
    step_events: list[str]
    step_counts: list[int] = Field(default_factory=list)
    step_rates: list[float] = Field(default_factory=list)
    total_conversion_rate: float = 0.0
    group_results: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class FunnelStepResult(BaseModel):
    """第 2 版本漏斗的单步结果：稳定步骤标识 + 步序 + 分组归因。"""

    step_id: str
    step_index: int
    event_id: str
    step_name: str = ""
    count: int | None = None
    rate: float | None = None
    count_source: str = "computed"
    group_attribution_available: bool = False
    group_results: list[dict[str, Any]] = Field(default_factory=list)


class FunnelResultV2(BaseModel):
    """漏斗分析结果产物（第 2 版本）：步骤有稳定标识，结果按版本存放。"""

    schema_version: str = "v2"
    funnel_id: str
    funnel_name: str
    data_version: str
    funnel_revision: str = ""
    step_events: list[str] = Field(default_factory=list)
    steps: list[FunnelStepResult] = Field(default_factory=list)
    step_counts: list[int | None] = Field(default_factory=list)
    step_rates: list[float | None] = Field(default_factory=list)
    total_conversion_rate: float = 0.0
    group_dimension: str = ""
    group_results: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    event_group_totals: list[dict[str, Any]] = Field(default_factory=list)
    counts_available: bool = True
    migration: dict[str, Any] | None = None


class RetentionResult(BaseModel):
    """留存计算结果产物。"""

    config_id: str
    init_event: str
    return_event: str
    base_date: str
    cohort_sizes: dict[str, int] = Field(default_factory=dict)
    retention_rates: dict[str, list[float]] = Field(default_factory=dict)
    result_table: str = ""


class LtvResult(BaseModel):
    """LTV预测结果产物。"""

    model_id: str
    segment_id: str
    predict_window: int
    predicted_values: list[dict[str, Any]] = Field(default_factory=list)
    avg_ltv: float = 0.0
    calibration_error: float = 0.0


class SessionResult(BaseModel):
    """会话切割结果产物。"""

    strategy_id: str
    total_events: int = 0
    session_count: int = 0
    avg_session_duration: float = 0.0
    sessions: list[dict[str, Any]] = Field(default_factory=list)


class PathResult(BaseModel):
    """行为路径分析结果产物。"""

    model_id: str
    start_event: str
    target_event: str
    sankey_nodes: list[dict[str, Any]] = Field(default_factory=list)
    sankey_links: list[dict[str, Any]] = Field(default_factory=list)
    conversion_paths: list[list[str]] = Field(default_factory=list)
    total_conversions: int = 0
    funnel_step_attribution: dict[str, Any] | None = None
