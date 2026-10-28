import { createSlice } from "@reduxjs/toolkit";
import { WELCOME_MESSAGE } from "../config/constants";
import { createId } from "../utils/createId";

const STORAGE_KEY = "egsa_saved_chats";

const createWelcomeMessage = () => ({
  id: "welcome",
  role: "agent",
  text: WELCOME_MESSAGE,
  createdAt: Date.now(),
});

const loadSavedChatsFromStorage = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const saveChatsToStorage = (chats) => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
  } catch {
    // ignore localStorage quota errors
  }
};

const deriveChatTitle = (messages) => {
  const userMsg = messages.find(
    (m) => m.role === "user" || m.type === "user",
  );
  if (!userMsg) return "New Conversation";

  if (userMsg.text && userMsg.text.trim()) {
    const firstLine = userMsg.text.trim().split("\n")[0];
    return firstLine.length > 34 ? `${firstLine.slice(0, 34)}...` : firstLine;
  }

  if (userMsg.file) {
    if (userMsg.file.isMapSelection) return "Map Selection Analysis";
    return `File: ${userMsg.file.name}`;
  }

  return "Satellite Analysis";
};

// Saves or updates current active conversation in the savedChats array
const updateSavedSession = (state) => {
  const hasUser = state.messages.some(
    (m) => m.role === "user" || m.type === "user",
  );
  if (!hasUser) return;

  const now = Date.now();
  const title = deriveChatTitle(state.messages);
  const existingIndex = state.savedChats.findIndex(
    (s) => s.id === state.chatKey,
  );

  const sessionData = {
    id: state.chatKey,
    title,
    messages: state.messages,
    conversationId: state.conversationId,
    updatedAt: now,
    createdAt:
      existingIndex >= 0 ? state.savedChats[existingIndex].createdAt : now,
  };

  if (existingIndex >= 0) {
    state.savedChats[existingIndex] = sessionData;
  } else {
    state.savedChats.unshift(sessionData);
  }

  state.savedChats.sort((a, b) => b.updatedAt - a.updatedAt);
  saveChatsToStorage(state.savedChats);
};

