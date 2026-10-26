import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import {
  addMessage,
  setStatus,
  receiveReply,
  removeMessage,
  expireConversation,
  updateRequestProgress,
  finishRequest,
  selectNeedsAttachments,
  selectConversationId,
  selectIsWaiting,
  selectChatKey,
} from "../../../store/chatSlice";
import { ALLOWED_EXTENSIONS, MAX_MESSAGE_LENGTH } from "../../../config/constants";
import { validateFile } from "../../../utils/validateFile";
import { formatFileSize } from "../../../utils/formatFileSize";
import { formatDateRange } from "../../../utils/dateUtils";
import { getMissingItems, joinWithAnd } from "../../../utils/sendRules";
import { createId } from "../../../utils/createId";
import {
  sendMessage,
  getErrorMessage,
  isConversationExpired,
  isRequestCancelled,
} from "../../../services/api";
import AttachmentChip from "../../UI/AttachmentChip/AttachmentChip";
import PlusMenu from "../PlusMenu/PlusMenu";
import DatePickerModal from "../DatePickerModal/DatePickerModal";
import MapSelectionModal from "../../Map/MapSelectionModal";
import styles from "./ChatInput.module.css";

const ChatInput = () => {
  // L1 => States & Global Data
  const dispatch = useDispatch();
  const needsAttachments = useSelector(selectNeedsAttachments);
  const conversationId = useSelector(selectConversationId);
  const isWaiting = useSelector(selectIsWaiting);
  const chatKey = useSelector(selectChatKey);
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [mapArea, setMapArea] = useState(null); // { areaKm2, geojson, coordinates }
  const [isMapModalOpen, setIsMapModalOpen] = useState(false);
  const [date, setDate] = useState(null); // { from: "YYYY-MM-DD", to: "YYYY-MM-DD" }
  const [errorMessage, setErrorMessage] = useState(""); // file problems and failed sends
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const abortRef = useRef(null); // lets the user cancel the request that is running
  const isNearLimit = text.length >= MAX_MESSAGE_LENGTH * 0.9;

  // Derived values (never stored in state)
  const missing = getMissingItems({ text, file, date, needsAttachments });
  const canSend = missing.length === 0 && !isWaiting;
  const hint =
    needsAttachments && missing.length > 0
      ? `Add ${joinWithAnd(missing)} to send.`
      : "";

  // L2 => Effects
  // Grow the field with its content (also shrinks it after clearing)
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const border = el.offsetHeight - el.clientHeight;
    el.style.height = `${el.scrollHeight + border}px`;
  }, [text]);

  // Leaving this chat (New Chat) cancels the request that is still running
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  // Listen for external focus and prefill events (e.g. PlanCard "Change" or Question quick-replies)
  useEffect(() => {
    const handleFocus = () => {
      textareaRef.current?.focus();
    };

    const handlePrefill = (e) => {
      const incoming = e.detail?.text;
      if (incoming) {
        setText((prev) => (prev.trim() ? `${prev.trim()} ${incoming}` : incoming));
      }
      textareaRef.current?.focus();
    };

    window.addEventListener("focus-chat-input", handleFocus);
    window.addEventListener("prefill-chat-input", handlePrefill);

    return () => {
      window.removeEventListener("focus-chat-input", handleFocus);
      window.removeEventListener("prefill-chat-input", handlePrefill);
    };
  }, []);

  // L3 => Handlers
  const handleChange = (e) => {
    setText(e.target.value);
  };

  const handleSend = async () => {
    if (!canSend) return;

    // The real File is needed for the upload; Redux only gets plain details
    const sentText = text.trim();
    const sentFile = file;
    const sentDate = date;
    const sentMapArea = mapArea;
    const messageId = createId();
    const controller = new AbortController();
    abortRef.current = controller;

    dispatch(
      addMessage({
        id: messageId,
        role: "user",
        type: "user",
        text: sentText,
        createdAt: Date.now(),
        file: sentFile
          ? {
              name: sentMapArea ? "Map Selection" : sentFile.name,
              size: sentFile.size,
              isMapSelection: Boolean(sentMapArea),
              areaKm2: sentMapArea?.areaKm2 || null,
            }
          : null,
        date: sentDate,
      }),
    );
    dispatch(setStatus("sending"));

    // Attachments belong to the message that carried them
    setText("");
    setFile(null);
    setMapArea(null);
    setDate(null);
    setErrorMessage("");

    try {
      const answer = await sendMessage({
        text: sentText,
        file: sentFile,
        date: sentDate,
        conversationId, // null until the agent has started the conversation
        signal: controller.signal,
        onUploadProgress: (event) => {
          const fraction =
            event.progress ?? (event.total ? event.loaded / event.total : null);
          if (fraction === null) return;
          dispatch(
            updateRequestProgress({
              chatKey,
              percent: Math.round(fraction * 100),
            }),
          );
        },
      });
      dispatch(
        receiveReply({
          chatKey, // ignored if the user started a new chat meanwhile
          conversationId: answer.conversationId,
          message: answer.message,
        }),
      );
    } catch (error) {
      // Take the message back and give the user everything to try again.
      // If the user started a new chat meanwhile, all of this has no effect.
      dispatch(removeMessage({ chatKey, id: messageId }));
      if (isConversationExpired(error)) {
        dispatch(expireConversation(chatKey));
      }
      // Whatever the user typed while waiting is kept after the restored text
      setText((current) =>
        current.trim() === ""
          ? sentText
          : `${sentText}\n\n${current}`.slice(0, MAX_MESSAGE_LENGTH),
      );
      setFile(sentFile);
      setMapArea(sentMapArea);
      setDate(sentDate);
      if (isRequestCancelled(error)) {
        // The user knows why: no alert, just let them edit the message
        textareaRef.current?.focus();
      } else {
        setErrorMessage(`Message not sent. ${getErrorMessage(error)}`);
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      dispatch(finishRequest(chatKey)); // never leave the input locked
    }
  };

  const handleCancel = () => {
    abortRef.current?.abort();
  };

  const handleAttachFile = () => {
    fileInputRef.current.click();
  };

  const handleFileChange = (e) => {
    const selected = e.target.files[0];
    e.target.value = ""; // allow choosing the same file again
    if (!selected) return;

    const error = validateFile(selected);
    if (error) {
      setErrorMessage(error);
      return;
    }
    setErrorMessage("");
    setFile(selected);
    setMapArea(null);
  };

  const handleRemoveFile = () => {
    setFile(null);
    setMapArea(null);
    setErrorMessage("");
  };

  // Map Selection handlers
  const handleConfirmMapSelection = ({ file: drawnFile, areaKm2, geojson, coordinates }) => {
    setFile(drawnFile);
    setMapArea({ areaKm2, geojson, coordinates });
    setErrorMessage("");
  };

  const handleRemoveMapArea = () => {
    setFile(null);
    setMapArea(null);
  };

  // Restores date to dedicated panel above text field
  const handleConfirmDate = (selected) => {
    setDate(selected);
  };

  const handleRemoveDate = () => {
    setDate(null);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault(); // stop the new line
      handleSend();
    }
  };

  // L4 => JSX
  return (
    <div className={styles.inputBar}>
      <input
        ref={fileInputRef}
        type="file"
        className="d-none"
        accept={ALLOWED_EXTENSIONS.join(",")}
        onChange={handleFileChange}
      />

      {errorMessage && (
        <div
          className="alert alert-danger small d-flex align-items-start justify-content-between gap-2 py-2 px-3 mb-2"
          role="alert"
        >
          <span>{errorMessage}</span>
          <button
            type="button"
            className="btn-close flex-shrink-0"
            aria-label="Dismiss error"
            onClick={() => setErrorMessage("")}
          ></button>
        </div>
      )}

      {/* Attachments panel positioned above the text field */}
      {(file || date) && (
        <div className="d-flex flex-wrap gap-2 mb-2">
          {file && mapArea ? (
            <AttachmentChip
              icon="fa-solid fa-draw-polygon"
              label="Map Selection"
              detail={`${mapArea.areaKm2} km²`}
              removeLabel="Remove map selection"
              onRemove={handleRemoveMapArea}
            />
          ) : file ? (
            <AttachmentChip
              icon="fa-solid fa-file"
              label={file.name}
              detail={formatFileSize(file.size)}
              removeLabel={`Remove ${file.name}`}
              onRemove={handleRemoveFile}
            />
          ) : null}
          {date && (
            <AttachmentChip
              icon="fa-solid fa-calendar-days"
              label={formatDateRange(date)}
              removeLabel="Remove date"
              onRemove={handleRemoveDate}
            />
          )}
        </div>
      )}

      <div className="d-flex align-items-end gap-2">
        <PlusMenu
          onAttachFile={handleAttachFile}
          onSelectOnMap={() => setIsMapModalOpen(true)}
          disabled={isWaiting}
        />
        <textarea
          ref={textareaRef}
          className={`form-control ${styles.textField}`}
          rows="1"
          dir="auto"
          maxLength={MAX_MESSAGE_LENGTH}
          placeholder="Type what you are looking for..."
          aria-label="Message"
          aria-describedby="char-counter"
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
        />
        {/* One button, so the keyboard focus stays on it: Send, or Cancel while waiting */}
        <button
          type="button"
          className={`${styles.sendBtn} ${isWaiting ? styles.stopBtn : ""}`}
          disabled={!isWaiting && !canSend}
          onClick={isWaiting ? handleCancel : handleSend}
          aria-label={isWaiting ? "Cancel request" : "Send message"}
          aria-describedby="send-hint"
        >
          <i className={`fa-solid ${isWaiting ? "fa-stop" : "fa-paper-plane"}`}></i>
        </button>
      </div>

      <div className={styles.footerRow}>
        <span id="send-hint" className={styles.hint}>
          {hint}
        </span>
        <span
          id="char-counter"
          className={`${styles.counter} ${isNearLimit ? styles.counterWarn : ""}`}
        >
          {text.length} / {MAX_MESSAGE_LENGTH}
        </span>
      </div>

      <DatePickerModal value={date} onConfirm={handleConfirmDate} />

      {isMapModalOpen && (
        <MapSelectionModal
          isOpen={isMapModalOpen}
          onClose={() => setIsMapModalOpen(false)}
          onConfirm={handleConfirmMapSelection}
          initialCoordinates={mapArea?.coordinates}
        />
      )}
    </div>
  );
};

export default ChatInput;