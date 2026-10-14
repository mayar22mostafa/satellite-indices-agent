const express = require("express");
const multer = require("multer");

const router = express.Router();

const {sendMessage} = require("./chatController");
const {validateChat, validateDateSelection, validateGeoJSONFile} = require("./chatValidation");
const upload = require("../../middlewares/uploadMiddleware");


router.post("/sendmsg", 
    upload.single("geojson"), 
    validateChat, 
    validateDateSelection,
    validateGeoJSONFile, 
    sendMessage);

module.exports = router;