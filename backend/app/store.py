"""内存数据仓库：支持跨模块数据消费、版本快照和关联查询。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from typing import Any

from app.seed import LEGACY_FUNNEL_REPORTS, SEED_ROWS


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }
        # 历史 v1 报告单独存放：只读、带自己的修订快照，不参与当前版本的切换
        self._legacy_funnel_reports: dict[str, dict[str, dict[str, Any]]] = {
            funnel_id: {report["data_version"]: dict(report) for report in reports}
            for funnel_id, reports in LEGACY_FUNNEL_REPORTS.items()
        }
        # 数据产物存储：跨模块共享的数据结果
        self._artifacts: dict[str, dict[str, Any]] = {}
        # 版本化产物：同一产物的多个数据版本必须同时保留，切换/回滚只移动活动指针，
        # 不覆盖历史版本，避免步序、分组和路径引用读到不同版本的数据。
        self._artifact_versions: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
        self._active_versions: dict[tuple[str, str], str] = {}
        self._version_events: dict[tuple[str, str], list[dict[str, Any]]] = {}
        # 版本快照
        self._snapshots: dict[str, list[dict[str, Any]]] = {}
        # 计算结果缓存
        self._compute_cache: dict[str, dict[str, Any]] = {}
        # 下一个自增ID
        self._next_ids: dict[str, int] = {
            name: max((int(row.get("id", 0)) for row in self._tables[name]), default=0) + 1
            for name in self._tables
        }

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def find_by_field(self, module: str, field: str, value: Any) -> dict[str, Any] | None:
        for row in self.rows(module):
            if row.get(field) == value:
                return row
        return None

    def find_all_by_field(self, module: str, field: str, value: Any) -> list[dict[str, Any]]:
        return [row for row in self.rows(module) if row.get(field) == value]

    def insert(self, module: str, row: dict[str, Any]) -> dict[str, Any]:
        """插入一条记录并分配自增ID。"""
        if "id" not in row:
            row["id"] = self._next_ids.get(module, 1)
            self._next_ids[module] = row["id"] + 1
        self._tables.setdefault(module, []).append(dict(row))
        return row

    def update(self, module: str, entry_id: int, updates: dict[str, Any]) -> dict[str, Any] | None:
        """更新一条记录。"""
        row = self.find(module, entry_id)
        if row is None:
            return None
        row.update(updates)
        return row

    def delete(self, module: str, entry_id: int) -> bool:
        """删除一条记录。"""
        rows = self.rows(module)
        for i, row in enumerate(rows):
            if int(row.get("id", 0)) == entry_id:
                rows.pop(i)
                return True
        return False

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}

    # ========== 数据产物管理 ==========
    def set_artifact(self, artifact_type: str, artifact_id: str, data: dict[str, Any]) -> None:
        """存储跨模块数据产物。"""
        if artifact_type not in self._artifacts:
            self._artifacts[artifact_type] = {}
        self._artifacts[artifact_type][artifact_id] = data

    def get_artifact(self, artifact_type: str, artifact_id: str) -> dict[str, Any] | None:
        """获取跨模块数据产物。"""
        return self._artifacts.get(artifact_type, {}).get(artifact_id)

    def list_artifacts(self, artifact_type: str) -> list[dict[str, Any]]:
        """列出某类型的所有产物。"""
        return list(self._artifacts.get(artifact_type, {}).values())

    def get_artifact_keys(self, artifact_type: str) -> list[str]:
        """获取某类型产物的所有键。"""
        return list(self._artifacts.get(artifact_type, {}).keys())

    # ========== 版本化产物管理 ==========
    # 真实项目里对应“同一业务对象多版本结果表 + 一个活动版本指针”：
    # - 每个版本单独存放，切换只移动活动指针，回滚只是把指针移回旧版本；
    # - 历史报告通过显式版本号读取，不随活动指针变化；
    # - 写入新版本号时拒绝覆盖已存在的版本，避免把旧数据挤出可回滚范围。
    def set_version_artifact(
        self,
        artifact_type: str,
        artifact_id: str,
        version: str,
        data: dict[str, Any],
        *,
        activate: bool = True,
        note: str = "",
    ) -> dict[str, Any]:
        """写入一个版本化产物；可选同时把活动指针指向该版本。"""
        key = (artifact_type, artifact_id)
        versions = self._artifact_versions.setdefault(key, {})
        if version in versions:
            raise ValueError(f"Version already exists: {artifact_type}/{artifact_id}/{version}")
        payload = dict(data)
        payload["data_version"] = version
        versions[version] = payload
        self._version_events.setdefault(key, []).append({
            "event": "publish",
            "version": version,
            "note": note,
        })
        if activate:
            self._active_versions[key] = version
            self._artifacts.setdefault(artifact_type, {})[artifact_id] = versions[version]
        return versions[version]

    def get_version_artifact(
        self, artifact_type: str, artifact_id: str, version: str
    ) -> dict[str, Any] | None:
        """按显式版本号读取产物（历史报告走这里，不受活动版本影响）。"""
        return self._artifact_versions.get((artifact_type, artifact_id), {}).get(version)

    def get_active_version(self, artifact_type: str, artifact_id: str) -> str | None:
        """读取当前活动版本号。"""
        return self._active_versions.get((artifact_type, artifact_id))

    def activate_version(
        self,
        artifact_type: str,
        artifact_id: str,
        version: str,
        *,
        event: str = "activate",
        note: str = "",
    ) -> dict[str, Any] | None:
        """切换活动版本指针；版本不存在时返回 None 且不改变指针。"""
        versions = self._artifact_versions.get((artifact_type, artifact_id), {})
        if version not in versions:
            return None
        key = (artifact_type, artifact_id)
        self._active_versions[key] = version
        self._artifacts.setdefault(artifact_type, {})[artifact_id] = versions[version]
        self._version_events.setdefault(key, []).append({
            "event": event,
            "version": version,
            "note": note,
        })
        return versions[version]

    def list_artifact_versions(self, artifact_type: str, artifact_id: str) -> list[str]:
        """列出某产物已发布的所有版本号（按发布时间顺序）。"""
        return list(self._artifact_versions.get((artifact_type, artifact_id), {}).keys())

    def list_version_events(self, artifact_type: str, artifact_id: str) -> list[dict[str, Any]]:
        """列出某产物的版本切换/发布事件，用于审计切换与回滚顺序。"""
        return list(self._version_events.get((artifact_type, artifact_id), []))

    # ========== 历史 v1 报告（只读） ==========
    def get_legacy_funnel_report(self, funnel_id: str, version: str | None = None) -> dict[str, Any] | None:
        """读取历史 v1 漏斗报告；不传版本时取最新一份。"""
        reports = self._legacy_funnel_reports.get(funnel_id, {})
        if not reports:
            return None
        if version is None:
            return dict(list(reports.values())[-1])
        report = reports.get(version)
        return dict(report) if report else None

    def list_legacy_funnel_reports(self, funnel_id: str) -> list[dict[str, Any]]:
        """列出某漏斗的历史 v1 报告（按登记顺序）。"""
        return [dict(report) for report in self._legacy_funnel_reports.get(funnel_id, {}).values()]

    # ========== 快照管理 ==========
    def add_snapshot(self, snapshot_type: str, data: dict[str, Any]) -> None:
        """添加快照。"""
        self._snapshots.setdefault(snapshot_type, []).append(data)

    def get_latest_snapshot(self, snapshot_type: str) -> dict[str, Any] | None:
        """获取最新快照。"""
        snapshots = self._snapshots.get(snapshot_type, [])
        return snapshots[-1] if snapshots else None

    def list_snapshots(self, snapshot_type: str) -> list[dict[str, Any]]:
        """列出所有快照。"""
        return list(self._snapshots.get(snapshot_type, []))

    # ========== 计算缓存 ==========
    def set_compute_cache(self, cache_key: str, data: dict[str, Any]) -> None:
        """存储计算缓存。"""
        self._compute_cache[cache_key] = data

    def get_compute_cache(self, cache_key: str) -> dict[str, Any] | None:
        """获取计算缓存。"""
        return self._compute_cache.get(cache_key)

    def invalidate_compute_cache(self, prefix: str) -> None:
        """按前缀失效缓存。"""
        keys_to_remove = [k for k in self._compute_cache if k.startswith(prefix)]
        for k in keys_to_remove:
            del self._compute_cache[k]

    # ========== 跨模块关联查询 ==========
    def join(self, left_module: str, right_module: str, left_field: str, right_field: str) -> list[dict[str, Any]]:
        """执行简单的内存join。"""
        results: list[dict[str, Any]] = []
        left_rows = self.rows(left_module)
        right_rows = self.rows(right_module)
        right_index: dict[Any, list[dict[str, Any]]] = {}
        for r in right_rows:
            key = r.get(right_field)
            right_index.setdefault(key, []).append(r)
        for l in left_rows:
            key = l.get(left_field)
            for r in right_index.get(key, []):
                merged = dict(l)
                for rk, rv in r.items():
                    if rk not in merged:
                        merged[rk] = rv
                    else:
                        merged[f"{right_module}.{rk}"] = rv
                results.append(merged)
        return results


def query_filters(request: Any) -> dict[str, Any]:
    """从请求查询参数中提取过滤条件（排除分页字段）。"""
    params = dict(request.query_params)
    return {k: v for k, v in params.items() if k not in ("page", "size")}


store = Store()
