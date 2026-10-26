/**
 * Utilities for geodesic area calculations and GeoJSON conversion.
 */

/**
 * Calculates the approximate geodesic area of a polygon on Earth in square kilometers.
 * Uses the spherical excess formula for geographical coordinates (WGS84 sphere).
 * 
 * @param {Array<[number, number]>} coords - Array of coordinate pairs.
 * @param {boolean} isGeoJSON - True if format is [lng, lat], false if [lat, lng].
 * @returns {number} Area in km² rounded to 2 decimal places.
 */
export const calculatePolygonAreaKm2 = (coords, isGeoJSON = false) => {
  if (!Array.isArray(coords) || coords.length < 3) return 0;

  // Convert all coordinates to [lat, lng]
  const points = coords.map((c) => (isGeoJSON ? [c[1], c[0]] : [c[0], c[1]]));

  // If the polygon is closed (last point == first point), drop the duplicate closing point for the formula
  if (
    points.length > 3 &&
    points[0][0] === points[points.length - 1][0] &&
    points[0][1] === points[points.length - 1][1]
  ) {
    points.pop();
  }

  if (points.length < 3) return 0;

  const R = 6378137; // Earth mean radius in meters (WGS84)
  const toRad = (deg) => (deg * Math.PI) / 180;
  let total = 0;

  for (let i = 0; i < points.length; i++) {
    const prev = points[(i - 1 + points.length) % points.length];
    const next = points[(i + 1) % points.length];
    const curr = points[i];

    const dLng = toRad(next[1] - prev[1]);
    total += dLng * Math.sin(toRad(curr[0]));
  }

  const areaM2 = Math.abs((total * R * R) / 2);
  const areaKm2 = areaM2 / 1000000;
  return Math.round(areaKm2 * 100) / 100;
};

/**
 * Creates a valid GeoJSON Feature with a closed Polygon geometry.
 * 
 * @param {Array<[number, number]>} coords - Array of vertices ([lng, lat] or [lat, lng])
 * @param {string} [name="User Defined Area"]
 * @param {boolean} [isLngLat=true] - True if input coordinates are [lng, lat], false if [lat, lng]
 * @returns {object|null} GeoJSON Feature object
 */
export const createGeoJSONPolygonFeature = (
  coords,
  name = "User Defined Area",
  isLngLat = true,
) => {
  if (!Array.isArray(coords) || coords.length < 3) return null;

  // GeoJSON requires coordinates in [longitude, latitude] format
  const ring = coords.map((c) => {
    const lng = isLngLat ? c[0] : c[1];
    const lat = isLngLat ? c[1] : c[0];
    return [
      parseFloat(Number(lng).toFixed(6)),
      parseFloat(Number(lat).toFixed(6)),
    ];
  });

  // GeoJSON Polygon must be closed (first and last coordinate identical)
  const first = ring[0];
  const last = ring[ring.length - 1];
  if (first[0] !== last[0] || first[1] !== last[1]) {
    ring.push([first[0], first[1]]);
  }

  const areaKm2 = calculatePolygonAreaKm2(ring, true);

  return {
    type: "Feature",
    properties: {
      name,
      area_km2: areaKm2,
      source: "map_selection",
      created_at: new Date().toISOString(),
    },
    geometry: {
      type: "Polygon",
      coordinates: [ring],
    },
  };
};

/**
 * Wraps a GeoJSON object into a File object acceptable by the backend file upload.
 * 
 * @param {object} geojson - The GeoJSON Feature object
 * @param {string} [filename="map-selection.geojson"]
 * @returns {File}
 */
export const createGeoJSONFile = (geojson, filename = "map-selection.geojson") => {
  const jsonString = JSON.stringify(geojson, null, 2);
  const blob = new Blob([jsonString], { type: "application/geo+json" });
  return new File([blob], filename, { type: "application/geo+json" });
};
