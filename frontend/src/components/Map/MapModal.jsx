import { useEffect, useRef, useState } from "react";
import { useSelector } from "react-redux";
import Map from "ol/Map";
import View from "ol/View";
import TileLayer from "ol/layer/Tile";
import XYZ from "ol/source/XYZ";
import { fromLonLat, transformExtent } from "ol/proj";
import "ol/ol.css";
import { BASEMAP_TILES, getIndexConfig } from "../../config/indices";
import { selectThemeMode } from "../../store/themeSlice";
import styles from "./MapModal.module.css";

const MapModal = ({
  isOpen,
  onClose,
  indexName = "NDVI",
  tileUrl,
  bounds,
  metadata = {},
}) => {
  const themeMode = useSelector(selectThemeMode);
  const mapContainerRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const baseLayerRef = useRef(null);
  const overlayLayerRef = useRef(null);
  const [opacity, setOpacity] = useState(0.85);
  const [initialOpacity] = useState(0.85);
  const [initialTheme] = useState(themeMode);

  const indexConfig = getIndexConfig(indexName);

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Initialize and manage OpenLayers map
  useEffect(() => {
    if (!isOpen || !mapContainerRef.current) return;

    // Default center (Cairo / Egypt: [lon, lat])
    const defaultCenter = fromLonLat([31.2357, 30.0444]);
    const defaultZoom = 7;

    const basemapConfig =
      initialTheme === "dark" ? BASEMAP_TILES.dark : BASEMAP_TILES.light;

    const baseLayer = new TileLayer({
      source: new XYZ({
        url: basemapConfig.url,
        attributions: basemapConfig.attribution,
        maxZoom: basemapConfig.maxZoom || 19,
      }),
    });
    baseLayerRef.current = baseLayer;

    const layers = [baseLayer];

    // Earth Engine overlay layer if tileUrl is present
    if (tileUrl) {
      const overlayLayer = new TileLayer({
        source: new XYZ({
          url: tileUrl,
          maxZoom: 20,
        }),
        opacity: initialOpacity,
      });
      overlayLayerRef.current = overlayLayer;
      layers.push(overlayLayer);
    }

    const view = new View({
      center: defaultCenter,
      zoom: defaultZoom,
    });

    const map = new Map({
      target: mapContainerRef.current,
      layers,
      view,
    });
    mapInstanceRef.current = map;

    // Fit bounds if provided: [[latMin, lonMin], [latMax, lonMax]]
    if (bounds && Array.isArray(bounds) && bounds.length >= 2) {
      try {
        const latMin = bounds[0][0];
        const lonMin = bounds[0][1];
        const latMax = bounds[1][0];
        const lonMax = bounds[1][1];

        const extent = transformExtent(
          [lonMin, latMin, lonMax, latMax],
          "EPSG:4326",
          "EPSG:3857",
        );
        view.fit(extent, {
          padding: [40, 40, 40, 40],
          duration: 300,
        });
      } catch (err) {
        console.warn("Could not fit OpenLayers map bounds:", err);
      }
    }

    // Ensure OpenLayers sizes correctly after modal transition
    const resizeTimer = setTimeout(() => {
      map.updateSize();
    }, 200);

    return () => {
      clearTimeout(resizeTimer);
      if (mapInstanceRef.current) {
        mapInstanceRef.current.setTarget(null);
        mapInstanceRef.current = null;
        baseLayerRef.current = null;
        overlayLayerRef.current = null;
      }
    };
  }, [isOpen, tileUrl, bounds, initialTheme, initialOpacity]);

  // Dynamically switch basemap tile style when theme changes
  useEffect(() => {
    if (!mapInstanceRef.current || !baseLayerRef.current) return;

    const basemapConfig =
      themeMode === "dark" ? BASEMAP_TILES.dark : BASEMAP_TILES.light;

    baseLayerRef.current.setSource(
      new XYZ({
        url: basemapConfig.url,
        attributions: basemapConfig.attribution,
        maxZoom: basemapConfig.maxZoom || 19,
      }),
    );
  }, [themeMode]);

  // Update overlay opacity in real-time
  const handleOpacityChange = (e) => {
    const newOpacity = parseFloat(e.target.value);
    setOpacity(newOpacity);
    if (overlayLayerRef.current) {
      overlayLayerRef.current.setOpacity(newOpacity);
    }
  };

  if (!isOpen) return null;

  // Build gradient CSS string for legend
  const gradientString = `linear-gradient(to right, ${indexConfig.palette.join(", ")})`;

  return (
    <div
      className={styles.backdrop}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="map-modal-title"
    >
      <div
        className={styles.modalDialog}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.modalHeader}>
          <div className={styles.titleArea}>
            <div className="avatar me-2" style={{ color: "#38bdf8" }}>
              <i className="fa-solid fa-map-location-dot fs-5"></i>
            </div>
            <div>
              <h2 id="map-modal-title" className={styles.modalTitle}>
                {indexConfig.label} Map Viewer
              </h2>
              <span className={styles.subTitle}>
                {metadata.date ? `Image used: ${metadata.date}` : "Satellite Layer"}{" "}
                {metadata.area_km2 ? `• Area: ${metadata.area_km2} km²` : ""}
              </span>
            </div>
          </div>

          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            aria-label="Close Map Modal"
          >
            <i className="fa-solid fa-xmark"></i>
          </button>
        </div>

        <div className={styles.mapContainerWrapper}>
          <div ref={mapContainerRef} className={styles.mapContainer}></div>

          {/* Controls Panel (Opacity Slider & Interactive Legend) */}
          <div className={styles.controlsPanel}>
            <div className={styles.controlGroup}>
              <div className={styles.controlLabel}>
                <span>
                  <i className="fa-solid fa-sliders me-1"></i> Layer Opacity
                </span>
                <span>{Math.round(opacity * 100)}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={opacity}
                onChange={handleOpacityChange}
                className={styles.slider}
                aria-label="Satellite layer opacity"
              />
            </div>

            <div className={styles.legendBox}>
              <div className={styles.controlLabel}>
                <span>
                  <i className="fa-solid fa-palette me-1"></i> {indexName} Scale
                </span>
                <span>[{indexConfig.range[0]}, {indexConfig.range[1]}]</span>
              </div>
              <div
                className={styles.legendBar}
                style={{ background: gradientString }}
                aria-hidden="true"
              ></div>
              <div className={styles.legendTicks}>
                {indexConfig.ticks.map((tick, i) => (
                  <span key={i}>{tick.label}</span>
                ))}
              </div>
            </div>
          </div>

          <div className={styles.zoomHint}>
            <i className="fa-solid fa-circle-info"></i>
            Scroll to zoom • Drag to pan • Fitted to AOI bounds
          </div>
        </div>
      </div>
    </div>
  );
};

export default MapModal;
