const { sendMsgToAgent } = require("../agent/agentService");

const sendMessage = async ({
  message,
  date,
  startDate,
  endDate,
  conversationId,
  geojson,
}) => {
  const result = await sendMsgToAgent({
    message,
    date,
    startDate,
    endDate,
    conversationId,
    geojson,
  });

  return result;
};

module.exports = {
  sendMessage,
};
