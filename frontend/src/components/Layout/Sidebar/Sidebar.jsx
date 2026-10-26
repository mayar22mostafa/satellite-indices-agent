import { useDispatch, useSelector } from "react-redux";
import { SIDEBAR_ID, NEW_CHAT_MODAL_ID } from "../../../config/constants";
import { toggleTheme, selectThemeMode } from "../../../store/themeSlice";
import {
  selectSavedChats,
  selectChatKey,
  loadSavedChat,
  deleteSavedChat,
} from "../../../store/chatSlice";
import { formatChatHistoryDate } from "../../../utils/dateUtils";
import styles from "./Sidebar.module.css";

const Sidebar = ({ isOpen, onNewChat, needsConfirm, onCloseSidebar }) => {
  // L1 => States & Global Data
  const dispatch = useDispatch();
  const themeMode = useSelector(selectThemeMode);
  const savedChats = useSelector(selectSavedChats);
  const activeChatKey = useSelector(selectChatKey);
  const isDark = themeMode === "dark";

  // L2 => Effects
  // L3 => Handlers
  const handleToggleTheme = () => {
    dispatch(toggleTheme());
  };

  const handleSelectChat = (id) => {
    if (id === activeChatKey) return;
    dispatch(loadSavedChat(id));
    if (onCloseSidebar) {
      onCloseSidebar();
    }
  };

  const handleDeleteChat = (e, id) => {
    e.stopPropagation();
    dispatch(deleteSavedChat(id));
  };

  // L4 => JSX
  return (
    <aside
      id={SIDEBAR_ID}
      className={`${styles.sidebar} ${isOpen ? styles.sidebarOpen : ""}`}
      aria-label="Chat sidebar"
    >
      <div className={`${styles.brand} d-flex align-items-center gap-2`}>
        <div className={styles.avatar}>
          <i className="fa-solid fa-robot"></i>
        </div>
        <span className="fw-semibold">EgSA Agent</span>
      </div>

      {/* With messages on screen the button opens the confirmation modal;
          with an empty chat it starts a new chat directly */}
      <button
        type="button"
        className={styles.newChatBtn}
        onClick={needsConfirm ? undefined : onNewChat}
        data-bs-toggle={needsConfirm ? "modal" : undefined}
        data-bs-target={needsConfirm ? `#${NEW_CHAT_MODAL_ID}` : undefined}
      >
        <i className="fa-solid fa-plus"></i>
        New Chat
      </button>

      {/* List of saved chats */}
      <div className={styles.listArea}>
        <div className={styles.listHeader}>
          <span className={styles.listTitle}>Recent Chats</span>
          {savedChats.length > 0 && (
            <span className={styles.chatCountBadge}>{savedChats.length}</span>
          )}
        </div>

        {savedChats.length === 0 ? (
          <div className={styles.emptyState}>
            <i className={`fa-regular fa-comments ${styles.emptyIcon}`}></i>
            <span className={styles.emptyTitle}>No saved chats yet</span>
            <span className={styles.emptySubtitle}>
              Your conversations will appear here
            </span>
          </div>
        ) : (
          <div className={styles.chatList}>
            {savedChats.map((chat) => {
              const isActive = chat.id === activeChatKey;
              return (
                <div
                  key={chat.id}
                  className={`${styles.chatItem} ${
                    isActive ? styles.chatItemActive : ""
                  }`}
                  onClick={() => handleSelectChat(chat.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      handleSelectChat(chat.id);
                    }
                  }}
                  aria-label={`Open conversation: ${chat.title}`}
                >
                  <div className={styles.chatItemIcon}>
                    <i
                      className={`fa-solid ${
                        isActive ? "fa-comment-dots" : "fa-message"
                      }`}
                    ></i>
                  </div>
                  <div className={styles.chatItemContent}>
                    <span className={styles.chatItemTitle} title={chat.title}>
                      {chat.title}
                    </span>
                    <span className={styles.chatItemDate}>
                      {formatChatHistoryDate(chat.updatedAt)}
                    </span>
                  </div>
                  <button
                    type="button"
                    className={styles.deleteBtn}
                    onClick={(e) => handleDeleteChat(e, chat.id)}
                    aria-label={`Delete chat: ${chat.title}`}
                    title="Delete chat"
                  >
                    <i className="fa-regular fa-trash-can"></i>
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Theme Switcher Toggle in Sidebar Footer */}
      <div className={styles.sidebarFooter}>
        <button
          type="button"
          className={styles.themeToggleBtn}
          onClick={handleToggleTheme}
          aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
        >
          <span className={styles.themeLabelArea}>
            <i
              className={`fa-solid ${
                isDark ? "fa-moon" : "fa-sun"
              }`}
            ></i>
            <span>{isDark ? "Dark Theme" : "Light Theme"}</span>
          </span>
          <i className="fa-solid fa-arrows-rotate small opacity-75"></i>
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;