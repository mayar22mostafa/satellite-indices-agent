import styles from "./ChatHeader.module.css";

const ChatHeader = ({ title = "EgSA Agent" }) => {
  // L1 => States & Global Data
  // L2 => Effects
  // L3 => Handlers
  // L4 => JSX
  return (
    <header
      className={`${styles.header} d-flex align-items-center gap-2 shadow-sm`}
    >
      <div className={styles.avatar}>
        <i className="fa-solid fa-robot"></i>
      </div>
      <h1 className="h6 mb-0 fw-semibold">{title}</h1>
    </header>
  );
};

export default ChatHeader;