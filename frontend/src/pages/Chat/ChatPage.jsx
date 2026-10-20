import { useEffect, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import {
  startNewChat,
  selectChatKey,
  selectIsFirstMessage,
} from "../../store/chatSlice";
import { SIDEBAR_DESKTOP_QUERY } from "../../config/constants";
import Sidebar from "../../components/Layout/Sidebar/Sidebar";
import NewChatModal from "../../components/Layout/NewChatModal/NewChatModal";
import SidebarToggle from "../../components/UI/SidebarToggle/SidebarToggle";
import ChatHeader from "../../components/Chat/ChatHeader/ChatHeader";
import MessageList from "../../components/Chat/MessageList/MessageList";
import ChatInput from "../../components/Chat/ChatInput/ChatInput";
import styles from "./ChatPage.module.css";

const ChatPage = () => {
  // L1 => States & Global Data
  const dispatch = useDispatch();
  const chatKey = useSelector(selectChatKey);
  const isFirstMessage = useSelector(selectIsFirstMessage);
  // Open on desktop, closed on tablets and phones (decided once, at load)
  const [isSidebarOpen, setIsSidebarOpen] = useState(
    () => window.matchMedia(SIDEBAR_DESKTOP_QUERY).matches,
  );
  const toggleRef = useRef(null);

  // L2 => Effects
  // Esc closes the sidebar while it covers the chat (small screens)
  useEffect(() => {
    if (!isSidebarOpen) return;

    const handleKeyDown = (e) => {
      const isOverlay = !window.matchMedia(SIDEBAR_DESKTOP_QUERY).matches;
      // defaultPrevented: Bootstrap already used this Esc (open modal or menu)
      if (e.key === "Escape" && isOverlay && !e.defaultPrevented) {
        setIsSidebarOpen(false);
        toggleRef.current?.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isSidebarOpen]);

  // L3 => Handlers
  const handleToggleSidebar = () => {
    setIsSidebarOpen((open) => !open);
  };

  const handleCloseSidebar = () => {
    setIsSidebarOpen(false);
  };

  const handleNewChat = () => {
    dispatch(startNewChat());
    // On small screens the sidebar covers the chat, so close it
    if (!window.matchMedia(SIDEBAR_DESKTOP_QUERY).matches) {
      setIsSidebarOpen(false);
    }
  };

  // L4 => JSX
  return (
    <div className={styles.page}>
      <Sidebar
        isOpen={isSidebarOpen}
        onNewChat={handleNewChat}
        needsConfirm={!isFirstMessage}
      />
      <NewChatModal onConfirm={handleNewChat} />
      {isSidebarOpen && (
        <div
          className={styles.backdrop}
          onClick={handleCloseSidebar}
          aria-hidden="true"
        ></div>
      )}
      <SidebarToggle
        ref={toggleRef}
        isOpen={isSidebarOpen}
        onToggle={handleToggleSidebar}
      />

      {/* A new key rebuilds the whole chat, so text, file and date start empty */}
      <div className={styles.chatShell} key={chatKey}>
        <ChatHeader />
        <MessageList />
        <ChatInput />
      </div>
    </div>
  );
};

export default ChatPage;