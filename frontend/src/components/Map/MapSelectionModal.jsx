import { useEffect, useRef, useState, useCallback } from "react";
import Map from "ol/Map";
import View from "ol/View";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
import OSM from "ol/source/OSM";
import Draw from "ol/interaction/Draw";
import Feature from "ol/Feature";
import Polygon from "ol/geom/Polygon";
import { fromLonLat } from "ol/proj";
import { getArea } from "ol/sphere";
import { Style, Fill, Stroke, Circle as CircleStyle } from "ol/style";
import "ol/ol.css";
import {
  calculatePolygonAreaKm2,
  createGeoJSONPolygonFeature,
  createGeoJSONFile,
} from "../../utils/geoUtils";
import styles from "./MapSelectionModal.module.css";

// Geographic bounds for Egypt in EPSG:4326 converted to EPSG:3857
const EGYPT_P_MIN = fromLonLat([24.7, 22.0]);
const EGYPT_P_MAX = fromLonLat([36.9, 31.7]);
const EGYPT_EXTENT = [EGYPT_P_MIN[0], EGYPT_P_MIN[1], EGYPT_P_MAX[0], EGYPT_P_MAX[1]];
const EGYPT_CENTER = fromLonLat([30.8, 26.85]);
const DEFAULT_ZOOM = 5.8;

// Style for active drawing
const DRAWING_STYLE = new Style({
  fill: new Fill({ color: "rgba(56, 189, 248, 0.22)" }),
  stroke: new Stroke({ color: "#38bdf8", width: 2, lineDash: [6, 6] }),
  image: new CircleStyle({
    radius: 6,
    fill: new Fill({ color: "#38bdf8" }),
    stroke: new Stroke({ color: "#ffffff", width: 2 }),
  }),
});

// Style for finished polygon
const COMPLETED_STYLE = new Style({
  fill: new Fill({
    color: "rgba(56, 189, 248, 0.28)",
  }),
  stroke: new Stroke({
    color: "#0ea5e9",
    width: 3,
  }),
  image: new CircleStyle({
    radius: 6,
    fill: new Fill({ color: "#38bdf8" }),
    stroke: new Stroke({ color: "#ffffff", width: 2 }),
  }),
});

