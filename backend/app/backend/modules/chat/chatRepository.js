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

// Deletes the conversation(s) that belong to an Agent session_id, together with
// their messages and analysis plans, in ONE transaction (all or nothing).
// Children are removed explicitly so this works whether or not the foreign keys
// are declared ON DELETE CASCADE. Only rows linked to this session_id are touched.
// Returns null when no conversation has this session_id.
const deleteConversationBySessionId = async (sessionId) => {
  const client = await pool.connect();

  try {
    await client.query("BEGIN");

    // Lock the matching conversation row(s) so a concurrent message cannot
    // attach new children while we are deleting.
    const found = await client.query(
      `SELECT id
       FROM conversations
       WHERE session_id = $1
       FOR UPDATE`,
      [sessionId]
    );

    if (found.rowCount === 0) {
      await client.query("ROLLBACK");
      return null;
    }

    const plans = await client.query(
      `DELETE FROM analysis_plans
       WHERE conversation_id IN (
         SELECT id FROM conversations WHERE session_id = $1
       )`,
      [sessionId]
    );

    const messages = await client.query(
      `DELETE FROM messages
       WHERE conversation_id IN (
         SELECT id FROM conversations WHERE session_id = $1
       )`,
      [sessionId]
    );

    const conversations = await client.query(
      `DELETE FROM conversations
       WHERE session_id = $1`,
      [sessionId]
    );

    await client.query("COMMIT");

    return {
      conversations: conversations.rowCount,
      messages: messages.rowCount,
      plans: plans.rowCount,
    };
  } catch (error) {
    try {
      await client.query("ROLLBACK");
    } catch (rollbackError) {
      console.error("Rollback failed:", rollbackError.message);
    }
    throw error;
  } finally {
    client.release();
  }
};


module.exports = {
  createConversation,
  getConversationBySessionId,
  updateConversationSessionId,
  saveMessage,
  saveAnalysisPlan,
  updateAnalysisPlanStatus,
  deleteConversationBySessionId,
};
