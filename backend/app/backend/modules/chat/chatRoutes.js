const express = require("express");
const router = express.Router();

const { sendMessage } = require("./chatController");
const { validateChat, validateDateSelection, validateGeoJSONFile } = require("./chatValidation");
const uploadGeoJSON = require("../../middlewares/uploadMiddleware");


router.post("/sendmsg",
    uploadGeoJSON,
    validateChat,
    validateDateSelection,
    validateGeoJSONFile,
    sendMessage);

module.exports = router;