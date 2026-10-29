const multer = require("multer");

const storage = multer.memoryStorage();

const upload = multer({
  storage,
  limits: {
    fileSize: 5 * 1024 * 1024, // Maximum 5 MB
  },
});

const uploadGeoJSON = (req, res, next) => {
  upload.single("aoi")(req, res, (err) => {
    if (err instanceof multer.MulterError) {
      if (err.code === "LIMIT_FILE_SIZE") {
        return res.status(400).json({
          status: "error",
          message: "GeoJSON file must not exceed 5 MB",
        });
      }

      return res.status(400).json({
        status: "error",
        message: "File upload failed",
      });
    }

    if (err) {
      return next(err);
    }

    next();
  });
};

module.exports = uploadGeoJSON;
