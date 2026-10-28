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
  const { image_date, start_date, end_date, session_id } = req.body;

    // Case 1: Existing conversation
  if (session_id) {
    return next();
  } 

  // Case 2: User selected one date
  if (image_date) {
    if (start_date || end_date) {
      return res.status(400).json({
        message: "Choose either one date or a date range",
      });
    }

    return next();
  }

// Case 3: New conversation with a date range
  if (start_date && end_date) {
    const start = new Date(start_date);
    const end = new Date(end_date);

    if (end <= start) {
      return res.status(400).json({
        message: "End date must be after start date",
      });
    }

    return next();
  }

  // Case 4: New conversation without a valid date selection
  return res.status(400).json({
    message: "Provide a date or both startDate and endDate",
  });
};


const validateGeoJSONFile = (req, res, next) => {
  const { session_id } = req.body;

  // Existing conversation: file is optional
  if (session_id && !req.file) {
    return next();
  }

  // New conversation: file is required
  if (!session_id && !req.file) {
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

    const allowedTypes = [
      "FeatureCollection",
      "Feature",
      "Polygon",
      "MultiPolygon",
    ];

    if (!allowedTypes.includes(geojson.type)) {
      return res.status(400).json({
        message:
          "GeoJSON must be a FeatureCollection, Feature, Polygon, or MultiPolygon",
      });
    }

    // Extract geometries to validate polygon types
    let geometries = [];

    if (geojson.type === "FeatureCollection") {
      geometries = geojson.features.map((feature) => feature.geometry);
    } else if (geojson.type === "Feature") {
      geometries = [geojson.geometry];
    } else {
      geometries = [geojson];
    }

    if (
      geometries.length === 0 ||
      geometries.some(
        (geometry) =>
          !geometry ||
          !["Polygon", "MultiPolygon"].includes(geometry.type)
      )
    ) {
      return res.status(400).json({
        message: "AOI must contain Polygon or MultiPolygon geometries",
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