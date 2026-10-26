import { useEffect, useRef } from "react";
import { useSelector } from "react-redux";
import {
  selectStatus,
  selectUploadPercent,
} from "../../../store/chatSlice";
import MessageRenderer from "../MessageRenderer/MessageRenderer";
import TypingIndicator from "../../UI/TypingIndicator/TypingIndicator";
import styles from "./MessageList.module.css";

const NEAR_BOTTOM_PX = 80;

const MessageList = () => {
  // L1 => States & Global Data
  const messages = useSelector((state) => state.chat.messages);
  const status = useSelector(selectStatus);
  const uploadPercent = useSelector(selectUploadPercent);
  const isWaiting = status !== "idle";
  const listRef = useRef(null);
  const isNearBottomRef = useRef(true);

  // L2 => Effects
  // Follow new messages: always after the user's own, only if near the bottom otherwise
  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    const lastMessage = messages[messages.length - 1];
    if (lastMessage?.role === "user" || isNearBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, isWaiting]);

  // L3 => Handlers
  const handleScroll = () => {
    const el = listRef.current;
    if (!el) return;
    isNearBottomRef.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
  };

  // L4 => JSX
  return (
    <div
      ref={listRef}
      className={`${styles.messageList} p-3`}
      role="log"
      aria-live="polite"
      onScroll={handleScroll}
    >
      {messages.map((message, index) => (
        <MessageRenderer
          key={message.id}
          message={message}
          isLatest={index === messages.length - 1}
        />
      ))}
      {isWaiting && <TypingIndicator phase={status} percent={uploadPercent} />}
    </div>
  );
};

export default MessageList;