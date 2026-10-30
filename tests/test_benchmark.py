from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "benchmark_archive.py"


def _benchmark_module():
    spec = importlib.util.spec_from_file_location("benchmark_archive", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_synthetic_benchmark_covers_data_paths_and_query_plans(tmp_path: Path):
    benchmark = _benchmark_module()
    result = benchmark.run_benchmark(
        tmp_path / "benchmark", creator_count=3, post_count=12, repeats=2, browser="none"
    )

    assert result["dataset"] == {
        "creators": 3,
        "posts": 12,
        "json_files": 12,
        "synthetic": True,
        "network_requests": 0,
    }
    assert result["timings_ms"]["archive_write"] > 0
    assert result["timings_ms"]["frontend_first_render"] is None
    assert result["timings_ms"]["sqlite"]["list_median"] > 0
    assert result["timings_ms"]["reader"]["list_median"] > 0
    assert result["static_index"]["first_rendered"] >= 12
    assert result["static_index"]["reuse_reused"] >= 12
    assert set(result["query_plans"]) == {"list", "creator_list", "search"}
    assert all(result["query_plans"].values())
    assert any("idx_posts_published" in step for step in result["query_plans"]["list"])
    assert not any("TEMP B-TREE" in step for step in result["query_plans"]["list"])
    assert (tmp_path / "benchmark" / "benchmark.json").is_file()
