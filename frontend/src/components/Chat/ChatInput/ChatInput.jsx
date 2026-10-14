import { useLayoutEffect, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import {
  addMessage,
  setStatus,
  receiveReply,
  finishRequest,
  selectIsFirstMessage,
  selectIsWaiting,
  selectChatKey,
} from "../../../store/chatSlice";
import { ALLOWED_EXTENSIONS, MAX_MESSAGE_LENGTH } from "../../../config/constants";
import { validateFile } from "../../../utils/validateFile";
import { formatFileSize } from "../../../utils/formatFileSize";
import { formatDateRange } from "../../../utils/dateUtils";
import { getMissingItems, joinWithAnd } from "../../../utils/sendRules";
import { createId } from "../../../utils/createId";
import { askMockAgent } from "../../../services/mockAgent";
import AttachmentChip from "../../UI/AttachmentChip/AttachmentChip";
import PlusMenu from "../PlusMenu/PlusMenu";
import DatePickerModal from "../DatePickerModal/DatePickerModal";
import styles from "./ChatInput.module.css";

const ChatInput = () => {
  // L1 => States & Global Data
  const dispatch = useDispatch();
  const isFirstMessage = useSelector(selectIsFirstMessage);
  const isWaiting = useSelector(selectIsWaiting);
  const chatKey = useSelector(selectChatKey); // never changes while this chat is on screen
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [fileError, setFileError] = useState("");
  const [date, setDate] = useState(null); // { from: "YYYY-MM-DD", to: "YYYY-MM-DD" }
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const isNearLimit = text.length >= MAX_MESSAGE_LENGTH * 0.9;
  // Derived values (never stored in state)
  const missing = getMissingItems({ text, file, date, isFirstMessage });
  const canSend = missing.length === 0 && !isWaiting;
  const hint =
    isFirstMessage && missing.length > 0
      ? `Add ${joinWithAnd(missing)} to send.`
      : "";

  // L2 => Effects
  // Grow the field with its content (also shrinks it after clearing)
  useLayoutEffect(() => {
    const el = textareaRef.current;
    el.style.height = "auto";
    const border = el.offsetHeight - el.clientHeight;
    el.style.height = `${el.scrollHeight + border}px`;
  }, [text]);

  // L3 => Handlers
  const handleChange = (e) => {
    setText(e.target.value);
  };

  const handleSend = async () => {
    if (!canSend) return;

    // Plain data only: the File object itself never goes into Redux
    const sentFile = file ? { name: file.name, size: file.size } : null;
    const sentDate = date;

    dispatch(
      addMessage({
        id: createId(),
        role: "user",
        text: text.trim(),
        createdAt: Date.now(),
        file: sentFile,
        date: sentDate,
      }),
    );
    dispatch(setStatus("waiting"));

    // Attachments belong to the message that carried them
    setText("");
    setFile(null);
    setFileError("");
    setDate(null);

        try {
      // TEMPORARY: replaced by the real API call in Sprint 2
      const reply = await askMockAgent({ file: sentFile, date: sentDate });
      dispatch(
        receiveReply({
          chatKey, // ignored if the user started a new chat meanwhile
          message: {
            id: createId(),
            role: "agent",
            text: reply,
            createdAt: Date.now(),
          },
        }),
      );
    } finally {
      dispatch(finishRequest(chatKey)); // never leave the input locked
    }
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
      setFileError(error);
      return;
    }
    setFileError("");
    setFile(selected);
  };

  const handleRemoveFile = () => {
    setFile(null);
    setFileError("");
  };

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

      {fileError && (
        <div
          className="alert alert-danger small d-flex align-items-start justify-content-between gap-2 py-2 px-3 mb-2"
          role="alert"
        >
          <span>{fileError}</span>
          <button
            type="button"
            className="btn-close flex-shrink-0"
            aria-label="Dismiss error"
            onClick={() => setFileError("")}
          ></button>
        </div>
      )}

      {(file || date) && (
        <div className="d-flex flex-wrap gap-2 mb-2">
          {file && (
            <AttachmentChip
              icon="fa-solid fa-file"
              label={file.name}
              detail={formatFileSize(file.size)}
              removeLabel={`Remove ${file.name}`}
              onRemove={handleRemoveFile}
            />
          )}
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
        <PlusMenu onAttachFile={handleAttachFile} disabled={isWaiting} />
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
        <button
          type="button"
          className={styles.sendBtn}
          disabled={!canSend}
          onClick={handleSend}
          aria-label="Send message"
          aria-describedby="send-hint"
        >
          <i className="fa-solid fa-paper-plane"></i>
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
    </div>
  );
};

export default ChatInput;