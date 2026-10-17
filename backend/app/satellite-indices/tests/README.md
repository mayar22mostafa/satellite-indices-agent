# Tests

All tests run offline: no network and no Earth Engine account.

| File | What it covers |
|---|---|
| `test_registry.py` | Registry lookups, resolutions, reflectance conversion; Pydantic validation rejects bad entries; the registry agrees with the independent textbook definitions used by the reference script |
| `test_aoi.py` | GeoJSON (Feature, FeatureCollection, bare geometry, legacy `crs`), zipped shapefiles (with and without `.prj`), geometry repair, out-of-range coordinates, size limit, clear error messages, the `AOI` model |
| `test_indices.py` | **One test per index formula** (NDVI, NDWI, NDBI) with hand-calculated values; zero denominators, NaN and masked inputs; cloud mask; statistics (population std, valid-pixel %); the README quick-start numbers |
| `test_reference_check.py` | The hand-calculated reference, `compare_to_reference` (including a deliberately wrong pipeline), the Code Editor script generator, the command line |

Run them with `pytest` from the repository root.
