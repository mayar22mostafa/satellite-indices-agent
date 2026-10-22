import { useEffect, useState } from "react";
import { SLOW_RESPONSE_SECONDS } from "../../../config/constants";
import styles from "./TypingIndicator.module.css";

// Shows what the app is doing while the user waits.
// phase: "sending" (the message is going out) or "thinking" (the agent works)
const TypingIndicator = ({ phase, percent }) => {
  // L1 => States & Global Data
  const [seconds, setSeconds] = useState(0); // time since the user pressed Send
  const isSending = phase === "sending";
  const isSlow = !isSending && seconds >= SLOW_RESPONSE_SECONDS;

  let label = "Agent is thinking…";
  if (isSending) {
    label = percent ? `Sending… ${percent}%` : "Sending…";
  } else if (isSlow) {
    label =
      "This is taking longer than usual. You can cancel with the red button.";
  }

  // L2 => Effects
  // This component only exists while the user waits, so it can count the seconds
  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  // L3 => Handlers
  // L4 => JSX
  return (
    <div className={styles.row}>
      <div className={`${styles.bubble} ${isSlow ? styles.bubbleSlow : ""}`}>
        <span className={styles.dots} aria-hidden="true">
          <span className={styles.dot}></span>
          <span className={styles.dot}></span>
          <span className={styles.dot}></span>
        </span>
        {/* Hidden from screen readers while sending: that phase is too short to announce */}
        <span aria-hidden={isSending}>{label}</span>
      </div>
    </div>
  );
};

export default TypingIndicator;