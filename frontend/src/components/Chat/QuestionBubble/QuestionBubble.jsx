import { formatTime } from "../../../utils/formatTime";
import styles from "./QuestionBubble.module.css";

const QuestionBubble = ({ message }) => {
  const prompt = message.prompt || message.text || "Clarification needed:";
  const reason = message.reason;
  const options = Array.isArray(message.options) ? message.options : [];

  const handleOptionClick = (option) => {
    // Prefill the input bar so user can send immediately or adjust
    window.dispatchEvent(
      new CustomEvent("prefill-chat-input", {
        detail: { text: option },
      }),
    );
  };

  return (
    <div className={styles.row}>
      <div
        className={styles.bubble}
        role="region"
        aria-label="Agent Question"
      >
        <div className={styles.header}>
          <span className={styles.badge}>
            <i className="fa-solid fa-circle-question"></i> Clarification
          </span>
        </div>

        <p className={styles.prompt} dir="auto">
          {prompt}
        </p>

        {reason && (
          <div className={styles.reason} dir="auto">
            <i className="fa-solid fa-lightbulb mt-1"></i>
            <span>{reason}</span>
          </div>
        )}

        {options.length > 0 && (
          <div className={styles.optionsArea}>
            <span className={styles.optionsLabel}>Suggested replies:</span>
            <div className={styles.optionsList}>
              {options.map((opt, i) => (
                <button
                  key={i}
                  type="button"
                  className={styles.optionChip}
                  onClick={() => handleOptionClick(opt)}
                  aria-label={`Reply: ${opt}`}
                >
                  <i className="fa-solid fa-reply"></i>
                  {opt}
                </button>
              ))}
            </div>
          </div>
        )}

        {message.createdAt && (
          <span className={styles.time}>{formatTime(message.createdAt)}</span>
        )}
      </div>
    </div>
  );
};

export default QuestionBubble;
