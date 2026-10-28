const {
  sendMsgToAgent,
  approvePlan: approvePlanWithAgent,
  getPlanResult,
} = require("../agent/agentService");
const {
  createConversation,
  getConversationBySessionId,
  updateConversationSessionId,
  updateAnalysisPlanStatus,
  saveMessage,
  saveAnalysisPlan,
  deleteConversation,
} = require("./chatRepository");

const { startPlanPolling } = require("./planPollingService");

const sendMessage = async ({
  message,
  date,
  startDate,
  endDate,
  session_id,
  geojson,
}) => {
  // 1. Find an existing conversation or create a new one.
  let conversation;

  if (session_id) {
    conversation = await getConversationBySessionId(session_id);

    if (!conversation) {
      conversation = await createConversation(session_id);
    }
  } else {
    conversation = await createConversation();
  }

  // 2. Save the user's message.
  await saveMessage(conversation.id, "user", message);

  // 3. Send the request to the Agent.
  const result = await sendMsgToAgent({
    message,
    date,
    startDate,
    endDate,
    session_id,
    geojson,
  });

  // 4. Save the session_id returned by the Agent.
  if (
    result.session_id &&
    result.session_id !== conversation.session_id
  ) {
    await updateConversationSessionId(
      conversation.id,
      result.session_id
    );
  }

  // 5. Save the Agent's response.
  await saveMessage(
    conversation.id,
    "agent",
    JSON.stringify(result)
  );

  // 6. Save the analysis plan if the Agent returned one.
  if (result.type === "plan" && result.plan_id && result.plan) {
    await saveAnalysisPlan({
      planId: result.plan_id,
      conversationId: conversation.id,
      plan: result.plan,
    });
  }

  // Keep the existing response format for the frontend.
  return result;
};


const approvePlan = async (planId) => {
  const response = await approvePlanWithAgent(planId);

  await updateAnalysisPlanStatus(planId, "Running");

  startPlanPolling(planId);

  return response;
};


const getPlanResultFromAgent = async (planId) => {
  return await getPlanResult(planId);
};

const deleteChat = async (conversationId) => {
  const deletedConversation = await deleteConversation(conversationId);

  if (!deletedConversation) {
    const error = new Error("Chat not found");
    error.statusCode = 404;
    throw error;
  }

  return {
    message: "Chat deleted successfully",
    conversationId: deletedConversation.id,
  };
};

module.exports = {
  sendMessage,
  approvePlan,
  getPlanResultFromAgent,
  deleteChat,
};
