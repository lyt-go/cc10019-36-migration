"""行为路径路由：构建路径Sankey并获取分析结果。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.schemas import ActionPayload, ActionResult
from app.services.behavior_path import build_path_sankey, get_path_result, find_common_paths
from app.store import store

router = APIRouter(prefix="/api/behavior-path", tags=["behavior_path"])


@router.get("")
def index(page: int = 1, size: int = 20) -> dict[str, Any]:
    rows = store.rows("behavior_path")
    total = len(rows)
    start = (page - 1) * size
    items = rows[start : start + size]
    # 路径页面按“模型 → 起止事件”渲染拓扑；漏斗归因字段随节点一起下发，
    # 节点被选中时按固定的结果版本 + 步骤标识读取归因。
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for row in rows:
        model_node_id = f"model:{row['model_id']}"
        nodes.append({
            "id": model_node_id,
            "name": row["model_id"],
            "label": row.get("model_id"),
            "status": row.get("status"),
            "funnel_id": row.get("funnel_id", ""),
            "funnel_result_version": row.get("funnel_result_version", ""),
            "funnel_step_id": row.get("funnel_step_id", ""),
        })
        for key, event_id in (("from", row.get("start_event")), ("to", row.get("target_event"))):
            if not event_id:
                continue
            event_node_id = f"event:{event_id}"
            if not any(node["id"] == event_node_id for node in nodes):
                nodes.append({
                    "id": event_node_id,
                    "name": event_id,
                    "label": event_id,
                    "status": "事件",
                })
            edges.append({"from": model_node_id, "to": event_node_id, "label": key})
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "nodes": nodes,
        "edges": edges,
    }




@router.get("/export")
def export_entries() -> dict[str, Any]:
    rows = store.rows("behavior_path")
    return {"items": rows, "total": len(rows)}
@router.get("/{entry_id}")
def detail(entry_id: int) -> dict[str, Any]:
    row = store.find("behavior_path", entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row


@router.post("/{model_id}/build")
def build(model_id: str) -> ActionResult:
    try:
        result = build_path_sankey(model_id)
        return ActionResult(ok=True, message="Built", entry=result.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{model_id}/result")
def result(model_id: str) -> dict[str, Any]:
    res = get_path_result(model_id)
    if res is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return res


@router.get("/{model_id}/common-paths")
def common_paths(model_id: str, min_count: int = 3) -> list[dict[str, Any]]:
    return find_common_paths(model_id, min_count)


@router.post("/{entry_id}/actions")
def run_action(entry_id: int, payload: ActionPayload) -> ActionResult:
    row = store.find("behavior_path", entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    action = payload.action
    row["status"] = action
    row["pending"] = False
    return ActionResult(ok=True, message=action, entry=row)
