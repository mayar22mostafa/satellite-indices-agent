const { pool } = require("../../config/db");

const createConversation = async (sessionId = null) => {
  const result = await pool.query(
    `INSERT INTO conversations (session_id)
     VALUES ($1)
     RETURNING id, session_id`,
    [sessionId]
  );

  return result.rows[0];
};

const getConversationBySessionId = async (sessionId) => {
  const result = await pool.query(
    `SELECT id, session_id
     FROM conversations
     WHERE session_id = $1`,
    [sessionId]
  );

  return result.rows[0] || null;
};

const updateConversationSessionId = async (conversationId, sessionId) => {
  const result = await pool.query(
    `UPDATE conversations
     SET session_id = $1,
         updated_at = NOW()
     WHERE id = $2
     RETURNING id, session_id`,
    [sessionId, conversationId]
  );

  return result.rows[0] || null;
};

const saveMessage = async (conversationId, role, content) => {
  const result = await pool.query(
    `INSERT INTO messages (conversation_id, role, content)
     VALUES ($1, $2, $3)
     RETURNING id, conversation_id, role, content, created_at`,
    [conversationId, role, content]
  );

  await pool.query(
    `UPDATE conversations
     SET updated_at = NOW()
     WHERE id = $1`,
    [conversationId]
  );

  return result.rows[0];
};

const saveAnalysisPlan = async ({
  plan_id,
  conversationId,
  plan,
}) => {
  const result = await pool.query(
    `INSERT INTO analysis_plans
       (plan_id, conversation_id, plan)
     VALUES ($1, $2, $3)
     RETURNING *`,
    [plan_id, conversationId, JSON.stringify(plan)]
  );

  return result.rows[0];
};

const updateAnalysisPlanStatus = async (plan_id, status, result) => {
  const resultJson =
    result === undefined ? null : JSON.stringify(result);

  const queryResult = await pool.query(
    `UPDATE analysis_plans
     SET status = $1,
         result = COALESCE($2::jsonb, result),
         updated_at = NOW()
     WHERE plan_id = $3
     RETURNING *`,
    [status, resultJson, plan_id]
  );

  return queryResult.rows[0] || null;
};

const deleteConversation = async (conversationId) => {
  const result = await pool.query(
    `DELETE FROM conversations
     WHERE id = $1
     RETURNING id`,
    [conversationId]
  );

  return result.rows[0] || null;
};


module.exports = {
  createConversation,
  getConversationBySessionId,
  updateConversationSessionId,
  saveMessage,
  saveAnalysisPlan,
  updateAnalysisPlanStatus,
  deleteConversation,
};
