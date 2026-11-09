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
  deleteConversationBySessionId,
} = require("./chatRepository");
const AppError = require("../../utils/AppError");

const { startPlanPolling } = require("./planPollingService");

const sendMessage = async ({
  message,
  image_date,
  start_date,
  end_date,
  session_id,
  aoi,
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
    image_date,
    start_date,
    end_date,
    session_id,
    aoi,
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
      plan_id: result.plan_id,
      conversationId: conversation.id,
      plan: result.plan,
    });
  }

  // Keep the existing response format for the frontend.
  return result;
};


const approvePlan = async (plan_id) => {
  const response = await approvePlanWithAgent(plan_id);

  await updateAnalysisPlanStatus(plan_id, "running");

  startPlanPolling(plan_id);

  return response;
};


const getPlanResultFromAgent = async (plan_id) => {
  return await getPlanResult(plan_id);
};

// The frontend only knows the Agent's session_id (the database id is never sent
// to it), so conversations are deleted by session_id.
const deleteChat = async (sessionId) => {
  const deleted = await deleteConversationBySessionId(sessionId);

  if (!deleted) {
    throw new AppError("Conversation not found", 404);
  }

  return {
    message: "Chat deleted successfully",
    session_id: sessionId,
    deleted,
  };
};

module.exports = {
  sendMessage,
  approvePlan,
  getPlanResultFromAgent,
  deleteChat,
};
