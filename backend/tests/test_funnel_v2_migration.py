"""漏斗第 2 版本结果数据：迁移、切换、回滚与路径归因一致性测试。

模拟场景：
1. 同一漏斗两个步骤都是商品详情（EV-002），历史分组只记了事件合计；
2. 旧 v1 报告仍供路径查询，运营调换当前漏斗步骤顺序并开始迁移；
3. 验证环境里“切换后、路径取数前回滚”，分别查询历史分组和新报告，
   核对路径引用与步序一致，且历史合计没有被当成某一步的转化数。
"""
from __future__ import annotations

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.store import store
from app.services.behavior_path import build_path_sankey, get_path_result
from app.services.funnel_analyze import (
    LEGACY_EVENT_TOTAL_ONLY,
    analyze_funnel,
    check_version_consistency,
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

FUNNEL_ID = "FN-003"
LEGACY_VERSION = "v1-2026-11-10"
MIGRATED_VERSION = "v2-mig-001"
SWITCHED_VERSION = "v2-order-r2"


def _snapshot_funnel(funnel_id: str) -> dict:
    row = store.find_by_field("funnel_analyze", "funnel_id", funnel_id)
    assert row is not None
    return {
        "id": row["id"],
        "step_defs": [dict(step) for step in row["step_defs"]],
        "step_events": list(row["step_events"]),
        "revision": row["revision"],
        "revision_history": [
            {"revision": item["revision"], "step_defs": [dict(s) for s in item["step_defs"]]}
            for item in row["revision_history"]
        ],
    }


class TestFunnelV2Migration(unittest.TestCase):
    """第 2 版本结果数据与历史 v1 报告的兼容行为。"""

    def setUp(self) -> None:
        store._artifacts.clear()
        store._artifact_versions.clear()
        store._active_versions.clear()
        store._version_events.clear()
        store._compute_cache.clear()

    def test_duplicate_event_steps_have_distinct_step_ids(self) -> None:
        """同一事件的两次步骤靠 step_id 区分，并且第二步人数继续衰减。"""
        result = analyze_funnel(FUNNEL_ID, data_version="v2-seed")
        self.assertEqual([step.event_id for step in result.steps], ["EV-002", "EV-002"])
        self.assertEqual(len({step.step_id for step in result.steps}), 2)
        self.assertEqual([step.step_index for step in result.steps], [1, 2])
        self.assertGreater(result.step_counts[0], result.step_counts[1])
        for step in result.steps:
            for row in step.group_results:
                self.assertEqual(row["step_id"], step.step_id)

    def test_migration_keeps_event_totals_without_splitting(self) -> None:
        """历史分组只有事件合计：迁移后仍按事件合计保留，不变成某一步人数。"""
        migrated = migrate_funnel_result(FUNNEL_ID, LEGACY_VERSION, target_version=MIGRATED_VERSION)

        self.assertEqual([step["step_id"] for step in migrated["steps"]], ["ST-FN003-01", "ST-FN003-02"])
        self.assertEqual([step["step_index"] for step in migrated["steps"]], [1, 2])
        for step in migrated["steps"]:
            self.assertEqual(step["group_results"], [])
            self.assertFalse(step["group_attribution_available"])

        self.assertTrue(migrated["event_group_totals"])
        for row in migrated["event_group_totals"]:
            self.assertEqual(row["source"], LEGACY_EVENT_TOTAL_ONLY)
            self.assertFalse(row["step_attribution_available"])
            self.assertEqual(row["event_step_ids"], ["ST-FN003-01", "ST-FN003-02"])
            self.assertNotEqual(row["count"], migrated["steps"][0]["count"])
            self.assertNotEqual(row["count"], migrated["steps"][1]["count"])

    def test_migration_binds_legacy_step_order_after_current_order_changed(self) -> None:
        """当前漏斗步骤顺序被调换后，迁移仍按历史修订快照绑定步序。"""
        original = _snapshot_funnel(FUNNEL_ID)
        swapped = list(reversed(original["step_defs"]))
        store.update("funnel_analyze", original["id"], {
            "step_defs": swapped,
            "revision": "FN-003-r2",
            "revision_history": original["revision_history"] + [
                {"revision": "FN-003-r2", "step_defs": [dict(step) for step in swapped]}
            ],
        })
        try:
            migrated = migrate_funnel_result(FUNNEL_ID, LEGACY_VERSION, target_version=MIGRATED_VERSION)
            self.assertEqual(
                [step["step_id"] for step in migrated["steps"]],
                ["ST-FN003-01", "ST-FN003-02"],
            )
            self.assertEqual(migrated["funnel_revision"], "FN-003-r1")
            self.assertFalse(migrated["migration"]["step_order_matches_current"])
        finally:
            store.update("funnel_analyze", original["id"], {
                "step_defs": original["step_defs"],
                "step_events": original["step_events"],
                "revision": original["revision"],
                "revision_history": original["revision_history"],
            })

    def test_legacy_report_stays_readable(self) -> None:
        """历史报告仍可读，且分组口径仍标记为事件合计。"""
        legacy = get_legacy_funnel_report(FUNNEL_ID, LEGACY_VERSION)
        self.assertIsNotNone(legacy)
        self.assertEqual(legacy["result_schema"], "v1")
        self.assertEqual(legacy["group_granularity"], "event_total_only")
        self.assertTrue(all(row["event_id"] == "EV-002" for row in legacy["group_results"]))


class TestPathUsesFunnelStepBinding(unittest.TestCase):
    """路径取数只认自己登记的漏斗结果版本，不跟着当前活动版本走。"""

    def setUp(self) -> None:
        store._artifacts.clear()
        store._artifact_versions.clear()
        store._active_versions.clear()
        store._version_events.clear()
        store._compute_cache.clear()

    def test_path_stays_on_pinned_version_when_active_changes(self) -> None:
        migrated = migrate_funnel_result(FUNNEL_ID, LEGACY_VERSION, target_version=MIGRATED_VERSION)
        self.assertEqual([step["step_id"] for step in migrated["steps"]], ["ST-FN003-01", "ST-FN003-02"])
        fresh = analyze_funnel(FUNNEL_ID, data_version="v2-fresh")
        self.assertEqual([step.step_id for step in fresh.steps], ["ST-FN003-01", "ST-FN003-02"])

        attribution = build_path_sankey("BP-001").funnel_step_attribution
        self.assertEqual(attribution["data_version"], LEGACY_VERSION)
        self.assertEqual(attribution["step_index"], 1)

        # 活动版本换成新报告后，路径仍按自己固定的版本取数
        store.activate_version("funnel_analyze", FUNNEL_ID, "v2-fresh")
        self.assertEqual(get_funnel_result(FUNNEL_ID)["data_version"], "v2-fresh")
        again = build_path_sankey("BP-001").funnel_step_attribution
        self.assertEqual(again["data_version"], LEGACY_VERSION)
        self.assertEqual(again["step_index"], 1)

    def test_invalid_step_binding_blocks_path_result(self) -> None:
        # 指向不存在的结果版本时宁可报错，也不退回当前版本或当前步序
        model = store.find_by_field("behavior_path", "model_id", "BP-001")
        original = dict(model)
        store.update("behavior_path", model["id"], {"funnel_result_version": "v2-missing"})
        try:
            with self.assertRaises(ValueError):
                build_path_sankey("BP-001")
            self.assertIsNone(get_path_result("BP-001"))
        finally:
            store.update("behavior_path", model["id"], {
                "funnel_result_version": original["funnel_result_version"],
            })


class TestFunnelVersionSwitchRollback(unittest.TestCase):
    """切换与回滚期间，步序/分组/路径引用必须落在同一数据版本。"""

    def setUp(self) -> None:
        store._artifacts.clear()
        store._artifact_versions.clear()
        store._active_versions.clear()
        store._version_events.clear()
        store._compute_cache.clear()

        self.original = _snapshot_funnel(FUNNEL_ID)
        self.migrated = migrate_funnel_result(
            FUNNEL_ID, LEGACY_VERSION, target_version=MIGRATED_VERSION
        )

        swapped = list(reversed(self.original["step_defs"]))
        store.update("funnel_analyze", self.original["id"], {
            "step_defs": swapped,
            "revision": "FN-003-r2",
            "revision_history": self.original["revision_history"] + [
                {"revision": "FN-003-r2", "step_defs": [dict(step) for step in swapped]}
            ],
        })
        self.switched = analyze_funnel(FUNNEL_ID, data_version=SWITCHED_VERSION)

    def tearDown(self) -> None:
        store.update("funnel_analyze", self.original["id"], {
            "step_defs": self.original["step_defs"],
            "step_events": self.original["step_events"],
            "revision": self.original["revision"],
            "revision_history": self.original["revision_history"],
        })

    def test_switch_then_rollback_before_path_query(self) -> None:
        """切换后、路径取数前回滚：活动结果与旧版本各自保持自己的步序。"""
        switch_funnel_version(FUNNEL_ID, SWITCHED_VERSION)
        self.assertEqual(
            [step["step_id"] for step in get_funnel_result(FUNNEL_ID)["steps"]],
            ["ST-FN003-02", "ST-FN003-01"],
        )

        rollback_funnel_version(FUNNEL_ID, MIGRATED_VERSION)
        active_name = store.get_active_version("funnel_analyze", FUNNEL_ID)
        self.assertEqual(active_name, MIGRATED_VERSION)
        active = get_funnel_result(FUNNEL_ID)
        self.assertEqual(active["data_version"], MIGRATED_VERSION)
        self.assertEqual([step["step_id"] for step in active["steps"]], ["ST-FN003-01", "ST-FN003-02"])

        # 被切换出去的新版本没有被回滚覆盖
        still_there = get_funnel_result_version(FUNNEL_ID, SWITCHED_VERSION)
        self.assertIsNotNone(still_there)
        self.assertEqual(
            [step["step_id"] for step in still_there["steps"]],
            ["ST-FN003-02", "ST-FN003-01"],
        )

        events = [event["event"] for event in list_funnel_versions(FUNNEL_ID)["events"]]
        self.assertEqual(events, ["publish", "publish", "switch", "rollback"])

    def test_path_reference_matches_pinned_version_after_rollback(self) -> None:
        """路径按固定版本读取：回滚前后引用的步序与分组都来自同一版本。"""
        before = build_path_sankey("BP-001").funnel_step_attribution
        switch_funnel_version(FUNNEL_ID, SWITCHED_VERSION)
        rollback_funnel_version(FUNNEL_ID, MIGRATED_VERSION)
        after = build_path_sankey("BP-001").funnel_step_attribution

        self.assertEqual(before["data_version"], LEGACY_VERSION)
        self.assertEqual(after["data_version"], LEGACY_VERSION)
        self.assertEqual(before["step_id"], after["step_id"])
        self.assertEqual(before["step_index"], after["step_index"])
        self.assertEqual(after["step_id"], "ST-FN003-01")
        self.assertEqual(after["step_index"], 1)

        second = build_path_sankey("BP-002").funnel_step_attribution
        self.assertEqual(second["step_id"], "ST-FN003-02")
        self.assertEqual(second["step_index"], 2)

    def test_path_attribution_never_uses_event_total_as_step_count(self) -> None:
        """路径归因读取历史报告时，分组只给事件合计，不冒充步骤人数。"""
        attribution = build_path_sankey("BP-001").funnel_step_attribution
        self.assertFalse(attribution["group_attribution_available"])
        self.assertEqual(attribution["group_results"], [])
        self.assertTrue(attribution["event_group_totals"])
        self.assertEqual(attribution["count"], 600)
        for row in attribution["event_group_totals"]:
            self.assertEqual(row["source"], LEGACY_EVENT_TOTAL_ONLY)
            self.assertFalse(row["step_attribution_available"])

    def test_new_report_groups_are_step_scoped(self) -> None:
        """新报告的分组行必须带 step_id/step_index，并与该版本步序一致。"""
        consistency = check_version_consistency(FUNNEL_ID, SWITCHED_VERSION)
        self.assertTrue(consistency["step_order_consistent"])
        self.assertTrue(consistency["group_rows_step_attributed"])
        self.assertEqual(consistency["step_ids"], ["ST-FN003-02", "ST-FN003-01"])
        self.assertTrue(set(consistency["group_row_step_ids"]) <= set(consistency["step_ids"]))

        # 换序后第一步换成了 ST-FN003-02，分组归因也必须跟着换
        first_step = resolve_step_reference(FUNNEL_ID, SWITCHED_VERSION, "ST-FN003-02")
        self.assertEqual(first_step["step_index"], 1)
        self.assertTrue(first_step["group_results"])
        self.assertTrue(all(row["step_id"] == "ST-FN003-02" for row in first_step["group_results"]))

    def test_step_reference_is_scoped_to_one_version(self) -> None:
        """按版本+步骤标识取数：版本里没有该步骤就报错，不回退当前顺序。"""
        with self.assertRaises(ValueError):
            resolve_step_reference(FUNNEL_ID, SWITCHED_VERSION, "ST-NOT-EXIST")
        with self.assertRaises(ValueError):
            resolve_step_reference(FUNNEL_ID, "v2-not-exist", "ST-FN003-01")
        with self.assertRaises(ValueError):
            resolve_step_reference(FUNNEL_ID, "", "ST-FN003-01")

    def test_legacy_and_new_report_versions_coexist(self) -> None:
        """历史分组与新报告同时可查，各自口径独立。"""
        legacy = get_legacy_funnel_report(FUNNEL_ID, LEGACY_VERSION)
        new = get_funnel_result_version(FUNNEL_ID, SWITCHED_VERSION)
        self.assertEqual(legacy["result_schema"], "v1")
        self.assertEqual(new["schema_version"], "v2")
        self.assertEqual(new["data_version"], SWITCHED_VERSION)
        self.assertTrue(all(row["event_id"] == "EV-002" for row in legacy["group_results"]))
        self.assertFalse(any("step_id" in row for row in legacy["group_results"]))

    def test_step_update_api_archives_previous_revision(self) -> None:
        """通过步骤调整接口换序：旧修订被归档，迁移仍能取到历史步序。"""
        current = store.find_by_field("funnel_analyze", "funnel_id", FUNNEL_ID)
        before = [dict(step) for step in current["step_defs"]]
        swapped = list(reversed(before))
        update = update_funnel_steps(FUNNEL_ID, swapped, revision="FN-003-r3")

        self.assertEqual(update["previous_revision"], "FN-003-r2")
        # setUp 里当前顺序已经是 [02, 01]，这里换回历史顺序 [01, 02]
        self.assertEqual([step["step_id"] for step in update["step_defs"]], ["ST-FN003-01", "ST-FN003-02"])
        revisions = [item["revision"] for item in update["entry"]["revision_history"]]
        self.assertIn("FN-003-r2", revisions)
        self.assertNotIn("FN-003-r3", revisions)

        # 已经发布出去的结果版本不受步骤调整影响
        published = get_funnel_result_version(FUNNEL_ID, MIGRATED_VERSION)
        self.assertEqual(
            [step["step_id"] for step in published["steps"]],
            ["ST-FN003-01", "ST-FN003-02"],
        )

        # 删除仍被历史结果引用的步骤会被拒绝
        with self.assertRaises(ValueError):
            update_funnel_steps(FUNNEL_ID, [update["step_defs"][0]], revision="FN-003-r4")

        # 换序产生的修订快照按历史顺序供迁移使用
        legacy_step_defs = _snapshot_funnel(FUNNEL_ID)
        self.assertEqual(legacy_step_defs["revision"], "FN-003-r3")


if __name__ == "__main__":
    unittest.main(verbosity=2)
