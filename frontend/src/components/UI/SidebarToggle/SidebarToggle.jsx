import { SIDEBAR_ID } from "../../../config/constants";
import styles from "./SidebarToggle.module.css";

const SidebarToggle = ({ isOpen, onToggle, ref }) => {
  // L1 => States & Global Data
  // L2 => Effects
  // L3 => Handlers
  // L4 => JSX
  return (
    <button
      ref={ref}
      type="button"
      className={`${styles.toggle} ${isOpen ? styles.toggleOpen : ""}`}
      onClick={onToggle}
      aria-expanded={isOpen}
      aria-controls={SIDEBAR_ID}
      aria-label={isOpen ? "Close sidebar" : "Open sidebar"}
    >
      <i
        className={`fa-solid ${isOpen ? "fa-chevron-left" : "fa-chevron-right"}`}
      ></i>
    </button>
  );
};

export default SidebarToggle;