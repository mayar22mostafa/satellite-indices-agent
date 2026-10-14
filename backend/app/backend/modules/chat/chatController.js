const chatService = require("./chatService");

const sendMessage = async (req, res, next) => {
  try {
    const {
      message,
      date,
      startDate,
      endDate,
      conversationId,
    } = req.body;
    const geojson = req.geojson;

    const result = await chatService.sendMessage({
      message,
      date,
      startDate,
      endDate,
      conversationId,
      geojson,
    });

    res.status(200).json(result);
  } catch (error) {
    console.error(error);

    next(error);
  }
};

module.exports = {
  sendMessage,
};