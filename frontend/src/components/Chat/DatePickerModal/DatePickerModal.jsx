import { useEffect, useRef, useState } from "react";
import { ALLOW_FUTURE_DATES, DATE_MODAL_ID } from "../../../config/constants";
import { getTodayISO, validateDateSelection } from "../../../utils/dateUtils";
import styles from "./DatePickerModal.module.css";

const DatePickerModal = ({ value, onConfirm }) => {
  // L1 => States & Global Data
  const modalRef = useRef(null);
  const [mode, setMode] = useState("single"); // "single" | "range"
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [touched, setTouched] = useState(false);
  const maxDate = ALLOW_FUTURE_DATES ? undefined : getTodayISO();
  const error = validateDateSelection({ mode, from, to });

  // L2 => Effects
  // Each time the modal opens, start from the confirmed date (or empty)
  useEffect(() => {
    const el = modalRef.current;
    const handleShow = () => {
      setMode(value && value.from !== value.to ? "range" : "single");
      setFrom(value ? value.from : "");
      setTo(value ? value.to : "");
      setTouched(false);
    };
    el.addEventListener("show.bs.modal", handleShow);
    return () => el.removeEventListener("show.bs.modal", handleShow);
  }, [value]);

  // L3 => Handlers
  const handleModeChange = (e) => {
    setMode(e.target.value);
  };

  const handleFromChange = (e) => {
    setFrom(e.target.value);
    setTouched(true);
  };

  const handleToChange = (e) => {
    setTo(e.target.value);
    setTouched(true);
  };

  const handleConfirm = () => {
    onConfirm({ from, to: mode === "range" ? to : from });
  };

  // L4 => JSX
  return (
    <div
      ref={modalRef}
      className="modal fade"
      id={DATE_MODAL_ID}
      tabIndex="-1"
      aria-labelledby={`${DATE_MODAL_ID}-title`}
      aria-hidden="true"
    >
      <div className="modal-dialog modal-dialog-centered">
        <div className="modal-content">
          <div className="modal-header">
            <h2
              className={`${styles.title} modal-title fs-5`}
              id={`${DATE_MODAL_ID}-title`}
            >
              Choose date
            </h2>
            <button
              type="button"
              className="btn-close"
              data-bs-dismiss="modal"
              aria-label="Close"
            ></button>
          </div>

          <div className="modal-body">
            <fieldset className="mb-3">
              <legend className="fs-6 fw-semibold">Search for</legend>
              <div className="form-check form-check-inline">
                <input
                  className="form-check-input"
                  type="radio"
                  name="date-mode"
                  id="date-mode-single"
                  value="single"
                  checked={mode === "single"}
                  onChange={handleModeChange}
                />
                <label className="form-check-label" htmlFor="date-mode-single">
                  A single day
                </label>
              </div>
              <div className="form-check form-check-inline">
                <input
                  className="form-check-input"
                  type="radio"
                  name="date-mode"
                  id="date-mode-range"
                  value="range"
                  checked={mode === "range"}
                  onChange={handleModeChange}
                />
                <label className="form-check-label" htmlFor="date-mode-range">
                  A date range
                </label>
              </div>
            </fieldset>

            <div className="row g-3">
              <div className={mode === "range" ? "col-6" : "col-12"}>
                <label htmlFor="date-from" className="form-label">
                  {mode === "range" ? "From" : "Date"}
                </label>
                <input
                  id="date-from"
                  type="date"
                  className={`form-control ${styles.dateInput}`}
                  value={from}
                  max={maxDate}
                  onChange={handleFromChange}
                />
              </div>
              {mode === "range" && (
                <div className="col-6">
                  <label htmlFor="date-to" className="form-label">
                    To
                  </label>
                  <input
                    id="date-to"
                    type="date"
                    className={`form-control ${styles.dateInput}`}
                    value={to}
                    min={from || undefined}
                    max={maxDate}
                    onChange={handleToChange}
                  />
                </div>
              )}
            </div>

            {touched && error && (
              <p className="text-danger small mt-3 mb-0" role="alert">
                {error}
              </p>
            )}
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
              disabled={Boolean(error)}
              onClick={handleConfirm}
            >
              Confirm
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DatePickerModal;