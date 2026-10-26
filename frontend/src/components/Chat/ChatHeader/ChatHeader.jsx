import styles from "./ChatHeader.module.css";

const ChatHeader = ({ title = "EgSA Agent" }) => {
  return (
    <header className={`${styles.header} d-flex align-items-center gap-2 shadow-sm`}>
      <div className={styles.avatar} aria-hidden="true">
        <i className="fa-solid fa-robot"></i>
      </div>
      <h1 className="h6 mb-0 fw-semibold">{title}</h1>
    </header>
  );
};

export default ChatHeader;