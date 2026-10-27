import axios from "axios";
import {
  REQUEST_TIMEOUT_MS,
  APPROVE_TIMEOUT_MS,
  PLAN_STATUS,
  MAX_SSE_ERRORS,
} from "../config/constants";
import { createId } from "../utils/createId";

// Backend base URL comes from the environment (see .env.example), never hardcoded.
export const API_BASE_URL = (import.meta.env.VITE_API_URL || "").replace(/\/+$/, "");

export const CONFIG_ERROR_MESSAGE =
  "The backend URL is not configured. Set VITE_API_URL in the frontend .env file and restart the dev server.";

// One configured client for the whole app
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: REQUEST_TIMEOUT_MS,
});

// Without a base URL, requests would silently go to the frontend dev server. Fail loudly instead.
api.interceptors.request.use((config) => {
  if (!API_BASE_URL) {
    return Promise.reject(new Error(CONFIG_ERROR_MESSAGE));
  }
  return config;
});

// Builds the multipart form the backend expects (POST /chat/sendmsg).
// Fields: message, geojson (file), date | startDate + endDate, session_id.
// Optional fields are omitted rather than sent empty (the backend validates them strictly).
// Do NOT set Content-Type here: the browser must add the multipart boundary itself.
export const buildMessageForm = ({ text, file, date, conversationId }) => {
  const form = new FormData();
  form.append("message", text);

  if (file) {
    form.append("geojson", file); // the field must be named exactly "geojson"
  }

  if (date) {
    if (date.from === date.to) {
      form.append("date", date.from);
    } else {
      form.append("startDate", date.from);
      form.append("endDate", date.to);
    }
  }

  // The backend calls the conversation identifier "session_id"
  if (conversationId) {
    form.append("session_id", conversationId);
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

  // 0. Agent-reported error -> shown as a normal text message
  if (data?.type === "error") {
    return {
      conversationId,
      message: {
        id,
        role: "agent",
        type: "text",
        createdAt,
        text: data.message || data.error || "The agent could not process this request.",
      },
    };
  }

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
        // Only the id the agent issued is valid for /approve; never invent one
        plan_id: data.plan_id ?? data.plan?.plan_id ?? null,
        plan: data.plan || data,
        text: data.reply || data.message || data.explanation || "Here is the proposed satellite analysis plan:",
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
      // Retry only when the request most likely never reached the agent
      // (network drop or 503). Retrying after 502/504/timeouts could process the message twice.
      const neverProcessed =
        (!err.response && err.code !== "ECONNABORTED" && err.code !== "ETIMEDOUT") ||
        err.response?.status === 503;
      if (axios.isCancel(err) || err.message === CONFIG_ERROR_MESSAGE || !neverProcessed) {
        throw err;
      }
      // Wait before the next attempt to allow the service to start
      if (attempt < maxRetries) {
        await new Promise((res) => setTimeout(res, 2500));
      }
    }
  }

  throw lastError;
};

// Approves a proposed plan: POST /chat/plans/:planId/approve (backend answers 202 immediately).
// The analysis result is NOT in this response; track it with watchPlan() below.
export const approvePlan = async ({ planId, signal }) => {
  const { data } = await api.post(
    `/chat/plans/${encodeURIComponent(planId)}/approve`,
    null,
    { signal, timeout: APPROVE_TIMEOUT_MS },
  );
  return data;
};

// Builds the chat message that shows a finished analysis.
// `result` is whatever the agent returned in GET /plans/:id/result -> { status: "Done", result }
export const buildAnalysisMessage = (result) => {
  const base = { id: createId(), role: "agent", createdAt: Date.now() };
  let data = result;

  if (typeof data === "string") {
    try {
      data = JSON.parse(data);
    } catch {
      return { ...base, type: "text", text: data };
    }
  }

  // GeoJSON Feature: { type: "Feature", geometry, properties: { results, explanation } }
  if (data?.properties?.results) {
    return { ...base, type: "analysis", feature: data, geometry: data.geometry, properties: data.properties };
  }

  // Flat shape: { results, explanation, errors }
  if (data?.results) {
    return {
      ...base,
      type: "analysis",
      feature: data,
      geometry: data.geometry,
      properties: { results: data.results, explanation: data.explanation, errors: data.errors },
    };
  }

  return {
    ...base,
    type: "text",
    text: "The analysis finished, but the result was empty or in an unexpected format.",
  };
};

// One live stream per plan: a new watchPlan() for the same plan closes the previous one,
// so duplicate listeners can never pile up.
const activeStreams = new Map();

// Follows an approved plan through the backend SSE endpoint GET /chat/plans/:planId/events.
// Calls onProgress(update) for non-final statuses, then exactly one of
// onDone(update) or onFailed({ message }). The stream is closed on any final state.
// Returns { close } so the caller can stop watching (e.g. when the chat is left).
export const watchPlan = (planId, { onProgress, onDone, onFailed }) => {
  activeStreams.get(planId)?.close();

  const source = new EventSource(
    `${API_BASE_URL}/chat/plans/${encodeURIComponent(planId)}/events`,
  );
  let errorCount = 0;
  let finished = false;
  let closed = false; // set on an intentional close: later events are ignored

  const handle = {
    close: () => {
      closed = true;
      source.close();
      if (activeStreams.get(planId) === handle) activeStreams.delete(planId);
    },
  };
  activeStreams.set(planId, handle);

  const finish = (callback, payload) => {
    if (finished) return;
    finished = true;
    handle.close();
    callback?.(payload);
  };

  source.onmessage = (event) => {
    if (closed) return;
    errorCount = 0;

    let update;
    try {
      update = JSON.parse(event.data);
    } catch {
      return; // ignore malformed events
    }

    switch (update.status) {
      case PLAN_STATUS.DONE:
        finish(onDone, update);
        break;
      case PLAN_STATUS.FAILED:
        finish(onFailed, {
          message:
            update.error || update.message || update.detail || update.reason || "The analysis failed.",
        });
        break;
      case PLAN_STATUS.ERROR:
        finish(onFailed, { message: update.message || "Could not retrieve the analysis status." });
        break;
      default:
        onProgress?.(update); // e.g. "Running"
    }
  };

  // EventSource reconnects by itself (the backend replays the latest status on reconnect).
  // Give up when the browser stops retrying or after too many consecutive failures.
  source.onerror = () => {
    if (closed) return;
    errorCount += 1;
    if (source.readyState === EventSource.CLOSED || errorCount >= MAX_SSE_ERRORS) {
      finish(onFailed, {
        message: "Lost the connection to the server while the analysis was running.",
      });
    }
  };

  return handle;
};

// Turns any failure into a sentence the user can understand
export const getErrorMessage = (error) => {
  if (error.message === CONFIG_ERROR_MESSAGE) {
    return CONFIG_ERROR_MESSAGE;
  }
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