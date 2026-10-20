"""Fixed pipeline: calls the tools in a fixed order (no agent, no LLM).

Run from the project root:
    python -m backend.app.analysis.pipeline --aoi cairo_box --index NDVI
"""

import argparse
import json
from datetime import date, timedelta

from . import tools
from .context import RunContext


def run_fixed_pipeline(aoi_id: str, index_name: str, start_date: str, end_date: str,
                       max_cloud: float = 20, cloud_mask: bool = True,
                       image_date: str | None = None) -> dict:
    ctx = RunContext()
    steps = {}

    steps["describe_aoi"] = tools.describe_aoi(ctx, aoi_id)
    if "error" in steps["describe_aoi"]:
        return steps

    steps["select_image"] = tools.select_image(ctx, aoi_id, start_date, end_date, max_cloud, date=image_date)
    if "error" in steps["select_image"]:
        return steps
    image_ref = steps["select_image"]["image_ref"]

    steps["compute_index"] = tools.compute_index(ctx, image_ref, aoi_id, index_name, cloud_mask)
    if "error" in steps["compute_index"]:
        return steps
    result_id = steps["compute_index"]["result_id"]

    steps["compute_statistics"] = tools.compute_statistics(ctx, result_id)
    steps["create_map_layer"] = tools.create_map_layer(ctx, result_id)
    return steps


def main() -> None:
    today = date.today()
    parser = argparse.ArgumentParser(description="Compute a satellite index for an area.")
    parser.add_argument("--aoi", default="cairo_box")
    parser.add_argument("--index", default="NDVI")
    parser.add_argument("--start", default=(today - timedelta(days=60)).isoformat())
    parser.add_argument("--end", default=today.isoformat())
    parser.add_argument("--cloud", type=float, default=20)
    parser.add_argument("--date", help="use exactly this image day (YYYY-MM-DD)")
    parser.add_argument("--no-mask", action="store_true", help="skip the cloud mask (for comparison)")
    args = parser.parse_args()

    tools.init_earth_engine()
    result = run_fixed_pipeline(args.aoi, args.index, args.start, args.end, args.cloud,
                                cloud_mask=not args.no_mask, image_date=args.date)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()