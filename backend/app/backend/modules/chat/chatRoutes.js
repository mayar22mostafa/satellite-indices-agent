const express = require("express");
const router = express.Router();

const { sendMessage, approvePlan, getPlanResult, subscribeToPlanEvents, deleteChat,} = require("./chatController");
const { validateChat, validateDateSelection, validateGeoJSONFile } = require("./chatValidation");
const uploadGeoJSON = require("../../middlewares/uploadMiddleware");


router.post("/plans",
    uploadGeoJSON,
    validateChat,
    validateDateSelection,
    validateGeoJSONFile,
    sendMessage);

router.post("/plans/:plan_id/approve", approvePlan);

router.get("/plans/:plan_id/result", getPlanResult);

router.get("/plans/:plan_id/events", subscribeToPlanEvents);

// :sessionId is the Agent session_id returned to the frontend (NOT the database id)
router.delete("/conversations/:sessionId", deleteChat);

module.exports = router;