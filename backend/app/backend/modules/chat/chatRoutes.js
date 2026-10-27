const express = require("express");
const router = express.Router();

const { sendMessage, approvePlan, getPlanResult, subscribeToPlanEvents, deleteChat,} = require("./chatController");
const { validateChat, validateDateSelection, validateGeoJSONFile } = require("./chatValidation");
const uploadGeoJSON = require("../../middlewares/uploadMiddleware");


router.post("/sendmsg",
    uploadGeoJSON,
    validateChat,
    validateDateSelection,
    validateGeoJSONFile,
    sendMessage);

router.post("/plans/:planId/approve", approvePlan);

router.get("/plans/:planId/result", getPlanResult);

router.get("/plans/:planId/events", subscribeToPlanEvents);

router.delete("/conversations/:conversationId", deleteChat);

module.exports = router;