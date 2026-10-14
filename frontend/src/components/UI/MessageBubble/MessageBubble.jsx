import styles from "./MessageBubble.module.css";
import { formatTime } from "../../../utils/formatTime";
import { formatFileSize } from "../../../utils/formatFileSize";
import { formatDateRange } from "../../../utils/dateUtils";

const MessageBubble = ({ role, text, createdAt, file, date }) => {
  // L1 => States & Global Data
  const isUser = role === "user";

  // L2 => Effects
  // L3 => Handlers
  // L4 => JSX
  return (
    <div
      className={`${styles.row} ${isUser ? styles.rowUser : styles.rowAgent}`}
    >
      <div
        className={`${styles.bubble} ${
          isUser ? styles.bubbleUser : styles.bubbleAgent
        }`}
      >
        {(file || date) && (
          <div className={styles.attachments}>
            {file && (
              <span className={styles.attachment}>
                <i className="fa-solid fa-file"></i>
                <span className={styles.attachmentName}>{file.name}</span>
                <span className={styles.attachmentDetail}>
                  {formatFileSize(file.size)}
                </span>
              </span>
            )}
            {date && (
              <span className={styles.attachment}>
                <i className="fa-solid fa-calendar-days"></i>
                <span>{formatDateRange(date)}</span>
              </span>
            )}
          </div>
        )}
        <p className={styles.text} dir="auto">
          {text}
        </p>
        <span className={styles.time}>{formatTime(createdAt)}</span>
      </div>
    </div>
  );
};

export default MessageBubble;