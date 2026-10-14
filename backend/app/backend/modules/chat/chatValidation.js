const gjv = require("geojson-validation");

const chatSchema = require("./chatSchema");

const validateChat = (req, res, next) => {
  const { error } = chatSchema.validate(req.body);

  if (error) {
    return res.status(400).json({
      message: error.details[0].message,
    });
  }

  next();
};

const validateDateSelection = (req, res, next) => {
  const { date, startDate, endDate } = req.body;

  // Case 1: User selected one date
  if (date) {
    if (startDate || endDate) {
      return res.status(400).json({
        message: "Choose either one date or a date range",
      });
    }

    return next();
  }

  // Case 2: User selected a date range
  if (startDate && endDate) {
    const start = new Date(startDate);
    const end = new Date(endDate);

    if (end <= start) {
      return res.status(400).json({
        message: "End date must be after start date",
      });
    }

    return next();
  }

  // Case 3: No date or incomplete date range
  return res.status(400).json({
    message: "Provide a date or both startDate and endDate",
  });
};

const validateGeoJSONFile = (req, res, next) => {
  if (!req.file) {
    return res.status(400).json({
      message: "GeoJSON file is required",
    });
  }

  const fileName = req.file.originalname;

  if (!fileName.toLowerCase().endsWith(".geojson")) {
    return res.status(400).json({
      message: "Only .geojson files are allowed",
    });
  }

  if (req.file.size === 0) {
    return res.status(400).json({
      message: "GeoJSON file is empty",
    });
  }

  try {
    const fileContent = req.file.buffer.toString("utf-8");

    const geojson = JSON.parse(fileContent);

    if (!gjv.valid(geojson)) {
      return res.status(400).json({
        message: "Invalid GeoJSON file",
      });
    }

    if (geojson.type !== "Feature") {
      return res.status(400).json({
        message: "GeoJSON must be a Feature",
      });
    }

    if (!geojson.geometry) {
      return res.status(400).json({
        message: "GeoJSON geometry is required",
      });
    }

    if (geojson.geometry.type !== "Polygon") {
      return res.status(400).json({
        message: "Geometry must be a Polygon",
      });
    }

  const coordinates = geojson.geometry.coordinates;

if (
      !Array.isArray(coordinates) ||
      coordinates.length === 0 ||
      !Array.isArray(coordinates[0]) ||
      coordinates[0].length < 4
    ) {
      return res.status(400).json({
        message: "Polygon coordinates are missing or insufficient",
      });
    }

    const ring = coordinates[0];
    const firstPoint = ring[0];
    const lastPoint = ring[ring.length - 1];

    if (
      firstPoint[0] !== lastPoint[0] ||
      firstPoint[1] !== lastPoint[1]
    ) {
      return res.status(400).json({
        message: "Polygon ring must be closed",
      });
    }


    req.geojson = geojson;

    next();
  } catch (error) {
    return res.status(400).json({
      message: "Invalid GeoJSON file",
    });
  }
};

module.exports = {
  validateChat,
  validateDateSelection,
  validateGeoJSONFile,
};