const chatService = require("./chatService");
const { subscribeToPlan } = require("./planEventService");

const sendMessage = async (req, res, next) => {
  try {
    const {
      message,
      date,
      startDate,
      endDate,
      session_id,
    } = req.body;
    const geojson = req.geojson;

    const result = await chatService.sendMessage({
      message,
      date,
      startDate,
      endDate,
      session_id,
      geojson,
    });

    res.status(200).json(result);
  } catch (error) {
    console.error(error);

    next(error);
  }
};

const approvePlan = async (req, res, next) => {
  try {
    const { planId } = req.params;

    if (!planId) {
      return res.status(400).json({
        status: "error",
        message: "planId is required",
      });
    }

    const result = await chatService.approvePlan(planId);

    res.status(202).json(result);
  } catch (error) {
    next(error);
  }
};


const getPlanResult = async (req, res, next) => {
  try {
    const { planId } = req.params;

    if (!planId) {
      return res.status(400).json({
        message: "Plan ID is required",
      });
    }

    const result = await chatService.getPlanResultFromAgent(planId);

    return res.status(200).json(result);
  } catch (error) {
    next(error);
  }
};


const subscribeToPlanEvents = (req, res, next) => {
  try {
    const { planId } = req.params;

    if (!planId) {
      return res.status(400).json({
        message: "Plan ID is required",
      });
    }

    subscribeToPlan(planId, res);
  } catch (error) {
    next(error);
  }
};


module.exports = {
  sendMessage,
  approvePlan,
  getPlanResult,
  subscribeToPlanEvents,
};