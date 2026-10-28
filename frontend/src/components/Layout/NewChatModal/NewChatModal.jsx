import { useEffect } from "react";
import styles from "./NewChatModal.module.css";

const NewChatModal = ({ isOpen, onClose, onConfirm }) => {
  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className={styles.backdrop}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="new-chat-modal-title"
    >
      <div className={styles.modalDialog} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <div className={styles.titleArea}>
            <div className={styles.headerIcon}>
              <i className="fa-solid fa-plus"></i>
            </div>
            <h2 id="new-chat-modal-title" className={styles.modalTitle}>
              Start a new chat?
            </h2>
          </div>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            aria-label="Close"
          >
            <i className="fa-solid fa-xmark"></i>
          </button>
        </div>

        <div className={styles.modalBody}>
          <p className="mb-0">
            Your current conversation will remain saved in the sidebar. Start a new chat?
          </p>
        </div>

        <div className={styles.modalFooter}>
          <button
            type="button"
            className={styles.cancelBtn}
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="button"
            className={styles.confirmBtn}
            onClick={() => {
              onConfirm();
              onClose();
            }}
          >
            <i className="fa-solid fa-plus"></i>
            New chat
          </button>
        </div>
      </div>
    </div>
  );
};

export default NewChatModal;