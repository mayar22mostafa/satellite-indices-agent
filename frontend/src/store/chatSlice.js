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
    status: "idle", // idle | waiting
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
    // Random ids and the clock are created in `prepare`, so the reducer stays pure
    startNewChat: {
      reducer: (state, action) => {
        state.messages = [action.payload.welcomeMessage];
        state.status = "idle";
        state.conversationId = null;
        state.chatKey = action.payload.chatKey;
      },
      prepare: () => ({
        payload: { chatKey: createId(), welcomeMessage: createWelcomeMessage() },
      }),
    },
    // A reply is stored only if it belongs to the chat that is still on screen
    receiveReply: (state, action) => {
      if (action.payload.chatKey !== state.chatKey) return;
      state.messages.push(action.payload.message);
    },
    // Unlocks the input, but only for the chat that sent the request
    finishRequest: (state, action) => {
      if (action.payload !== state.chatKey) return;
      state.status = "idle";
    },
  },
});

export const { addMessage, setStatus, startNewChat, receiveReply, finishRequest } =
  chatSlice.actions;

// Derived: true until the user has sent their first message
export const selectIsFirstMessage = (state) =>
  !state.chat.messages.some((message) => message.role === "user");

export const selectIsWaiting = (state) => state.chat.status === "waiting";

export const selectChatKey = (state) => state.chat.chatKey;

export default chatSlice.reducer;