import { useEffect, useRef } from "react";
import { useSelector } from "react-redux";
import {
  selectStatus,
  selectUploadPercent,
} from "../../../store/chatSlice";
import MessageBubble from "../../UI/MessageBubble/MessageBubble";
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
    const lastMessage = messages[messages.length - 1];
    if (lastMessage?.role === "user" || isNearBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, isWaiting]);

  // L3 => Handlers
  const handleScroll = () => {
    const el = listRef.current;
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
      {messages.map((message) => (
        <MessageBubble
          key={message.id}
          role={message.role}
          text={message.text}
          createdAt={message.createdAt}
          file={message.file}
          date={message.date}
        />
      ))}
      {isWaiting && <TypingIndicator phase={status} percent={uploadPercent} />}
    </div>
  );
};

export default MessageList;