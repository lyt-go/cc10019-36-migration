"""漏斗分析引擎（第 2 版本结果数据）。

第 2 版本用稳定步骤标识 ``step_id`` 表达步骤，不再依赖数组位置和事件编号：

* 同一漏斗可以出现两个完全相同的事件（例如两步都是商品详情）；
* 结果产物按 ``data_version`` 分版本存放，切换/回滚只移动活动版本指针；
* 行为路径通过 ``step_id`` 关联步骤，按结果版本里的步序和分组读取归因；
* 历史 v1 报告按事件记录分组时，迁移只保留事件合计，绝不拆成步骤人数。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.store import store
from app.schemas import FunnelResultV2

RESULT_SCHEMA = "v2"
LEGACY_SCHEMA = "v1"

# 漏斗 v1 结果只有事件级分组，没有按步骤拆分的依据
LEGACY_EVENT_TOTAL_ONLY = "legacy_event_total_only"
STEP_COUNT_UNAVAILABLE = "unavailable_legacy_event_total_only"


def _generate_event_data(event_id: str, count: int, occurrence: int = 1) -> list[dict[str, Any]]:
    """生成模拟事件数据用于漏斗计算。

    ``occurrence`` 表示同一事件在漏斗里第几次出现（从 1 开始）。同一漏斗允许
    两个步骤使用同一个事件编号，这时第二次出现要晚于第一次，且人数继续衰减。
    """
    events = []
    keep = max(0.0, 0.6 ** (occurrence - 1))
    time_offset = (occurrence - 1) * 2000
    for i in range(1, count + 1):
        user_id = f"U{i:05d}"
        # 模拟漏斗流失：每一步只有前一步的一部分用户继续
        if event_id == "EV-001":  # 页面浏览
            events.append({
                "user_id": user_id,
                "event_id": event_id,
                "timestamp": 1700000000 + time_offset + i * 100,
                "ATTR-001": ["app", "web", "miniapp", "h5"][i % 4],
                "ATTR-005": ["普通", "银卡", "金卡", "钻石"][i % 4],
            })
        elif event_id == "EV-002":  # 商品点击 - 60% 转化
            if i <= int(count * 0.6 * keep):
                events.append({
                    "user_id": user_id,
                    "event_id": event_id,
                    "timestamp": 1700000100 + time_offset + i * 100,
                    "ATTR-001": ["app", "web", "miniapp", "h5"][i % 4],
                    "ATTR-005": ["普通", "银卡", "金卡", "钻石"][i % 4],
                })
        elif event_id == "EV-003":  # 下单成功 - 30% 转化
            if i <= int(count * 0.3 * keep):
                events.append({
                    "user_id": user_id,
                    "event_id": event_id,
                    "timestamp": 1700000200 + time_offset + i * 100,
                    "ATTR-001": ["app", "web", "miniapp", "h5"][i % 4],
                    "ATTR-005": ["普通", "银卡", "金卡", "钻石"][i % 4],
                })
        elif event_id == "EV-004":  # 支付完成 - 25% 转化
            if i <= int(count * 0.25 * keep):
                events.append({
                    "user_id": user_id,
                    "event_id": event_id,
                    "timestamp": 1700000300 + time_offset + i * 100,
                    "ATTR-001": ["app", "web", "miniapp", "h5"][i % 4],
                    "ATTR-005": ["普通", "银卡", "金卡", "钻石"][i % 4],
                })
    return events


def _resolve_step_defs(funnel: dict[str, Any]) -> list[dict[str, Any]]:
    """解析漏斗步骤定义。

    优先使用业务登记的 ``step_defs``（带稳定 ``step_id``）。只有完全没有步骤标识的
    历史漏斗才按位置推导一次，并把推导方式写进结果，避免把位置当成长期标识。
    """
    step_defs = funnel.get("step_defs") or []
    if step_defs:
        resolved: list[dict[str, Any]] = []
        for index, item in enumerate(step_defs, start=1):
            event_id = item.get("event_id")
            if not event_id:
                raise ValueError(f"Funnel step missing event_id at index {index}")
            step_id = item.get("step_id") or f"{funnel['funnel_id']}-S{index:02d}"
            resolved.append({
                "step_id": step_id,
                "event_id": event_id,
                "step_name": item.get("step_name", ""),
                "step_index": index,
            })
        return resolved

    step_events = funnel.get("step_events") or []
    if not step_events:
        raise ValueError(f"Funnel has no steps: {funnel['funnel_id']}")
    return [
        {
            "step_id": f"{funnel['funnel_id']}-S{index:02d}",
            "event_id": event_id,
            "step_name": "",
            "step_index": index,
            "derived_step_id": True,
        }
        for index, event_id in enumerate(step_events, start=1)
    ]


def _funnel_revision(funnel: dict[str, Any]) -> str:
    """当前漏斗步骤定义的修订号；没有登记时按步骤标识推导一个可追溯的值。"""
    revision = funnel.get("revision")
    if revision:
        return str(revision)
    return "derived-" + "-".join(
        str(step["step_id"]) for step in _resolve_step_defs(funnel)
    )


def _revision_step_defs(funnel: dict[str, Any], revision: str) -> list[dict[str, Any]] | None:
    """按修订号取步骤定义快照；找不到返回 None，绝不回退到当前顺序。"""
    if revision and revision == _funnel_revision(funnel):
        return _copy_step_defs(_resolve_step_defs(funnel))
    for item in funnel.get("revision_history", []):
        if item.get("revision") == revision:
            return _copy_step_defs(item.get("step_defs") or [])
    return None


def _copy_step_defs(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """复制步骤快照并补齐步序，供迁移与路径引用使用。"""
    return [
        {
            "step_id": step.get("step_id"),
            "event_id": step["event_id"],
            "step_name": step.get("step_name", ""),
            "step_index": index,
        }
        for index, step in enumerate(steps, start=1)
    ]


def _occurrences(step_defs: list[dict[str, Any]]) -> list[int]:
    """每一步事件在漏斗里是第几次出现，用于区分两个相同事件的步骤。"""
    seen: dict[str, int] = defaultdict(int)
    result: list[int] = []
    for step in step_defs:
        seen[step["event_id"]] += 1
        result.append(seen[step["event_id"]])
    return result


def _collect_user_events(
    step_defs: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], list[int]]:
    """按用户归集所有步骤事件并排序；返回每步的事件出现序号。"""
    occurrences = _occurrences(step_defs)
    all_events: list[dict[str, Any]] = []
    for step, occurrence in zip(step_defs, occurrences):
        all_events.extend(_generate_event_data(step["event_id"], 1000, occurrence))
    user_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in all_events:
        user_events[event["user_id"]].append(event)
    for uid in user_events:
        user_events[uid].sort(key=lambda item: item["timestamp"])
    return user_events, occurrences


def _reach_steps(
    step_defs: list[dict[str, Any]], step_window: int, conversion_window: int
) -> list[dict[str, dict[str, Any]]]:
    """逐步计算到达用户及其触发事件，返回每一步 ``uid -> event``。"""
    user_events, occurrences = _collect_user_events(step_defs)

    window = step_window if step_window > 0 else conversion_window
    reached: list[dict[str, dict[str, Any]]] = []

    first: dict[str, dict[str, Any]] = {}
    for uid, events in user_events.items():
        for item in events:
            if item["event_id"] == step_defs[0]["event_id"]:
                first.setdefault(uid, item)
    reached.append(first)

    for index in range(1, len(step_defs)):
        min_timestamp = 1700000000 + (occurrences[index] - 1) * 2000
        current: dict[str, dict[str, Any]] = {}
        for uid, prev_event in reached[index - 1].items():
            prev_time = prev_event["timestamp"]
            for item in user_events[uid]:
                if item["event_id"] != step_defs[index]["event_id"]:
                    continue
                # 同一事件的第 n 次出现只匹配第 n 批事件，避免两步都记到同一条埋点
                if item["timestamp"] < min_timestamp:
                    continue
                if prev_time < item["timestamp"] <= prev_time + window:
                    current[uid] = item
                    break
        reached.append(current)
    return reached


def _group_rows(
    step: dict[str, Any],
    users: dict[str, dict[str, Any]],
    group_dim: str,
    source: str,
) -> list[dict[str, Any]]:
    """按步骤统计分组人数（同一用户同组只计一次）。"""
    if not group_dim:
        return []
    counts: dict[str, int] = defaultdict(int)
    for event in users.values():
        counts[str(event.get(group_dim, "unknown"))] += 1
    return [
        {
            "step_id": step["step_id"],
            "step_index": step["step_index"],
            "event_id": step["event_id"],
            "group_value": value,
            "count": count,
            "source": source,
        }
        for value, count in sorted(counts.items())
    ]


def analyze_funnel(funnel_id: str, data_version: str | None = None) -> FunnelResultV2:
    """执行漏斗分析，产出带稳定步骤标识的第 2 版本结果。"""
    funnel = store.find_by_field("funnel_analyze", "funnel_id", funnel_id)
    if funnel is None:
        raise ValueError(f"Funnel not found: {funnel_id}")

    step_defs = _resolve_step_defs(funnel)
    funnel_revision = _funnel_revision(funnel)
    group_dim = funnel.get("group_dimension", "")
    conversion_window = funnel.get("conversion_window", 86400)
    step_window = funnel.get("step_window", 3600)

    reached = _reach_steps(step_defs, step_window, conversion_window)
    step1_count = len(reached[0]) if reached else 0

    steps: list[dict[str, Any]] = []
    step_counts: list[int] = []
    step_rates: list[float] = []
    for index, step in enumerate(step_defs):
        count = len(reached[index])
        rate = 1.0 if index == 0 else (round(count / step1_count, 4) if step1_count else 0.0)
        rows = _group_rows(step, reached[index], group_dim, "computed")
        step_counts.append(count)
        step_rates.append(rate)
        steps.append({
            "step_id": step["step_id"],
            "step_index": step["step_index"],
            "event_id": step["event_id"],
            "step_name": step.get("step_name", ""),
            "count": count,
            "rate": rate,
            "count_source": "computed",
            "group_attribution_available": bool(rows),
            "group_results": rows,
        })

    version = data_version or _next_version(funnel_id)
    result = FunnelResultV2(
        funnel_id=funnel_id,
        funnel_name=funnel["funnel_name"],
        data_version=version,
        funnel_revision=funnel_revision,
        step_events=[step["event_id"] for step in step_defs],
        steps=steps,
        step_counts=step_counts,
        step_rates=step_rates,
        total_conversion_rate=step_rates[-1] if step_rates else 0.0,
        group_dimension=group_dim,
        group_results={group_dim: [row for step in steps for row in step["group_results"]]} if group_dim else {},
        counts_available=True,
    )

    store.set_version_artifact("funnel_analyze", funnel_id, version, result.model_dump())
    store.update("funnel_analyze", funnel["id"], {"status": "已完成", "pending": False})
    return result


def _next_version(funnel_id: str) -> str:
    """在进程内生成下一个可回滚的版本号。"""
    return f"v2-{len(store.list_artifact_versions('funnel_analyze', funnel_id)) + 1:03d}"


def _step_summary(step: dict[str, Any]) -> dict[str, Any]:
    return {
        "step_id": step.get("step_id"),
        "step_index": step.get("step_index"),
        "event_id": step.get("event_id"),
        "step_name": step.get("step_name", ""),
    }


def migrate_funnel_result(
    funnel_id: str,
    source_version: str,
    target_version: str | None = None,
    *,
    activate: bool = True,
) -> dict[str, Any]:
    """把历史 v1 结果迁移成第 2 版本结果数据。

    迁移规则：
    1. 步骤与步序取历史报告记录的 ``funnel_revision`` 快照，不取当前漏斗顺序；
    2. v1 的 ``step_counts`` 只按位置原样搬运（历史版本本身就是这样表达的）；
    3. v1 的 ``group_results`` 只有事件合计，一律保留为事件级合计并标记不可拆步骤，
       绝不用事件人数顶替某一步的转化人数。
    """
    funnel = store.find_by_field("funnel_analyze", "funnel_id", funnel_id)
    if funnel is None:
        raise ValueError(f"Funnel not found: {funnel_id}")

    legacy = store.get_legacy_funnel_report(funnel_id, source_version)
    if legacy is None:
        raise ValueError(f"Legacy funnel report not found: {funnel_id}/{source_version}")
    if legacy.get("result_schema") != LEGACY_SCHEMA:
        raise ValueError(f"Not a legacy v1 report: {funnel_id}/{source_version}")

    legacy_revision = legacy.get("funnel_revision", "")
    steps = legacy.get("steps")
    if not steps:
        steps = _revision_step_defs(funnel, legacy_revision) if legacy_revision else None
    if not steps:
        raise ValueError("Legacy report has no step snapshot; refusing to guess current step order")
    steps = [
        {
            "step_id": step.get("step_id"),
            "step_index": index,
            "event_id": step["event_id"],
            "step_name": step.get("step_name", ""),
        }
        for index, step in enumerate(steps, start=1)
    ]

    legacy_counts = legacy.get("step_counts")
    counts_available = isinstance(legacy_counts, list) and len(legacy_counts) == len(steps)
    legacy_rates = legacy.get("step_rates") or []
    step1_count = legacy_counts[0] if counts_available and legacy_counts else 0

    migrated_steps: list[dict[str, Any]] = []
    step_counts: list[int | None] = []
    step_rates: list[float | None] = []
    for index, step in enumerate(steps):
        if counts_available:
            count: int | None = legacy_counts[index]
            rate = legacy_rates[index] if index < len(legacy_rates) else (
                round(count / step1_count, 4) if step1_count else 0.0
            )
            source = "legacy_step_count"
        else:
            count = None
            rate = None
            source = STEP_COUNT_UNAVAILABLE
        step_counts.append(count)
        step_rates.append(rate)
        migrated_steps.append({
            **step,
            "count": count,
            "rate": rate,
            "count_source": source,
            "group_attribution_available": False,
            "group_results": [],
        })

    event_group_totals: list[dict[str, Any]] = []
    for row in legacy.get("group_results", []):
        event_id = row.get("event_id")
        event_group_totals.append({
            "event_id": event_id,
            "group_value": row.get("group_value"),
            "count": row.get("count"),
            "source": LEGACY_EVENT_TOTAL_ONLY,
            "step_attribution_available": False,
            "event_step_ids": [
                step["step_id"] for step in steps if step["event_id"] == event_id
            ],
            "reason": "历史分组只记录事件合计，不能拆成步骤人数",
        })

    current_revision = _funnel_revision(funnel)
    version = target_version or f"v2-{len(store.list_artifact_versions('funnel_analyze', funnel_id)) + 1:03d}"

    result = FunnelResultV2(
        funnel_id=funnel_id,
        funnel_name=legacy.get("funnel_name") or funnel["funnel_name"],
        data_version=version,
        funnel_revision=legacy_revision,
        step_events=[step["event_id"] for step in steps],
        steps=migrated_steps,
        step_counts=step_counts,
        step_rates=step_rates,
        total_conversion_rate=step_rates[-1] if step_rates and step_rates[-1] is not None else 0.0,
        group_dimension=legacy.get("group_dimension", ""),
        group_results={},
        event_group_totals=event_group_totals,
        counts_available=counts_available,
        migration={
            "source_schema": LEGACY_SCHEMA,
            "source_data_version": source_version,
            "source_funnel_revision": legacy_revision,
            "current_funnel_revision": current_revision,
            "step_order_matches_current": legacy_revision == current_revision,
            "rule": "步骤按历史修订快照绑定；事件合计不拆步骤人数",
        },
    )

    store.set_version_artifact("funnel_analyze", funnel_id, version, result.model_dump(), activate=activate)
    return result.model_dump()


def get_funnel_result(funnel_id: str) -> dict[str, Any] | None:
    """获取当前活动版本的漏斗结果。"""
    active = store.get_active_version("funnel_analyze", funnel_id)
    if active:
        artifact = store.get_version_artifact("funnel_analyze", funnel_id, active)
        if artifact:
            return artifact
    artifact = store.get_artifact("funnel_analyze", funnel_id)
    if artifact:
        return artifact
    try:
        return analyze_funnel(funnel_id).model_dump()
    except ValueError:
        return None


def get_funnel_result_version(funnel_id: str, version: str) -> dict[str, Any] | None:
    """按显式版本号读取漏斗结果；历史报告读取走这里，不随活动版本变化。"""
    return store.get_version_artifact("funnel_analyze", funnel_id, version)


def list_funnel_versions(funnel_id: str) -> dict[str, Any]:
    """列出一个漏斗的所有结果版本与活动版本。"""
    return {
        "funnel_id": funnel_id,
        "active_version": store.get_active_version("funnel_analyze", funnel_id),
        "versions": store.list_artifact_versions("funnel_analyze", funnel_id),
        "events": store.list_version_events("funnel_analyze", funnel_id),
    }


def switch_funnel_version(funnel_id: str, version: str, reason: str = "switch") -> dict[str, Any]:
    """切换漏斗结果的活动版本（步序、分组、路径引用随之整体切换）。"""
    activated = store.activate_version("funnel_analyze", funnel_id, version, event="switch", note=reason)
    if activated is None:
        raise ValueError(f"Funnel result version not found: {funnel_id}/{version}")
    return {"funnel_id": funnel_id, "active_version": version, "event": "switch", "reason": reason}


def rollback_funnel_version(funnel_id: str, version: str, reason: str = "rollback") -> dict[str, Any]:
    """回滚到指定漏斗结果版本；只移动活动指针，不覆盖任何版本的数据。"""
    activated = store.activate_version("funnel_analyze", funnel_id, version, event="rollback", note=reason)
    if activated is None:
        raise ValueError(f"Funnel result version not found: {funnel_id}/{version}")
    return {"funnel_id": funnel_id, "active_version": version, "event": "rollback", "reason": reason}


def get_legacy_funnel_report(funnel_id: str, version: str | None = None) -> dict[str, Any] | None:
    """读取历史 v1 漏斗报告（含只有事件合计的分组明细）。"""
    return store.get_legacy_funnel_report(funnel_id, version)


def update_funnel_steps(
    funnel_id: str,
    step_defs: list[dict[str, Any]],
    revision: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    """调整漏斗步骤（含换序），并把旧定义归档成修订快照。

    步骤以 ``step_id`` 为身份：换序只改顺序，不换身份；删除已有步骤会被拒绝，
    避免历史结果里的路径引用失去对应步骤。
    """
    funnel = store.find_by_field("funnel_analyze", "funnel_id", funnel_id)
    if funnel is None:
        raise ValueError(f"Funnel not found: {funnel_id}")
    if not step_defs:
        raise ValueError("Funnel must keep at least one step")

    seen_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, step in enumerate(step_defs, start=1):
        event_id = step.get("event_id")
        step_id = step.get("step_id")
        if not event_id or not step_id:
            raise ValueError(f"Step {index} requires both step_id and event_id")
        if step_id in seen_ids:
            raise ValueError(f"Duplicate step_id: {step_id}")
        seen_ids.add(step_id)
        normalized.append({
            "step_id": step_id,
            "event_id": event_id,
            "step_name": step.get("step_name", ""),
        })

    current_ids = {step["step_id"] for step in _resolve_step_defs(funnel)}
    missing = current_ids - seen_ids
    if missing:
        raise ValueError(f"Cannot drop steps still referenced by history: {sorted(missing)}")

    current_revision = _funnel_revision(funnel)
    history = [
        {"revision": item["revision"], "step_defs": [dict(step) for step in item["step_defs"]]}
        for item in funnel.get("revision_history", [])
    ]
    if current_revision and not current_revision.startswith("derived-"):
        if not any(item["revision"] == current_revision for item in history):
            history.append({
                "revision": current_revision,
                "step_defs": [
                    {"step_id": step["step_id"], "event_id": step["event_id"], "step_name": step.get("step_name", "")}
                    for step in _resolve_step_defs(funnel)
                ],
            })

    next_revision = revision or f"{funnel_id}-r{len(history) + 1}"
    if any(item["revision"] == next_revision for item in history):
        raise ValueError(f"Revision already exists: {next_revision}")

    updated = store.update("funnel_analyze", funnel["id"], {
        "step_defs": normalized,
        "step_events": [step["event_id"] for step in normalized],
        "revision": next_revision,
        "revision_history": history,
        "pending": True,
        "status": "草稿",
    })
    return {
        "funnel_id": funnel_id,
        "revision": next_revision,
        "previous_revision": current_revision,
        "step_defs": normalized,
        "note": note,
        "entry": updated,
    }


def resolve_step_reference(funnel_id: str, data_version: str, step_id: str) -> dict[str, Any]:
    """在指定结果版本里按稳定步骤标识解析步骤引用。

    只认 ``data_version`` 这一份数据：步序、分组和路径引用都从同一版本读取。
    版本不存在或步骤不在该版本里时直接报错，绝不回退到当前活动版本或当前漏斗顺序。
    """
    if not data_version:
        raise ValueError("Funnel result version must be pinned before step attribution")
    if not step_id:
        raise ValueError("Funnel step id is required for attribution")

    artifact = store.get_version_artifact("funnel_analyze", funnel_id, data_version)
    if artifact is not None:
        steps = artifact.get("steps", [])
        step = next((item for item in steps if item.get("step_id") == step_id), None)
        if step is None:
            raise ValueError(
                f"Step {step_id} not found in funnel result {funnel_id}/{data_version}"
            )
        return {
            "funnel_id": funnel_id,
            "data_version": data_version,
            "schema_version": artifact.get("schema_version", RESULT_SCHEMA),
            "funnel_revision": artifact.get("funnel_revision", ""),
            "group_dimension": artifact.get("group_dimension", ""),
            "step_id": step["step_id"],
            "step_index": step["step_index"],
            "step_event_id": step["event_id"],
            "step_name": step.get("step_name", ""),
            "count": step.get("count"),
            "count_source": step.get("count_source", "computed"),
            "group_attribution_available": bool(step.get("group_attribution_available")),
            "group_results": [
                row for row in step.get("group_results", []) if row.get("step_id") == step_id
            ],
            "event_group_totals": [],
        }

    legacy = store.get_legacy_funnel_report(funnel_id, data_version)
    if legacy is None:
        raise ValueError(f"Funnel result version not found: {funnel_id}/{data_version}")

    steps = legacy.get("steps") or []
    step = next((item for item in steps if item.get("step_id") == step_id), None)
    if step is None:
        raise ValueError(f"Step {step_id} not found in legacy report {funnel_id}/{data_version}")

    index = steps.index(step)
    counts = legacy.get("step_counts") or []
    count = counts[index] if index < len(counts) else None
    event_totals = [
        {**row, "source": LEGACY_EVENT_TOTAL_ONLY, "step_attribution_available": False}
        for row in legacy.get("group_results", [])
        if row.get("event_id") == step["event_id"]
    ]
    return {
        "funnel_id": funnel_id,
        "data_version": data_version,
        "schema_version": LEGACY_SCHEMA,
        "funnel_revision": legacy.get("funnel_revision", ""),
        "group_dimension": legacy.get("group_dimension", ""),
        "step_id": step["step_id"],
        "step_index": index + 1,
        "step_event_id": step["event_id"],
        "step_name": step.get("step_name", ""),
        "count": count,
        "count_source": "legacy_step_count" if count is not None else STEP_COUNT_UNAVAILABLE,
        # 历史 v1 分组只有事件合计，不能当作该步骤的分组转化人数
        "group_attribution_available": False,
        "group_results": [],
        "event_group_totals": event_totals,
    }


def check_version_consistency(funnel_id: str, data_version: str) -> dict[str, Any]:
    """核对一个结果版本内部：步序、分组归因与路径引用是否指向同一步骤标识。"""
    artifact = store.get_version_artifact("funnel_analyze", funnel_id, data_version)
    if artifact is None:
        legacy = store.get_legacy_funnel_report(funnel_id, data_version)
        if legacy is None:
            raise ValueError(f"Funnel result version not found: {funnel_id}/{data_version}")
        steps = [
            {**step, "step_index": index}
            for index, step in enumerate(legacy.get("steps") or [], start=1)
        ]
        group_rows = legacy.get("group_results", [])
        return {
            "funnel_id": funnel_id,
            "data_version": data_version,
            "schema_version": LEGACY_SCHEMA,
            "steps": steps,
            "step_order_consistent": all(
                step["step_index"] == index
                for index, step in enumerate(steps, start=1)
            ),
            "group_rows_step_attributed": False,
            "event_group_total_only": True,
            "group_rows": group_rows,
        }

    steps = artifact.get("steps", [])
    group_rows = [
        row
        for step in steps
        for row in step.get("group_results", [])
    ]
    return {
        "funnel_id": funnel_id,
        "data_version": data_version,
        "schema_version": artifact.get("schema_version", RESULT_SCHEMA),
        "steps": [
            {
                "step_id": step["step_id"],
                "step_index": step["step_index"],
                "event_id": step["event_id"],
            }
            for step in steps
        ],
        "step_order_consistent": all(
            step["step_index"] == index for index, step in enumerate(steps, start=1)
        ),
        "group_rows_step_attributed": all(
            row.get("step_id") and row.get("step_index") for row in group_rows
        ),
        "group_row_step_ids": sorted({row.get("step_id") for row in group_rows}),
        "step_ids": [step["step_id"] for step in steps],
        "event_group_total_only": False,
        "group_rows": group_rows,
    }


def compare_funnels(funnel_id_a: str, funnel_id_b: str) -> dict[str, Any]:
    """对比两个漏斗当前活动版本的转化情况。"""
    result_a = get_funnel_result(funnel_id_a)
    result_b = get_funnel_result(funnel_id_b)
    if result_a is None or result_b is None:
        raise ValueError("Funnel result not found")

    return {
        "funnel_a": result_a["funnel_id"],
        "funnel_b": result_b["funnel_id"],
        "version_a": result_a.get("data_version"),
        "version_b": result_b.get("data_version"),
        "step_comparison": [
            {
                "step": i,
                "step_id_a": result_a["steps"][i]["step_id"] if i < len(result_a.get("steps", [])) else None,
                "step_id_b": result_b["steps"][i]["step_id"] if i < len(result_b.get("steps", [])) else None,
                "count_a": (result_a["step_counts"][i] or 0) if i < len(result_a["step_counts"]) else 0,
                "count_b": (result_b["step_counts"][i] or 0) if i < len(result_b["step_counts"]) else 0,
                "rate_a": (result_a["step_rates"][i] or 0) if i < len(result_a["step_rates"]) else 0,
                "rate_b": (result_b["step_rates"][i] or 0) if i < len(result_b["step_rates"]) else 0,
            }
            for i in range(max(len(result_a["step_counts"]), len(result_b["step_counts"])))
        ],
        "total_rate_diff": result_a["total_conversion_rate"] - result_b["total_conversion_rate"],
    }