const chatSlice = createSlice({
  name: "chat",
  initialState: {
    messages: [createWelcomeMessage()],
    status: "idle", // idle | sending (the upload) | thinking (the agent works)
    uploadPercent: null, // 0-100 while sending, otherwise null
    conversationId: null, // given by the server later; null = a new conversation
    chatKey: createId(), // local id of the chat on screen, changes on New Chat
    approvingPlanId: null, // plan_id currently undergoing POST /plans/{plan_id}/approve
    savedChats: loadSavedChatsFromStorage(),
  },
  reducers: {
    addMessage: (state, action) => {
      state.messages.push(action.payload);
      updateSavedSession(state);
    },
    setStatus: (state, action) => {
      state.status = action.payload;
    },
    setApprovingPlan: (state, action) => {
      state.approvingPlanId = action.payload;
    },
    markPlanApproved: (state, action) => {
      const planId = action.payload;
      const msg = state.messages.find(
        (m) => m.plan_id === planId || m.plan?.id === planId || m.id === planId,
      );
      if (msg) {
        msg.approved = true;
      }
      updateSavedSession(state);
    },
    appendAnalysisResult: (state, action) => {
      state.approvingPlanId = null;
      const { planId, analysisMessage, chatKey } = action.payload;
      if (chatKey && chatKey !== state.chatKey) return;
      if (planId) {
        const planMsg = state.messages.find(
          (m) => m.plan_id === planId || m.plan?.id === planId,
        );
        if (planMsg) {
          planMsg.approved = true;
        }
      }
      state.messages.push(analysisMessage);
      updateSavedSession(state);
    },
    startNewChat: {
      reducer: (state, action) => {
        // Save existing chat if it has user messages
        updateSavedSession(state);

        state.messages = [action.payload.welcomeMessage];
        state.status = "idle";
        state.uploadPercent = null;
        state.conversationId = null;
        state.approvingPlanId = null;
        state.chatKey = action.payload.chatKey;
      },
      prepare: () => ({
        payload: { chatKey: createId(), welcomeMessage: createWelcomeMessage() },
      }),
    },
    // Loads an existing saved chat session from the sidebar
    loadSavedChat: (state, action) => {
      const sessionId = action.payload;
      const session = state.savedChats.find((s) => s.id === sessionId);
      if (!session) return;

      // Save whatever is currently on screen first
      updateSavedSession(state);

      state.chatKey = session.id;
      // Preserve original messages and their exact createdAt timestamps
      state.messages = (session.messages || [createWelcomeMessage()]).map((msg) => ({
        ...msg,
        createdAt: msg.createdAt || session.createdAt || session.updatedAt || Date.now(),
      }));
      state.conversationId = session.conversationId || null;
      state.status = "idle";
      state.uploadPercent = null;
      state.approvingPlanId = null;
    },
    // Deletes a saved chat session
    deleteSavedChat: (state, action) => {
      const sessionId = action.payload;
      state.savedChats = state.savedChats.filter((s) => s.id !== sessionId);
      saveChatsToStorage(state.savedChats);

      // If user deleted the active session, reset to a fresh chat
      if (state.chatKey === sessionId) {
        state.messages = [createWelcomeMessage()];
        state.status = "idle";
        state.uploadPercent = null;
        state.conversationId = null;
        state.approvingPlanId = null;
        state.chatKey = createId();
      }
    },
    // A reply is stored only if it belongs to the chat that is still on screen.
    receiveReply: (state, action) => {
      if (action.payload.chatKey !== state.chatKey) return;
      state.messages.push(action.payload.message);
      if (action.payload.conversationId) {
        state.conversationId = action.payload.conversationId;
      }
      updateSavedSession(state);
    },
    // Takes back a message that could not be sent (only in the chat that sent it)
    removeMessage: (state, action) => {
      if (action.payload.chatKey !== state.chatKey) return;
      state.messages = state.messages.filter(
        (message) => message.id !== action.payload.id,
      );
      updateSavedSession(state);
    },
    // The agent forgot this conversation: the next message starts a new one
    expireConversation: (state, action) => {
      if (action.payload !== state.chatKey) return;
      state.conversationId = null;
      updateSavedSession(state);
    },
    // Upload progress of the request that is running
    updateRequestProgress: (state, action) => {
      if (action.payload.chatKey !== state.chatKey) return;
      if (state.status !== "sending") return;
      if (action.payload.percent >= 100) {
        state.status = "thinking";
        state.uploadPercent = null;
      } else {
        state.uploadPercent = action.payload.percent;
      }
    },
    finishRequest: (state, action) => {
      if (action.payload !== state.chatKey) return;
      state.status = "idle";
      state.uploadPercent = null;
    },
  },
});

export const {
  addMessage,
  setStatus,
  setApprovingPlan,
  markPlanApproved,
  appendAnalysisResult,
  startNewChat,
  loadSavedChat,
  deleteSavedChat,
  receiveReply,
  removeMessage,
  expireConversation,
  updateRequestProgress,
  finishRequest,
} = chatSlice.actions;

// True when the chat has at least one message from the user
export const selectHasUserMessages = (state) =>
  state.chat.messages.some((message) => message.role === "user");

export const selectConversationId = (state) => state.chat.conversationId;

// GeoJSON file is required for the initial conversation start
export const selectNeedsAttachments = (state) =>
  state.chat.conversationId === null;

// Busy while the message is being sent or the agent is working
export const selectIsWaiting = (state) =>
  state.chat.status !== "idle" || Boolean(state.chat.approvingPlanId);

export const selectStatus = (state) => state.chat.status;

export const selectApprovingPlanId = (state) => state.chat.approvingPlanId;

export const selectUploadPercent = (state) => state.chat.uploadPercent;

export const selectChatKey = (state) => state.chat.chatKey;

export const selectSavedChats = (state) => state.chat.savedChats;

export default chatSlice.reducer;