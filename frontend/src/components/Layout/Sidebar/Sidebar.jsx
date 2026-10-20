import { SIDEBAR_ID, NEW_CHAT_MODAL_ID } from "../../../config/constants";
import styles from "./Sidebar.module.css";

const Sidebar = ({ isOpen, onNewChat, needsConfirm }) => {
  // L1 => States & Global Data
  // L2 => Effects
  // L3 => Handlers
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

      {/* Space reserved for the list of previous chats (future feature) */}
      <div className={styles.listArea}></div>
    </aside>
  );
};

export default Sidebar;