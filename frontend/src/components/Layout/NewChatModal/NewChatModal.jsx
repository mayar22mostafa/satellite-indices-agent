import { NEW_CHAT_MODAL_ID } from "../../../config/constants";
import styles from "./NewChatModal.module.css";

const NewChatModal = ({ onConfirm }) => {
  // L1 => States & Global Data
  // L2 => Effects
  // L3 => Handlers
  // L4 => JSX
  return (
    <div
      className="modal fade"
      id={NEW_CHAT_MODAL_ID}
      tabIndex="-1"
      aria-labelledby={`${NEW_CHAT_MODAL_ID}-title`}
      aria-hidden="true"
    >
      <div className="modal-dialog modal-dialog-centered">
        <div className="modal-content">
          <div className="modal-header">
            <h2
              className={`${styles.title} modal-title fs-5`}
              id={`${NEW_CHAT_MODAL_ID}-title`}
            >
              Start a new chat?
            </h2>
            <button
              type="button"
              className="btn-close"
              data-bs-dismiss="modal"
              aria-label="Close"
            ></button>
          </div>

          <div className="modal-body">
            <p className="mb-0">
              Your current conversation will remain saved in the sidebar. Start a new chat?
            </p>
          </div>

          <div className="modal-footer">
            <button
              type="button"
              className="btn btn-light"
              data-bs-dismiss="modal"
            >
              Cancel
            </button>
            <button
              type="button"
              className={`btn btn-primary ${styles.confirmBtn}`}
              data-bs-dismiss="modal"
              onClick={onConfirm}
            >
              New chat
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default NewChatModal;