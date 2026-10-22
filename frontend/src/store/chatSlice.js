import { createSlice } from "@reduxjs/toolkit";
import { WELCOME_MESSAGE } from "../config/constants";
import { createId } from "../utils/createId";

const createWelcomeMessage = () => ({
  id: "welcome",
  role: "agent",
  text: WELCOME_MESSAGE,
  createdAt: Date.now(),
});

const chatSlice = createSlice({
  name: "chat",
  initialState: {
    messages: [createWelcomeMessage()],
    status: "idle", // idle | sending (the upload) | thinking (the agent works)
    uploadPercent: null, // 0-100 while sending, otherwise null
    conversationId: null, // given by the server later; null = a new conversation
    chatKey: createId(), // local id of the chat on screen, changes on New Chat
  },
  reducers: {
    addMessage: (state, action) => {
      state.messages.push(action.payload);
    },
    setStatus: (state, action) => {
      state.status = action.payload;
    },
    startNewChat: {
      reducer: (state, action) => {
        state.messages = [action.payload.welcomeMessage];
        state.status = "idle";
        state.uploadPercent = null;
        state.conversationId = null;
        state.chatKey = action.payload.chatKey;
      },
      prepare: () => ({
        payload: { chatKey: createId(), welcomeMessage: createWelcomeMessage() },
      }),
    },
    // A reply is stored only if it belongs to the chat that is still on screen.
    // The agent's conversation id (when it sends one) is kept for the follow-ups.
    receiveReply: (state, action) => {
      if (action.payload.chatKey !== state.chatKey) return;
      state.messages.push(action.payload.message);
      if (action.payload.conversationId) {
        state.conversationId = action.payload.conversationId;
      }
    },
    // Takes back a message that could not be sent (only in the chat that sent it)
    removeMessage: (state, action) => {
      if (action.payload.chatKey !== state.chatKey) return;
      state.messages = state.messages.filter(
        (message) => message.id !== action.payload.id,
      );
    },
    // The agent forgot this conversation: the next message starts a new one
    expireConversation: (state, action) => {
      if (action.payload !== state.chatKey) return;
      state.conversationId = null;
    },
    // Upload progress of the request that is running (ignored for an old chat).
    // At 100% the message has arrived and the agent starts working.
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
  startNewChat,
  receiveReply,
  removeMessage,
  expireConversation,
  updateRequestProgress,
  finishRequest,
} = chatSlice.actions;

// True when the chat has at least one message from the user (New Chat asks first)
export const selectHasUserMessages = (state) =>
  state.chat.messages.some((message) => message.role === "user");

export const selectConversationId = (state) => state.chat.conversationId;

// File and date are required until the agent has started the conversation
export const selectNeedsAttachments = (state) =>
  state.chat.conversationId === null;

// Busy while the message is being sent or the agent is working
export const selectIsWaiting = (state) => state.chat.status !== "idle";

export const selectStatus = (state) => state.chat.status;

export const selectUploadPercent = (state) => state.chat.uploadPercent;

export const selectChatKey = (state) => state.chat.chatKey;

export default chatSlice.reducer;