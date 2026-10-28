// Configuration and color palettes for Satellite Indices

export const INDICES_CONFIG = {
  NDVI: {
    key: "NDVI",
    name: "NDVI",
    label: "NDVI (vegetation)",
    fullName: "Normalized Difference Vegetation Index",
    description: "Measures vegetation density, health, and canopy vigor.",
    range: [-0.2, 0.8],
    min: -0.2,
    max: 0.8,
    // Colors from Sprint 3 spec: #a50026 -> #f46d43 -> #fee08b -> #d9ef8b -> #66bd63 -> #006837
    palette: ["#a50026", "#f46d43", "#fee08b", "#d9ef8b", "#66bd63", "#006837"],
    ticks: [
      { value: -0.2, label: "-0.2 (Bare/Water)" },
      { value: 0.0, label: "0.0" },
      { value: 0.3, label: "0.3 (Sparse)" },
      { value: 0.8, label: "0.8 (Dense Canopy)" },
    ],
    unit: "",
  },
  NDWI: {
    key: "NDWI",
    name: "NDWI",
    label: "NDWI (water)",
    fullName: "Normalized Difference Water Index",
    description: "Delineates open water features and surface water presence.",
    range: [-0.5, 0.5],
    min: -0.5,
    max: 0.5,
    // Colors from Sprint 3 spec: #8c510a -> #f6e8c3 -> #c7eae5 -> #01665e -> #08306b
    palette: ["#8c510a", "#f6e8c3", "#c7eae5", "#01665e", "#08306b"],
    ticks: [
      { value: -0.5, label: "-0.5 (Dry Soil)" },
      { value: 0.0, label: "0.0 (Moist)" },
      { value: 0.5, label: "0.5 (Deep Water)" },
    ],
    unit: "",
  },
  NDBI: {
    key: "NDBI",
    name: "NDBI",
    label: "NDBI (built-up areas)",
    fullName: "Normalized Difference Built-up Index",
    description: "Highlights impervious surfaces, roads, and built-up infrastructure.",
    range: [-0.5, 0.5],
    min: -0.5,
    max: 0.5,
    // Colors from Sprint 3 spec: #1a9850 -> #ffffbf -> #d73027
    palette: ["#1a9850", "#ffffbf", "#d73027"],
    ticks: [
      { value: -0.5, label: "-0.5 (Vegetation)" },
      { value: 0.0, label: "0.0 (Fallow)" },
      { value: 0.5, label: "0.5 (Built-up)" },
    ],
    unit: "",
  },
};

export const getIndexConfig = (indexName) => {
  const upper = (indexName || "").toUpperCase();
  if (INDICES_CONFIG[upper]) {
    return INDICES_CONFIG[upper];
  }
  // Safe fallback for unknown indices
  return {
    key: upper,
    name: upper,
    label: `${upper}`,
    fullName: upper,
    description: "Satellite spectral index computation.",
    range: [-1, 1],
    min: -1,
    max: 1,
    palette: ["#313695", "#4575b4", "#e0f3f8", "#fee090", "#f46d43", "#a50026"],
    ticks: [
      { value: -1, label: "-1.0" },
      { value: 0, label: "0.0" },
      { value: 1, label: "1.0" },
    ],
    unit: "",
  };
};

export const BASEMAP_TILES = {
  dark: {
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  },
  light: {
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  },
};
