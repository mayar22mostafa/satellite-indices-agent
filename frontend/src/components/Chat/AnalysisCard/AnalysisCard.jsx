import { useState } from "react";
import { getIndexConfig } from "../../../config/indices";
import MapModal from "../../Map/MapModal";
import styles from "./AnalysisCard.module.css";

const AnalysisCard = ({ message }) => {
  const [selectedMapIndex, setSelectedMapIndex] = useState(null);
  const [imgErrors, setImgErrors] = useState({});

  const properties =
    message.properties ||
    message.feature?.properties ||
    message.results ||
    {};

  const results = properties.results || message.results || {};
  const errors = properties.errors || {};
  const explanation = properties.explanation || message.explanation;

  const resultsEntries = Object.entries(results);

  const handleImageError = (indexKey) => {
    setImgErrors((prev) => ({ ...prev, [indexKey]: true }));
  };

  const handleOpenMap = (indexKey, indexData) => {
    setSelectedMapIndex({
      indexName: indexKey,
      tileUrl: indexData.create_map_layer?.tile_url,
      bounds: indexData.create_map_layer?.bounds,
      metadata: {
        date: indexData.select_image?.date,
        area_km2: indexData.describe_aoi?.area_km2,
      },
    });
  };

  const handleCloseMap = () => {
    setSelectedMapIndex(null);
  };

  return (
    <div className={styles.container} role="region" aria-label="Analysis Results">
      {/* 1. Text Summary / Explanation */}
      {explanation && (
        <div className={styles.explanationBox}>
          <div className={styles.explanationHeader}>
            <i className="fa-solid fa-wand-magic-sparkles"></i>
            <span>Agent Analysis Summary</span>
          </div>
          <p className={styles.explanationText} dir="auto">
            {explanation}
          </p>
        </div>
      )}

      {/* 2. Results per Index */}
      {resultsEntries.map(([indexKey, data]) => {
        const config = getIndexConfig(indexKey);
        const aoi = data.describe_aoi || {};
        const image = data.select_image || {};
        const stats = data.compute_statistics || {};
        const mapLayer = data.create_map_layer || {};

        // Calculate visual position of mean marker on gradient track
        const minVal = stats.min ?? config.min;
        const maxVal = stats.max ?? config.max;
        const meanVal = stats.mean ?? (minVal + maxVal) / 2;
        const rangeSpan = maxVal - minVal || 1;
        const markerPercent = Math.max(
          0,
          Math.min(100, ((meanVal - minVal) / rangeSpan) * 100),
        );

        const gradientString = `linear-gradient(to right, ${config.palette.join(", ")})`;
        const hasImgError = imgErrors[indexKey];

        const warnings = aoi.warnings || [];
        const isRepaired = aoi.repaired;

        return (
          <div key={indexKey} className={styles.indexCard}>
            <div className={styles.cardHeader}>
              <div className={styles.titleArea}>
                <div className={styles.iconBadge} aria-hidden="true">
                  <i className="fa-solid fa-satellite-dish"></i>
                </div>
                <div>
                  <h3 className={styles.indexTitle}>{config.label}</h3>
                  <span className={styles.indexSub}>{config.fullName}</span>
                </div>
              </div>

              <div className={styles.metaChips}>
                <span className={styles.chip}>
                  <i className="fa-solid fa-database"></i>
                  Sentinel-2 (Level-2A, 10 m)
                </span>
                {image.date && (
                  <span className={styles.chip}>
                    <i className="fa-solid fa-calendar-check"></i>
                    Image used: {image.date}
                  </span>
                )}
                {aoi.area_km2 !== undefined && (
                  <span className={styles.chip}>
                    <i className="fa-solid fa-draw-polygon"></i>
                    Area: {aoi.area_km2} km²
                  </span>
                )}
              </div>
            </div>

            <div className={styles.cardBody}>
              {/* Preview Column */}
              <div className={styles.previewColumn}>
                <div className={styles.previewWrapper}>
                  {mapLayer.preview_url && !hasImgError ? (
                    <img
                      src={mapLayer.preview_url}
                      alt={`${indexKey} preview`}
                      className={styles.previewImg}
                      onError={() => handleImageError(indexKey)}
                    />
                  ) : (
                    <div className={styles.fallbackPreview}>
                      <i className="fa-solid fa-image-slash fs-4"></i>
                      <span>
                        {hasImgError
                          ? "Preview expired or unavailable"
                          : "No static preview"}
                      </span>
                      <small className="text-muted">
                        Use the interactive map to view live tiles
                      </small>
                    </div>
                  )}
                </div>

                <button
                  type="button"
                  className={styles.expandBtn}
                  onClick={() => handleOpenMap(indexKey, data)}
                  aria-label={`Expand ${indexKey} Interactive Map`}
                >
                  <i className="fa-solid fa-up-right-and-down-left-from-center"></i>
                  Expand map
                </button>
              </div>

              {/* Statistics Column */}
              <div className={styles.statsColumn}>
                <div className={styles.gradientBarSection}>
                  <div className={styles.barHeader}>
                    <span>Mean Value Position</span>
                    <span className={styles.meanValueHighlight}>
                      {stats.mean !== undefined ? stats.mean.toFixed(2) : "N/A"}
                    </span>
                  </div>

                  <div className={styles.barTrackWrapper}>
                    <div
                      className={styles.barTrack}
                      style={{ background: gradientString }}
                      aria-hidden="true"
                    ></div>
                    {stats.mean !== undefined && (
                      <div
                        className={styles.meanMarker}
                        style={{ left: `${markerPercent}%` }}
                        title={`Mean: ${stats.mean}`}
                      >
                        <div className={styles.markerPin}></div>
                      </div>
                    )}
                  </div>

                  <div className={styles.barRangeLabels}>
                    <span>Min: {stats.min !== undefined ? stats.min : minVal}</span>
                    <span>Max: {stats.max !== undefined ? stats.max : maxVal}</span>
                  </div>
                </div>

                <div className={styles.statsGrid}>
                  <div className={styles.statItem}>
                    <span className={styles.statLabel}>Min Value</span>
                    <span className={styles.statVal}>
                      {stats.min !== undefined ? stats.min.toFixed(2) : "—"}
                    </span>
                  </div>

                  <div className={styles.statItem}>
                    <span className={styles.statLabel}>Max Value</span>
                    <span className={styles.statVal}>
                      {stats.max !== undefined ? stats.max.toFixed(2) : "—"}
                    </span>
                  </div>

                  <div className={styles.statItem}>
                    <span className={styles.statLabel}>Valid Pixels</span>
                    <span className={styles.statVal}>
                      {stats.valid_pixel_pct !== undefined
                        ? `${stats.valid_pixel_pct}%`
                        : "100%"}
                    </span>
                  </div>

                  <div className={styles.statItem}>
                    <span className={styles.statLabel}>Resolution</span>
                    <span className={styles.statVal}>
                      {stats.pixel_size_m ? `${stats.pixel_size_m} m` : "10 m"}
                    </span>
                  </div>
                </div>

                {(warnings.length > 0 || isRepaired) && (
                  <div className={styles.warningsBox} role="alert">
                    <i className="fa-solid fa-triangle-exclamation"></i>
                    <div>
                      {isRepaired && (
                        <div>AOI geometry was self-intersecting and automatically repaired.</div>
                      )}
                      {warnings.map((w, idx) => (
                        <div key={idx}>{w}</div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}

      {/* Errors per index if any */}
      {Object.entries(errors).map(([idx, err]) => (
        <div key={idx} className="alert alert-warning small py-2 px-3 mb-0" role="alert">
          <i className="fa-solid fa-triangle-exclamation me-2"></i>
          <strong>{idx}:</strong> {typeof err === "string" ? err : JSON.stringify(err)}
        </div>
      ))}

      {/* OpenLayers Map Modal */}
      {selectedMapIndex && (
        <MapModal
          isOpen={Boolean(selectedMapIndex)}
          onClose={handleCloseMap}
          indexName={selectedMapIndex.indexName}
          tileUrl={selectedMapIndex.tileUrl}
          bounds={selectedMapIndex.bounds}
          metadata={selectedMapIndex.metadata}
        />
      )}
    </div>
  );
};

export default AnalysisCard;
