import styles from "./TypingIndicator.module.css";

const TypingIndicator = ({ label = "Agent is thinking…" }) => {
  // L1 => States & Global Data
  // L2 => Effects
  // L3 => Handlers
  // L4 => JSX
  return (
    <div className={styles.row}>
      <div className={styles.bubble}>
        <span className={styles.dots} aria-hidden="true">
          <span className={styles.dot}></span>
          <span className={styles.dot}></span>
          <span className={styles.dot}></span>
        </span>
        <span>{label}</span>
      </div>
    </div>
  );
};

export default TypingIndicator;