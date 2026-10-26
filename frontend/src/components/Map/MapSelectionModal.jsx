import { useEffect, useRef, useState, useCallback } from "react";
import { useSelector } from "react-redux";
import Map from "ol/Map";
import View from "ol/View";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
import XYZ from "ol/source/XYZ";
import Draw from "ol/interaction/Draw";
import Feature from "ol/Feature";
import Polygon from "ol/geom/Polygon";
import { fromLonLat } from "ol/proj";
import { getArea } from "ol/sphere";
import { Style, Fill, Stroke, Circle as CircleStyle } from "ol/style";
import "ol/ol.css";
import { BASEMAP_TILES } from "../../config/indices";
import { selectThemeMode } from "../../store/themeSlice";
import {
  calculatePolygonAreaKm2,
  createGeoJSONPolygonFeature,
  createGeoJSONFile,
} from "../../utils/geoUtils";
import styles from "./MapSelectionModal.module.css";

const SATELLITE_TILE = {
  url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  attribution:
    "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community",
  maxZoom: 19,
};

const MapSelectionModal = ({
  isOpen,
  onClose,
  onConfirm,
  initialCoordinates = null,
}) => {
  const themeMode = useSelector(selectThemeMode);
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
  const [basemapType, setBasemapType] = useState("carto"); // "carto" | "satellite"

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

    // Re-attach draw interaction if missing
    const map = mapInstanceRef.current;
    if (map && !drawInteractionRef.current) {
      const source = vectorSourceRef.current;
      const draw = new Draw({
        source,
        type: "Polygon",
        style: new Style({
          fill: new Fill({ color: "rgba(56, 189, 248, 0.22)" }),
          stroke: new Stroke({ color: "#38bdf8", width: 2, lineDash: [6, 6] }),
          image: new CircleStyle({
            radius: 6,
            fill: new Fill({ color: "#38bdf8" }),
            stroke: new Stroke({ color: "#ffffff", width: 2 }),
          }),
        }),
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
        const coords = geom4326.getCoordinates()[0];
        setCoordinates(coords);
        setPointsCount(coords.length);

        // Remove active drawing interaction so polygon is locked until clear
        map.removeInteraction(draw);
        drawInteractionRef.current = null;
      });

      map.addInteraction(draw);
      drawInteractionRef.current = draw;
    }
  }, []);

  // Confirm selection handler
  const handleConfirm = useCallback(() => {
    if (!isClosed || coordinates.length < 3) return;

    const geojson = createGeoJSONPolygonFeature(
      coordinates,
      "User Defined AOI",
      true,
    );
    if (!geojson) return;

    const file = createGeoJSONFile(geojson, "map-selection.geojson");
    onConfirm({
      file,
      areaKm2,
      geojson,
      coordinates,
    });
    onClose();
  }, [isClosed, coordinates, areaKm2, onConfirm, onClose]);

  // Initialize OpenLayers Map
  useEffect(() => {
    if (!isOpen || !mapContainerRef.current) return;

    // Default center (Cairo / Egypt: [lon, lat])
    const defaultCenter = fromLonLat([31.2357, 30.0444]);
    const defaultZoom = 6.5;

    // Basemap configuration
    const basemapConfig =
      basemapType === "satellite"
        ? SATELLITE_TILE
        : themeMode === "dark"
          ? BASEMAP_TILES.dark
          : BASEMAP_TILES.light;

    const baseLayer = new TileLayer({
      source: new XYZ({
        url: basemapConfig.url,
        attributions: basemapConfig.attribution,
        maxZoom: basemapConfig.maxZoom || 19,
      }),
    });
    baseLayerRef.current = baseLayer;

    // Vector Source & Layer for drawing
    const vectorSource = new VectorSource();
    vectorSourceRef.current = vectorSource;

    const vectorLayer = new VectorLayer({
      source: vectorSource,
      style: new Style({
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
      }),
    });
    vectorLayerRef.current = vectorLayer;

    const view = new View({
      center: defaultCenter,
      zoom: defaultZoom,
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
        const coordsIn3857 = initialCoordinates.map((c) => fromLonLat([c[0], c[1]]));
        const first = coordsIn3857[0];
        const last = coordsIn3857[coordsIn3857.length - 1];
        if (first[0] !== last[0] || first[1] !== last[1]) {
          coordsIn3857.push([first[0], first[1]]);
        }

        const polygonGeom = new Polygon([coordsIn3857]);
        const feature = new Feature({ geometry: polygonGeom });
        vectorSource.addFeature(feature);

        view.fit(polygonGeom.getExtent(), {
          padding: [40, 40, 40, 40],
          duration: 300,
        });
      } catch (err) {
        console.warn("Could not load initial polygon:", err);
      }
    } else {
      // Create and attach Draw interaction
      const draw = new Draw({
        source: vectorSource,
        type: "Polygon",
        style: new Style({
          fill: new Fill({ color: "rgba(56, 189, 248, 0.22)" }),
          stroke: new Stroke({ color: "#38bdf8", width: 2, lineDash: [6, 6] }),
          image: new CircleStyle({
            radius: 6,
            fill: new Fill({ color: "#38bdf8" }),
            stroke: new Stroke({ color: "#ffffff", width: 2 }),
          }),
        }),
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
        const coords = geom4326.getCoordinates()[0];
        setCoordinates(coords);
        setPointsCount(coords.length);

        map.removeInteraction(draw);
        drawInteractionRef.current = null;
      });

      map.addInteraction(draw);
      drawInteractionRef.current = draw;
    }

    // Update sizing after modal animation
    const resizeTimer = setTimeout(() => {
      map.updateSize();
    }, 200);

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
  }, [isOpen, basemapType, themeMode, initialCoordinates]);

  // Dynamically switch basemap tile style when theme or basemapType changes
  useEffect(() => {
    if (!mapInstanceRef.current || !baseLayerRef.current) return;

    const basemapConfig =
      basemapType === "satellite"
        ? SATELLITE_TILE
        : themeMode === "dark"
          ? BASEMAP_TILES.dark
          : BASEMAP_TILES.light;

    baseLayerRef.current.setSource(
      new XYZ({
        url: basemapConfig.url,
        attributions: basemapConfig.attribution,
        maxZoom: basemapConfig.maxZoom || 19,
      }),
    );
  }, [basemapType, themeMode]);

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
              <i className="fa-solid fa-draw-polygon"></i>
            </div>
            <div>
              <h2 id="map-selection-title" className={styles.modalTitle}>
                Select Area on Map (OpenLayers)
              </h2>
              <span className={styles.subTitle}>
                Define your Area of Interest (AOI) for satellite analysis
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
                className={`fa-solid ${
                  isClosed ? "fa-circle-check" : "fa-crosshairs"
                } ${styles.instructionsIcon}`}
              ></i>
              <span>
                {isClosed
                  ? `Polygon defined • Area: ${areaKm2} km²`
                  : pointsCount === 0
                    ? "Click on the map to start drawing polygon vertices"
                    : pointsCount < 3
                      ? `Click to place vertex (${pointsCount} points)`
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

          {/* Basemap Toggle */}
          <div className={styles.layerToggle}>
            <button
              type="button"
              className={`${styles.layerBtn} ${
                basemapType === "carto" ? styles.layerBtnActive : ""
              }`}
              onClick={() => setBasemapType("carto")}
            >
              <i className="fa-solid fa-map me-1"></i> Standard
            </button>
            <button
              type="button"
              className={`${styles.layerBtn} ${
                basemapType === "satellite" ? styles.layerBtnActive : ""
              }`}
              onClick={() => setBasemapType("satellite")}
            >
              <i className="fa-solid fa-satellite me-1"></i> Satellite
            </button>
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
                  ? "No area selected"
                  : `${pointsCount} point${pointsCount > 1 ? "s" : ""} placed`}
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
