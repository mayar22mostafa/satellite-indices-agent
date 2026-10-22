import axios from "axios";
import { REQUEST_TIMEOUT_MS } from "../config/constants";

// One configured client for the whole app
const api = axios.create({
    baseURL: import.meta.env.VITE_API_URL,
    timeout: REQUEST_TIMEOUT_MS,
});

// Builds the multipart form the backend expects (POST /chat/sendmsg).
// This is the only place that knows the backend's field names.
export const buildMessageForm = ({ text, file, date, conversationId }) => {
    const form = new FormData();
    form.append("message", text);

    if (file) {
        form.append("geojson", file); // the field must be named exactly "geojson"
    }

    if (date) {
        if (date.from === date.to) {
            form.append("date", date.from); // one day
        } else {
            form.append("startDate", date.from);
            form.append("endDate", date.to);
        }
    }

    // Multipart cannot carry null, so the field is left out for a new conversation
    if (conversationId) {
        form.append("conversationId", conversationId);
    }

    return form;
};

// Sends one message and returns { reply, conversationId }
export const sendMessage = async ({
  text,
  file,
  date,
  conversationId,
  signal,
  onUploadProgress,
}) => {
  const form = buildMessageForm({ text, file, date, conversationId });
  const { data } = await api.post("/chat/sendmsg", form, {
    signal,
    onUploadProgress,
  });

  if (typeof data?.reply !== "string" || data.reply === "") {
    throw new Error("The agent's answer has no text.");
  }

  return { reply: data.reply, conversationId: data.conversationId ?? null };
};

// Turns any failure into a sentence the user can understand
export const getErrorMessage = (error) => {
    if (axios.isCancel(error)) {
        return "The request was cancelled.";
    }
    if (error.code === "ECONNABORTED") {
        return "The agent took too long to answer. Please try again.";
    }

    if (error.response) {
        const { status, data } = error.response;
        if (status === 400 || status === 413) {
            // The backend's own explanation, such as "Geometry must be a Polygon"
            return data?.message ?? "The request was not accepted.";
        }
        if (status === 404) {
            return "This conversation has expired. Attach the file and the date again to continue.";
        }
        if (status === 502 || status === 503) {
            return "The agent is not available right now. Please try again later.";
        }
        if (status === 504) {
            return "The agent took too long to answer. Please try again.";
        }
        return "Something went wrong on the server. Please try again.";
    }

    if (error.request) {
        return "Cannot reach the server. Check your connection and try again.";
    }

    return error.message || "Something went wrong. Please try again.";
};
// The agent no longer knows this conversation (for example, it was restarted)
export const isConversationExpired = (error) =>
  error.response?.status === 404;
// The user (or New Chat) cancelled the request on purpose
export const isRequestCancelled = (error) => axios.isCancel(error);