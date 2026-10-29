const chatService = require("./chatService");
const { subscribeToPlan } = require("./planEventService");

const sendMessage = async (req, res, next) => {
  try {
    const {
      message,
      image_date,
      start_date,
      end_date,
      session_id,
    } = req.body;
    const aoi = req.geojson;

    const result = await chatService.sendMessage({
      message,
      image_date,
      start_date,
      end_date,
      session_id,
      aoi,
    });

    res.status(200).json(result);
  } catch (error) {
    console.error(error);

    next(error);
  }
};

const approvePlan = async (req, res, next) => {
  try {
    const { plan_id } = req.params;

    if (!plan_id) {
      return res.status(400).json({
        status: "error",
        message: "planId is required",
      });
    }

    const result = await chatService.approvePlan(plan_id);

    res.status(202).json(result);
  } catch (error) {
    next(error);
  }
};

const getPlanResult = async (req, res, next) => {
  try {
    const { plan_id } = req.params;

    if (!plan_id) {
      return res.status(400).json({
        message: "Plan ID is required",
      });
    }

    const result = await chatService.getPlanResultFromAgent(plan_id);

    return res.status(200).json(result);
  } catch (error) {
    next(error);
  }
};

const subscribeToPlanEvents = (req, res, next) => {
  try {
    const { plan_id } = req.params;

    if (!plan_id) {
      return res.status(400).json({
        message: "Plan ID is required",
      });
    }

    subscribeToPlan(plan_id, res);
  } catch (error) {
    next(error);
  }
};

const deleteChat = async (req, res, next) => {
  try {
    const { conversationId } = req.params;

    if (!conversationId) {
      return res.status(400).json({
        status: "error",
        message: "Conversation ID is required",
      });
    }

    const result = await chatService.deleteChat(conversationId);

    return res.status(200).json({
      status: "success",
      ...result,
    });
  } catch (error) {
    next(error);
  }
};


module.exports = {
  sendMessage,
  approvePlan,
  getPlanResult,
  subscribeToPlanEvents,
  deleteChat,
};