import { useState, useEffect, useRef } from "react";
import { useDispatch, useSelector } from "react-redux";
import {
  setApprovingPlan,
  markPlanApproved,
  appendAnalysisResult,
  selectApprovingPlanId,
  selectChatKey,
} from "../../../store/chatSlice";
import {
  approvePlan,
  watchPlan,
  buildAnalysisMessage,
  getErrorMessage,
} from "../../../services/api";
import { getIndexConfig } from "../../../config/indices";
import styles from "./PlanCard.module.css";

const PlanCard = ({ message, isLatest }) => {
  const dispatch = useDispatch();
  const chatKey = useSelector(selectChatKey);
  const approvingPlanId = useSelector(selectApprovingPlanId);

  // Only the plan_id issued by the agent is valid for /approve (it is not the session id
  // and not the local message id). null means the agent did not provide one.
  // It is used internally only and is never shown to the user.
  const planId = message.plan_id || null;
  const plan = message.plan || {};
  const isApproved = Boolean(message.approved);
  const isCurrentlyApproving = approvingPlanId === planId;

  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [errorMessage, setErrorMessage] = useState("");
  const [progressText, setProgressText] = useState("");
  const abortRef = useRef(null); // the approve request
  const streamRef = useRef(null); // the SSE stream that follows the analysis

  // Locking rule: Active ONLY while it is the latest message and not yet approved
  const isLocked = !isLatest || isApproved;

  // Stop following the analysis when this card goes away (e.g. New Chat)
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      streamRef.current?.close();
    };
  }, []);

  // Elapsed-time counter while the analysis is running
  useEffect(() => {
    if (!isCurrentlyApproving) return;

    const startTime = Date.now();
    const timer = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);

    return () => clearInterval(timer);
  }, [isCurrentlyApproving]);

  const handleApprove = async () => {
    if (isLocked || isCurrentlyApproving || !planId) return;

    setErrorMessage("");
    setElapsedSeconds(0);
    setProgressText("Sending approval to the agent…");
    dispatch(setApprovingPlan(planId));

    const controller = new AbortController();
    abortRef.current = controller;

    // Final states: show the result (or the failure) in the chat and unlock the input
    const showFinal = (analysisMessage) => {
      streamRef.current = null;
      dispatch(appendAnalysisResult({ chatKey, planId, analysisMessage }));
    };

    try {
      // The backend answers 202 right away; the analysis keeps running on the server
      await approvePlan({ planId, signal: controller.signal });
      dispatch(markPlanApproved(planId));
      setProgressText("Analysis is running…");

      streamRef.current = watchPlan(planId, {
        onProgress: (update) => {
          setProgressText(
            update.message || `Analysis status: ${update.status ?? "Running"}…`,
          );
        },
        onDone: (update) => showFinal(buildAnalysisMessage(update.result)),
        onFailed: ({ message: reason }) =>
          showFinal({
            id: `${planId}-failed`,
            role: "agent",
            type: "text",
            createdAt: Date.now(),
            text: `The analysis failed: ${reason}`,
          }),
      });
    } catch (err) {
      setErrorMessage(getErrorMessage(err));
      dispatch(setApprovingPlan(null));
    } finally {
      abortRef.current = null;
    }
  };

  const handleChange = () => {
    // Focus chat input so user can type modification requests
    window.dispatchEvent(new CustomEvent("focus-chat-input"));
  };

  // Indices formatting
  const rawIndices = plan.indices || (plan.index ? [plan.index] : ["NDVI"]);
  const indicesList = Array.isArray(rawIndices) ? rawIndices : [rawIndices];

  // Dates formatting
  // Same start and end date = the user picked a single day, so show one date.
  // A real range still shows "start to end".
  const dateDisplay =
    plan.start_date && plan.end_date
      ? plan.start_date === plan.end_date
        ? plan.start_date
        : `${plan.start_date} to ${plan.end_date}`
      : plan.image_date || plan.date || "Latest clear date";
  // Assumptions
  const assumptions = Array.isArray(plan.assumptions)
    ? plan.assumptions
    : [
      "Used Sentinel-2 Level-2A imagery",
      `Cloud cover under ${plan.max_cloud ?? 20}%`,
    ];

  const cloudMask = plan.cloud_mask !== false;

  return (
    <div
      className={styles.planCard}
      role="region"
      aria-label="Satellite Analysis Plan"
    >
      <div className={styles.header}>
        <div className={styles.titleArea}>
          <div className={styles.iconBadge} aria-hidden="true">
            <i className="fa-solid fa-satellite"></i>
          </div>
          <div>
            <h3 className={styles.title}>Proposed Analysis Plan</h3>
          </div>
        </div>

        {isApproved ? (
          <span className={styles.statusBadge}>
            <i className="fa-solid fa-circle-check"></i> Approved & Run
          </span>
        ) : isLocked ? (
          <span className={styles.lockedBadge}>
            <i className="fa-solid fa-lock"></i> Inactive
          </span>
        ) : (
          <span className={styles.statusBadge} style={{ background: "rgba(56, 189, 248, 0.15)", color: "#38bdf8", borderColor: "rgba(56, 189, 248, 0.3)" }}>
            <i className="fa-solid fa-clock"></i> Ready for Approval
          </span>
        )}
      </div>

      {message.text && <p className={styles.description}>{message.text}</p>}

      <div className={styles.grid}>
        <div className={styles.infoItem}>
          <span className={styles.infoLabel}>
            <i className="fa-solid fa-layer-group"></i> Target Indices
          </span>
          <div className={styles.chipsList}>
            {indicesList.map((idx) => {
              const cfg = getIndexConfig(idx);
              return (
                <span key={idx} className={styles.indexChip}>
                  <i className="fa-solid fa-chart-line"></i>
                  {cfg.label}
                </span>
              );
            })}
          </div>
        </div>

        <div className={styles.infoItem}>
          <span className={styles.infoLabel}>
            <i className="fa-solid fa-calendar-range"></i> Imagery Period
          </span>
          <div className={styles.infoValue}>{dateDisplay}</div>
        </div>

        <div className={styles.infoItem}>
          <span className={styles.infoLabel}>
            <i className="fa-solid fa-cloud"></i> Max Cloud Cover
          </span>
          <div className={styles.infoValue}>{plan.max_cloud ?? 20}%</div>
        </div>

        <div className={styles.infoItem}>
          <span className={styles.infoLabel}>
            <i className="fa-solid fa-shield-halved"></i> Cloud Filtering
          </span>
          <div className={styles.infoValue}>
            {cloudMask ? "Applied (Clear Sky Only)" : "Off"}
          </div>
        </div>
      </div>

      {assumptions.length > 0 && (
        <div className={styles.assumptionsBox}>
          <span className={styles.assumptionsTitle}>
            <i className="fa-solid fa-circle-info"></i> Execution Assumptions
          </span>
          <ul className={styles.assumptionsList}>
            {assumptions.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {!planId && !isApproved && (
        <div className="alert alert-warning small py-2 px-3 mb-3" role="alert">
          <i className="fa-solid fa-triangle-exclamation me-2"></i>
          This plan can't be approved right now. Please rephrase your request.
        </div>
      )}

      {errorMessage && (
        <div className="alert alert-danger small py-2 px-3 mb-3" role="alert">
          <i className="fa-solid fa-triangle-exclamation me-2"></i>
          {errorMessage}
        </div>
      )}

      {isCurrentlyApproving && (
        <div className={styles.loadingProgress} role="status" aria-live="polite">
          <div className={styles.progressBar}>
            {/* Duration is unknown, so the bar is a full "working" indicator, not a percentage */}
            <div className={styles.progressFill} style={{ width: "100%" }}></div>
          </div>
          <div className={styles.loadingText}>
            <span>
              <i className="fa-solid fa-circle-notch fa-spin me-2"></i>
              {progressText || "Analysis is running…"}
            </span>
            <span>{elapsedSeconds}s</span>
          </div>
        </div>
      )}

      <div className={styles.actions}>
        <button
          type="button"
          className={styles.runBtn}
          disabled={isLocked || isCurrentlyApproving || !planId}
          onClick={handleApprove}
          aria-label={
            isApproved
              ? "Plan already approved"
              : isCurrentlyApproving
                ? "Running analysis in Earth Engine"
                : "Approve and run plan"
          }
        >
          {isCurrentlyApproving ? (
            <>
              <i className="fa-solid fa-circle-notch fa-spin"></i>
              Running Analysis…
            </>
          ) : isApproved ? (
            <>
              <i className="fa-solid fa-check"></i>
              Approved
            </>
          ) : (
            <>
              <i className="fa-solid fa-play"></i>
              Yes, run it
            </>
          )}
        </button>

        <button
          type="button"
          className={styles.changeBtn}
          disabled={isLocked || isCurrentlyApproving}
          onClick={handleChange}
          aria-label="Change plan parameters"
        >
          <i className="fa-solid fa-pen"></i>
          Change
        </button>
      </div>
    </div>
  );
};

export default PlanCard;