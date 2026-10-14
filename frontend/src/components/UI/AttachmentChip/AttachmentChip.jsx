import styles from "./AttachmentChip.module.css";

const AttachmentChip = ({ icon, label, detail, removeLabel, onRemove }) => {
  // L1 => States & Global Data
  // L2 => Effects
  // L3 => Handlers
  // L4 => JSX
  return (
    <div className={`${styles.chip} d-inline-flex align-items-center gap-2`}>
      <i className={`${icon} ${styles.icon}`}></i>
      <span className={styles.label} title={label}>
        {label}
      </span>
      {detail && <span className={styles.detail}>{detail}</span>}
      <button
        type="button"
        className={styles.removeBtn}
        onClick={onRemove}
        aria-label={removeLabel}
      >
        <i className="fa-solid fa-xmark"></i>
      </button>
    </div>
  );
};

export default AttachmentChip;