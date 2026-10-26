import axios from "axios";
import { REQUEST_TIMEOUT_MS, APPROVE_TIMEOUT_MS } from "../config/constants";
import { createId } from "../utils/createId";

// One configured client for the whole app
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  timeout: REQUEST_TIMEOUT_MS,
});

// Builds the multipart form the backend expects (POST /chat/sendmsg).
export const buildMessageForm = ({ text, file, date, conversationId }) => {
  const form = new FormData();
  form.append("message", text);

  if (file) {
    form.append("geojson", file); // the field must be named exactly "geojson"
  }

  // Extract dates from text or pass fallback so legacy backend validation succeeds
  if (date) {
    if (date.from === date.to) {
      form.append("date", date.from);
    } else {
      form.append("startDate", date.from);
      form.append("endDate", date.to);
    }
  } else if (text) {
    const rangeMatch = text.match(/from\s+(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})/i);
    const singleMatch = text.match(/on\s+(\d{4}-\d{2}-\d{2})/i);
    if (rangeMatch) {
      form.append("startDate", rangeMatch[1]);
      form.append("endDate", rangeMatch[2]);
    } else if (singleMatch) {
      form.append("date", singleMatch[1]);
    } else if (!conversationId) {
      const today = new Date().toISOString().split("T")[0];
      form.append("date", today);
    }
  }

  if (conversationId) {
    form.append("conversationId", conversationId);
  }

  return form;
};

// Parses whatever envelope the backend or agent service returns into a polymorphic message
export const parseAgentResponse = (raw) => {
  let data = raw;

  // If raw is a string, test if it's JSON
  if (typeof raw === "string") {
    try {
      data = JSON.parse(raw);
    } catch {
      data = { reply: raw };
    }
  }

  // If data.reply is a string that might be JSON
  if (
    typeof data?.reply === "string" &&
    data.reply.trim().startsWith("{") &&
    data.reply.trim().endsWith("}")
  ) {
    try {
      const parsed = JSON.parse(data.reply);
      data = { ...parsed, conversationId: data.conversationId ?? parsed.conversationId };
    } catch {
      // keep original data
    }
  }

  const conversationId =
    data?.conversationId ??
    data?.properties?.session_id ??
    data?.session_id ??
    null;

  const id = createId();
  const createdAt = Date.now();

  // 1. GeoJSON Feature -> Analysis result
  if (data?.type === "Feature" || data?.properties?.results || data?.results) {
    return {
      conversationId,
      message: {
        id,
        role: "agent",
        type: "analysis",
        createdAt,
        feature: data,
        geometry: data.geometry,
        properties: data.properties || { results: data.results, explanation: data.explanation },
      },
    };
  }

  // 2. Plan proposal
  if (data?.type === "plan" || data?.plan || data?.plan_id) {
    return {
      conversationId,
      message: {
        id,
        role: "agent",
        type: "plan",
        createdAt,
        plan_id: data.plan_id || data.plan?.id || data.plan?.plan_id || `plan_${createId()}`,
        plan: data.plan || data,
        text: data.reply || data.explanation || "Here is the proposed satellite analysis plan:",
        approved: false,
      },
    };
  }

  // 3. Question / clarification
  if (data?.type === "question" || data?.question || (data?.prompt && data?.options)) {
    return {
      conversationId,
      message: {
        id,
        role: "agent",
        type: "question",
        createdAt,
        prompt: data.prompt || data.question || data.reply || "Clarification needed:",
        reason: data.reason || null,
        options: Array.isArray(data.options) ? data.options : [],
      },
    };
  }

  // 4. Standard text reply
  const replyText =
    typeof data?.reply === "string"
      ? data.reply
      : typeof data?.message === "string"
      ? data.message
      : typeof data?.text === "string"
      ? data.text
      : typeof data === "string"
      ? data
      : JSON.stringify(data);

  return {
    conversationId,
    message: {
      id,
      role: "agent",
      type: "text",
      text: replyText,
      createdAt,
    },
  };
};

// Sends one chat message (POST /chat/sendmsg) and returns { message, conversationId }
export const sendMessage = async ({
  text,
  file,
  date,
  conversationId,
  signal,
  onUploadProgress,
}) => {
  const form = buildMessageForm({ text, file, date, conversationId });

  let lastError;
  const maxRetries = 2;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const { data } = await api.post("/chat/sendmsg", form, {
        signal,
        onUploadProgress,
      });

      return parseAgentResponse(data);
    } catch (err) {
      lastError = err;
      if (
        axios.isCancel(err) ||
        err.response?.status === 400 ||
        err.response?.status === 404 ||
        err.response?.status === 413
      ) {
        throw err;
      }
      // If service is inactive (502, 503, network drop), wait before next attempt to allow service startup
      if (attempt < maxRetries) {
        await new Promise((res) => setTimeout(res, 2500));
      }
    }
  }

  throw lastError;
};

// Approves a proposed plan: POST /plans/{plan_id}/approve (no body, 120s timeout)
// Returns GeoJSON Feature: { type: "Feature", geometry: ..., properties: ... }
export const approvePlan = async ({ planId, signal }) => {
  const { data } = await api.post(`/plans/${planId}/approve`, null, {
    signal,
    timeout: APPROVE_TIMEOUT_MS,
  });

  const parsed = parseAgentResponse(data);
  // Ensure message is marked as analysis
  if (parsed.message.type !== "analysis") {
    parsed.message.type = "analysis";
    parsed.message.feature = data;
    parsed.message.properties = data.properties || { results: data.results, explanation: data.explanation };
  }
  return parsed;
};

// Turns any failure into a sentence the user can understand
export const getErrorMessage = (error) => {
  if (axios.isCancel(error)) {
    return "The request was cancelled.";
  }
  if (error.code === "ECONNABORTED" || error.message?.toLowerCase().includes("timeout")) {
    return "The operation timed out. Earth Engine or the agent may be processing a heavy request. Please try again.";
  }

  if (error.response) {
    const { status, data } = error.response;
    if (status === 400 || status === 413) {
      return data?.message ?? "The request was not accepted.";
    }
    if (status === 404) {
      return "This plan or conversation was not found or has expired. Please try again.";
    }
    if (status === 502 || status === 503) {
      return "The agent or Earth Engine service is not available right now. Please try again later.";
    }
    if (status === 504) {
      return "The analysis timed out on the server. Please try a smaller area or narrower date range.";
    }
    return data?.message ?? "Something went wrong on the server. Please try again.";
  }

  if (error.request) {
    return "Cannot reach the server. Check your connection and try again.";
  }

  return error.message || "Something went wrong. Please try again.";
};

export const isConversationExpired = (error) => error.response?.status === 404;

export const isRequestCancelled = (error) => axios.isCancel(error);