"""行为路径分析引擎：构建用户行为路径的Sankey图数据。"""
from __future__ import annotations

from typing import Any
from collections import defaultdict, Counter

from app.store import store
from app.schemas import PathResult


def _generate_path_events(start_event: str, target_event: str, count: int) -> list[dict[str, Any]]:
    """生成模拟路径事件数据。"""
    events = []
    base_time = 1700000000
    for user_idx in range(1, count + 1):
        user_id = f"U{user_idx:05d}"
        # 生成随机深度的路径
        path_len = 3 + (user_idx % 4)
        for step in range(path_len):
            if step == 0:
                event_id = start_event
            elif step == path_len - 1 and user_idx % 3 == 0:
                event_id = target_event
            else:
                event_id = ["EV-001", "EV-002", "EV-003", "EV-004"][(user_idx + step) % 4]
            events.append({
                "user_id": user_id,
                "event_id": event_id,
                "timestamp": base_time + user_idx * 1000 + step * 200,
                "session_id": f"S{user_idx:03d}",
            })
    return sorted(events, key=lambda x: (x["user_id"], x["timestamp"]))


def build_path_sankey(model_id: str) -> PathResult:
    """构建行为路径的Sankey数据。"""
    model = store.find_by_field("behavior_path", "model_id", model_id)
    if model is None:
        raise ValueError(f"Path model not found: {model_id}")

    start_event = model["start_event"]
    target_event = model["target_event"]
    time_window = model.get("time_window", 86400)
    path_depth = model.get("path_depth", 5)
    path_filter = model.get("path_filter", "")

    # 漏斗归因：路径固定读取模型登记的漏斗结果版本，按稳定步骤标识取步序与分组，
    # 不读取“当前活动版本”，避免切换/回滚期间路径引用与步序落到不同数据版本。
    funnel_attribution = None
    funnel_id = model.get("funnel_id", "")
    funnel_result_version = model.get("funnel_result_version", "")
    funnel_step_id = model.get("funnel_step_id", "")
    if funnel_id and funnel_result_version and funnel_step_id:
        from app.services.funnel_analyze import resolve_step_reference

        try:
            funnel_attribution = resolve_step_reference(
                funnel_id, funnel_result_version, funnel_step_id
            )
        except ValueError as error:
            raise ValueError(f"Funnel step attribution invalid: {error}") from error

    events = _generate_path_events(start_event, target_event, 200)

    # 按用户分组构建路径
    user_paths: dict[str, list[str]] = defaultdict(list)
    for e in events:
        user_paths[e["user_id"]].append(e["event_id"])

    # 统计路径转换
    edge_counts: dict[tuple[str, str], int] = defaultdict(int)
    node_counts: Counter[str] = Counter()
    conversion_paths: list[list[str]] = []
    total_conversions = 0

    for user_id, path in user_paths.items():
        # 限制路径深度
        path = path[:path_depth]
        if len(path) < 2:
            continue

        # 统计节点
        for node in path:
            node_counts[node] += 1

        # 统计边
        for i in range(len(path) - 1):
            edge = (path[i], path[i + 1])
            edge_counts[edge] += 1

        # 检查是否到达目标
        if target_event in path:
            conversion_paths.append(path)
            total_conversions += 1

    # 构建Sankey节点
    nodes = []
    node_index: dict[str, int] = {}
    for node, count in sorted(node_counts.items(), key=lambda x: -x[1]):
        node_index[node] = len(nodes)
        nodes.append({
            "name": node,
            "value": count,
            "category": _get_event_category(node),
        })

    # 构建Sankey边
    links = []
    for (source, target), count in sorted(edge_counts.items(), key=lambda x: -x[1]):
        if source in node_index and target in node_index:
            links.append({
                "source": node_index[source],
                "target": node_index[target],
                "value": count,
                "source_name": source,
                "target_name": target,
            })

    result = PathResult(
        model_id=model_id,
        start_event=start_event,
        target_event=target_event,
        sankey_nodes=nodes,
        sankey_links=links,
        conversion_paths=conversion_paths[:50],
        total_conversions=total_conversions,
        funnel_step_attribution=funnel_attribution,
    )

    # 存储产物
    store.set_artifact("behavior_path", model_id, result.model_dump())

    # 更新状态
    store.update("behavior_path", model["id"], {
        "status": "已完成",
        "pending": False,
    })

    return result


def _get_event_category(event_id: str) -> str:
    """获取事件分类。"""
    event = store.find_by_field("event_track", "event_id", event_id)
    if event:
        return event.get("category", "unknown")
    return "unknown"


def get_path_result(model_id: str) -> dict[str, Any] | None:
    """获取路径分析结果。"""
    artifact = store.get_artifact("behavior_path", model_id)
    if artifact:
        return artifact
    try:
        result = build_path_sankey(model_id)
        return result.model_dump()
    except ValueError:
        return None


def find_common_paths(model_id: str, min_count: int = 3) -> list[dict[str, Any]]:
    """查找高频路径模式。"""
    result = get_path_result(model_id)
    if result is None:
        return []

    path_counter: Counter[tuple[str, ...]] = Counter()
    for path in result.get("conversion_paths", []):
        path_counter[tuple(path)] += 1

    return [
        {"path": list(path), "count": count}
        for path, count in path_counter.most_common(20)
        if count >= min_count
    ]