const MapSelectionModal = ({
  isOpen,
  onClose,
  onConfirm,
  initialCoordinates = null,
}) => {
  const mapContainerRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const baseLayerRef = useRef(null);
  const vectorSourceRef = useRef(null);
  const vectorLayerRef = useRef(null);
  const drawInteractionRef = useRef(null);

  // States
  const [coordinates, setCoordinates] = useState(() =>
    Array.isArray(initialCoordinates) && initialCoordinates.length >= 3
      ? initialCoordinates
      : [],
  );
  const [isClosed, setIsClosed] = useState(
    () =>
      Boolean(
        Array.isArray(initialCoordinates) && initialCoordinates.length >= 3,
      ),
  );
  const [areaKm2, setAreaKm2] = useState(() => {
    if (Array.isArray(initialCoordinates) && initialCoordinates.length >= 3) {
      return calculatePolygonAreaKm2(initialCoordinates, true);
    }
    return 0;
  });
  const [pointsCount, setPointsCount] = useState(() =>
    Array.isArray(initialCoordinates) ? initialCoordinates.length : 0,
  );

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

  // Attach OpenLayers drawing interaction
  const attachDrawInteraction = useCallback((map, source) => {
    if (!map || !source) return;

    if (drawInteractionRef.current) {
      map.removeInteraction(drawInteractionRef.current);
      drawInteractionRef.current = null;
    }

    const draw = new Draw({
      source,
      type: "Polygon",
      style: DRAWING_STYLE,
    });

    draw.on("drawstart", (evt) => {
      setIsClosed(false);
      const geom = evt.feature.getGeometry();
      geom.on("change", (e) => {
        const ring = e.target.getCoordinates()[0];
        if (ring) {
          setPointsCount(ring.length - 1);
          if (ring.length >= 3) {
            const liveAreaM2 = getArea(e.target);
            setAreaKm2(Math.round((liveAreaM2 / 1000000) * 100) / 100);
          }
        }
      });
    });

    draw.on("drawend", (evt) => {
      const geom = evt.feature.getGeometry();
      const areaM2 = getArea(geom);
      const km2 = Math.round((areaM2 / 1000000) * 100) / 100;
      setAreaKm2(km2);
      setIsClosed(true);

      const geom4326 = geom.clone().transform("EPSG:3857", "EPSG:4326");
      const rawCoords = geom4326.getCoordinates()[0] || [];
      const ring = rawCoords.map((pt) => [
        parseFloat(Number(pt[0]).toFixed(6)),
        parseFloat(Number(pt[1]).toFixed(6)),
      ]);

      if (ring.length > 0) {
        const first = ring[0];
        const last = ring[ring.length - 1];
        if (first[0] !== last[0] || first[1] !== last[1]) {
          ring.push([first[0], first[1]]);
        }
      }

      setCoordinates(ring);
      setPointsCount(ring.length);

      map.removeInteraction(draw);
      drawInteractionRef.current = null;
    });

    map.addInteraction(draw);
    drawInteractionRef.current = draw;
  }, []);

  // Undo point handler
  const handleUndo = useCallback(() => {
    if (drawInteractionRef.current && !isClosed) {
      drawInteractionRef.current.removeLastPoint();
      setPointsCount((prev) => Math.max(0, prev - 1));
    }
  }, [isClosed]);

  // Complete polygon handler
  const handleCompletePolygon = useCallback(() => {
    if (drawInteractionRef.current && !isClosed && pointsCount >= 3) {
      drawInteractionRef.current.finishDrawing();
    }
  }, [isClosed, pointsCount]);

  // Clear / Redraw handler
  const handleClear = useCallback(() => {
    if (vectorSourceRef.current) {
      vectorSourceRef.current.clear();
    }
    setCoordinates([]);
    setIsClosed(false);
    setAreaKm2(0);
    setPointsCount(0);

    const map = mapInstanceRef.current;
    const source = vectorSourceRef.current;
    if (map && source) {
      attachDrawInteraction(map, source);
    }
  }, [attachDrawInteraction]);

  // Confirm selection handler - emits coordinates and GeoJSON
  const handleConfirm = useCallback(() => {
    if (!isClosed || coordinates.length < 3) return;

    const geojson = createGeoJSONPolygonFeature(
      coordinates,
      "User Defined AOI",
      true,
    );
    if (!geojson) return;

    const file = createGeoJSONFile(geojson, "map-selection.geojson");
    // GeoJSON Polygon coordinate format: array of rings, each ring an array of [lng, lat] pairs
    const geojsonCoordinates = geojson.geometry.coordinates;
    const ringCoordinates = geojsonCoordinates[0];

    onConfirm({
      file,
      areaKm2,
      geojson,
      coordinates: ringCoordinates,
      geojsonCoordinates,
    });
    onClose();
  }, [isClosed, coordinates, areaKm2, onConfirm, onClose]);

  // Initialize OpenLayers Map with standard OpenStreetMap street layer & clear view of Egypt
  useEffect(() => {
    if (!isOpen || !mapContainerRef.current) return;

    // Standard OpenStreetMap street map tiles: fast, crisp, reliable, no API keys needed
    const baseLayer = new TileLayer({
      source: new OSM(),
    });
    baseLayerRef.current = baseLayer;

    // Vector Source & Layer for drawing polygon
    const vectorSource = new VectorSource();
    vectorSourceRef.current = vectorSource;

    const vectorLayer = new VectorLayer({
      source: vectorSource,
      style: COMPLETED_STYLE,
    });
    vectorLayerRef.current = vectorLayer;

    const view = new View({
      center: EGYPT_CENTER,
      zoom: DEFAULT_ZOOM,
      minZoom: 4,
      maxZoom: 19,
    });

    const map = new Map({
      target: mapContainerRef.current,
      layers: [baseLayer, vectorLayer],
      view,
    });
    mapInstanceRef.current = map;

    // If initial coordinates exist, load them as completed polygon
    if (Array.isArray(initialCoordinates) && initialCoordinates.length >= 3) {
      try {
        const coordsIn3857 = initialCoordinates.map((c) =>
          fromLonLat([c[0], c[1]]),
        );
        const first = coordsIn3857[0];
        const last = coordsIn3857[coordsIn3857.length - 1];
        if (first[0] !== last[0] || first[1] !== last[1]) {
          coordsIn3857.push([first[0], first[1]]);
        }

        const polygonGeom = new Polygon([coordsIn3857]);
        const feature = new Feature({ geometry: polygonGeom });
        vectorSource.addFeature(feature);

        view.fit(polygonGeom.getExtent(), {
          padding: [50, 50, 50, 50],
          duration: 300,
        });
      } catch (err) {
        console.warn("Could not load initial polygon:", err);
      }
    } else {
      // Clear view of Egypt: fit to Egypt's bounds
      view.fit(EGYPT_EXTENT, {
        padding: [30, 30, 30, 30],
        duration: 0,
      });

      // Attach drawing interaction
      attachDrawInteraction(map, vectorSource);
    }

    // Update map size and re-fit view if needed after modal animation
    const resizeTimer = setTimeout(() => {
      map.updateSize();
      if (!initialCoordinates || initialCoordinates.length < 3) {
        view.fit(EGYPT_EXTENT, {
          padding: [30, 30, 30, 30],
          duration: 200,
        });
      }
    }, 150);

    return () => {
      clearTimeout(resizeTimer);
      if (mapInstanceRef.current) {
        mapInstanceRef.current.setTarget(null);
        mapInstanceRef.current = null;
        baseLayerRef.current = null;
        vectorSourceRef.current = null;
        vectorLayerRef.current = null;
        drawInteractionRef.current = null;
      }
    };
  }, [isOpen, initialCoordinates, attachDrawInteraction]);

  if (!isOpen) return null;

  return (
    <div
      className={styles.backdrop}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="map-selection-title"
    >
      <div className={styles.modalDialog} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className={styles.modalHeader}>
          <div className={styles.titleArea}>
            <div className={styles.headerIcon}>
              <i className="fa-solid fa-map-location-dot"></i>
            </div>
            <div>
              <h2 id="map-selection-title" className={styles.modalTitle}>
                Select Area on Map
              </h2>
              <span className={styles.subTitle}>
                Define your Area of Interest (AOI) over Egypt for satellite analysis
              </span>
            </div>
          </div>

          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            aria-label="Close Map Selection"
          >
            <i className="fa-solid fa-xmark"></i>
          </button>
        </div>

        {/* Map Body */}
        <div className={styles.mapContainerWrapper}>
          <div ref={mapContainerRef} className={styles.mapContainer}></div>

          {/* Floating Instruction & Action Bar */}
          <div className={styles.floatingToolbar}>
            <div className={styles.instructionsCard}>
              <i
                className={`fa-solid ${isClosed ? "fa-circle-check" : "fa-crosshairs"
                  } ${styles.instructionsIcon}`}
              ></i>
              <span>
                {isClosed
                  ? `Polygon defined • Area: ${areaKm2} km²`
                  : pointsCount === 0
                    ? "Click on the map to start drawing polygon vertices"
                    : pointsCount < 3
                      ? `Click to place vertex (${pointsCount} placed)`
                      : "Double-click or click starting vertex to close polygon"}
              </span>
            </div>

            <div className={styles.actionButtonGroup}>
              {!isClosed && pointsCount >= 3 && (
                <button
                  type="button"
                  className={`${styles.toolBtn} ${styles.toolBtnPrimary}`}
                  onClick={handleCompletePolygon}
                >
                  <i className="fa-solid fa-check"></i>
                  Complete Polygon
                </button>
              )}

              {pointsCount > 0 && !isClosed && (
                <button
                  type="button"
                  className={styles.toolBtn}
                  onClick={handleUndo}
                >
                  <i className="fa-solid fa-rotate-left"></i>
                  Undo Point
                </button>
              )}

              {(pointsCount > 0 || isClosed) && (
                <button
                  type="button"
                  className={styles.toolBtn}
                  onClick={handleClear}
                >
                  <i className="fa-solid fa-trash-can"></i>
                  Clear / Redraw
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className={styles.modalFooter}>
          <div className={styles.areaSummary}>
            {isClosed && areaKm2 > 0 ? (
              <span className={styles.areaBadge}>
                <i className="fa-solid fa-vector-square"></i>
                Area: {areaKm2} km²
              </span>
            ) : (
              <span className={styles.statusText}>
                {pointsCount === 0
                  ? "No area selected (click on Egypt to start drawing)"
                  : `${pointsCount} vertex placed`}
              </span>
            )}
          </div>

          <div className={styles.footerActions}>
            <button
              type="button"
              className={styles.btnCancel}
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="button"
              className={styles.btnConfirm}
              onClick={handleConfirm}
              disabled={!isClosed || coordinates.length < 3}
            >
              <i className="fa-solid fa-check"></i>
              Confirm Selection
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MapSelectionModal;
