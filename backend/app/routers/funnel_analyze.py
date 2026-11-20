"""漏斗分析路由：执行漏斗计算、管理结果版本并读取历史报告。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.schemas import ActionPayload, ActionResult
from app.services.funnel_analyze import (
    analyze_funnel,
    check_version_consistency,
    compare_funnels,
    get_funnel_result,
    get_funnel_result_version,
    get_legacy_funnel_report,
    list_funnel_versions,
    migrate_funnel_result,
    resolve_step_reference,
    rollback_funnel_version,
    switch_funnel_version,
    update_funnel_steps,
)
from app.store import store

router = APIRouter(prefix="/api/funnel-analyze", tags=["funnel_analyze"])


@router.get("")
def index(page: int = 1, size: int = 20) -> dict[str, Any]:
    rows = store.rows("funnel_analyze")
    total = len(rows)
    start = (page - 1) * size
    return {"items": rows[start : start + size], "total": total, "page": page, "size": size}




@router.get("/export")
def export_entries() -> dict[str, Any]:
    rows = store.rows("funnel_analyze")
    return {"items": rows, "total": len(rows)}


@router.get("/legacy/{funnel_id}")
def legacy_report(funnel_id: str, version: str | None = None) -> dict[str, Any]:
    """读取历史 v1 报告；分组明细保持事件合计口径。"""
    report = get_legacy_funnel_report(funnel_id, version)
    if report is None:
        raise HTTPException(status_code=404, detail="Legacy report not found")
    return report


@router.get("/{funnel_id}/versions")
def versions(funnel_id: str) -> dict[str, Any]:
    """列出漏斗结果的所有数据版本与活动版本。"""
    return list_funnel_versions(funnel_id)


@router.get("/{funnel_id}/versions/{version}")
def version_result(funnel_id: str, version: str) -> dict[str, Any]:
    """按显式版本号读取结果；历史报告走这里，不随活动版本变化。"""
    res = get_funnel_result_version(funnel_id, version)
    if res is None:
        raise HTTPException(status_code=404, detail="Result version not found")
    return res


@router.get("/{funnel_id}/versions/{version}/consistency")
def version_consistency(funnel_id: str, version: str) -> dict[str, Any]:
    """核对一个结果版本内步序、分组归因与步骤标识是否一致。"""
    try:
        return check_version_consistency(funnel_id, version)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{funnel_id}/versions/{version}/steps/{step_id}")
def version_step(funnel_id: str, version: str, step_id: str) -> dict[str, Any]:
    """按稳定步骤标识在指定结果版本里读取步序与分组归因。"""
    try:
        return resolve_step_reference(funnel_id, version, step_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{funnel_id}/steps")
def update_steps(funnel_id: str, payload: dict[str, Any]) -> ActionResult:
    """调整漏斗步骤或步序；旧定义归档为修订快照，供历史报告和迁移使用。"""
    try:
        result = update_funnel_steps(
            funnel_id,
            payload.get("step_defs") or [],
            revision=payload.get("revision"),
            note=payload.get("note", ""),
        )
        return ActionResult(ok=True, message="StepsUpdated", entry=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{funnel_id}/migrate")
def migrate(funnel_id: str, source_version: str, target_version: str | None = None, activate: bool = True) -> ActionResult:
    """把历史 v1 报告迁移成带稳定步骤标识的第 2 版本结果。"""
    try:
        result = migrate_funnel_result(
            funnel_id, source_version, target_version=target_version, activate=activate
        )
        return ActionResult(ok=True, message="Migrated", entry=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{funnel_id}/switch")
def switch(funnel_id: str, version: str, reason: str = "switch") -> ActionResult:
    """切换活动结果版本；整体移动指针，不覆盖旧版本。"""
    try:
        result = switch_funnel_version(funnel_id, version, reason)
        return ActionResult(ok=True, message="Switched", entry=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{funnel_id}/rollback")
def rollback(funnel_id: str, version: str, reason: str = "rollback") -> ActionResult:
    """回滚到指定结果版本；各版本数据保持不变。"""
    try:
        result = rollback_funnel_version(funnel_id, version, reason)
        return ActionResult(ok=True, message="RolledBack", entry=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{entry_id}")
def detail(entry_id: int) -> dict[str, Any]:
    row = store.find("funnel_analyze", entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row


@router.post("/{funnel_id}/run")
def run(funnel_id: str, data_version: str | None = None) -> ActionResult:
    try:
        result = analyze_funnel(funnel_id, data_version=data_version)
        return ActionResult(ok=True, message="Analyzed", entry=result.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{funnel_id}/result")
def result(funnel_id: str) -> dict[str, Any]:
    res = get_funnel_result(funnel_id)
    if res is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return res


@router.get("/compare/{funnel_id_a}/{funnel_id_b}")
def compare(funnel_id_a: str, funnel_id_b: str) -> dict[str, Any]:
    try:
        return compare_funnels(funnel_id_a, funnel_id_b)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{entry_id}/actions")
def run_action(entry_id: int, payload: ActionPayload) -> ActionResult:
    row = store.find("funnel_analyze", entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    action = payload.action
    row["status"] = action
    row["pending"] = False
    return ActionResult(ok=True, message=action, entry=row)
