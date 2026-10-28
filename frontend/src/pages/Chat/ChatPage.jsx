import { useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import {
  startNewChat,
  selectChatKey,
} from "../../store/chatSlice";
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

  // The sidebar should always remain open; it only closes when explicitly clicked on the toggle arrow
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isNewChatModalOpen, setIsNewChatModalOpen] = useState(false);
  const toggleRef = useRef(null);

  // L2 => Effects
  // L3 => Handlers
  const handleToggleSidebar = () => {
    setIsSidebarOpen((open) => !open);
  };

  const handleOpenNewChatModal = () => {
    setIsNewChatModalOpen(true);
  };

  const handleCloseNewChatModal = () => {
    setIsNewChatModalOpen(false);
  };

  const handleConfirmNewChat = () => {
    dispatch(startNewChat());
    setIsNewChatModalOpen(false);
  };

  // L4 => JSX
  return (
    <div className={styles.page}>
      <Sidebar
        isOpen={isSidebarOpen}
        onNewChat={handleOpenNewChatModal}
      />
      <NewChatModal
        isOpen={isNewChatModalOpen}
        onClose={handleCloseNewChatModal}
        onConfirm={handleConfirmNewChat}
      />
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