from datetime import date, timedelta

from ai_service.app.analysis import tools
from ai_service.app.analysis.context import RunContext

tools.init_earth_engine()

aoi_id = "cairo_box"
ctx = RunContext()

area = tools.describe_aoi(ctx, aoi_id)
print("AOI:", area)
if "error" in area:
    raise SystemExit(area["error"])

end = date.today()
start = end - timedelta(days=60)

selected = tools.select_image(
    ctx,
    aoi_id,
    start.isoformat(),
    end.isoformat(),
    max_cloud=20,
)
print("IMAGE:", selected)
if "error" in selected:
    raise SystemExit(selected["error"])

result = tools.classify_land_cover(
    ctx,
    selected["image_ref"],
    aoi_id,
)
print("CLASSIFICATION:", result)
if "result_id" in result:
    map_result = tools.create_land_cover_map(ctx, result["result_id"])
    print("MAP:", map_result)
