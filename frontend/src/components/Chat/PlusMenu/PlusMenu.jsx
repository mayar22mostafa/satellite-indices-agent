import { DATE_MODAL_ID } from "../../../config/constants";
import styles from "./PlusMenu.module.css";

const PlusMenu = ({ onAttachFile , disabled}) => {
  // L1 => States & Global Data
  // L2 => Effects
  // L3 => Handlers
  // L4 => JSX
  return (
    <div className="dropup flex-shrink-0">
      <button
        type="button"
        className={styles.plusBtn}
        data-bs-toggle="dropdown"
        aria-expanded="false"
        aria-label="Add file or date"
        disabled={disabled}
      >
        <i className="fa-solid fa-plus"></i>
      </button>

      <ul className={`dropdown-menu ${styles.menu}`}>
        <li>
          <button
            type="button"
            className={`dropdown-item d-flex align-items-center gap-2 ${styles.menuItem}`}
            onClick={onAttachFile}
          >
            <i className={`fa-solid fa-paperclip ${styles.menuIcon}`}></i>
            Attach file
          </button>
        </li>
        <li>
          <button
            type="button"
            className={`dropdown-item d-flex align-items-center gap-2 ${styles.menuItem}`}
            data-bs-toggle="modal"
            data-bs-target={`#${DATE_MODAL_ID}`}
          >
            <i className={`fa-solid fa-calendar-days ${styles.menuIcon}`}></i>
            Choose date
          </button>
        </li>
      </ul>
    </div>
  );
};

export default PlusMenu;