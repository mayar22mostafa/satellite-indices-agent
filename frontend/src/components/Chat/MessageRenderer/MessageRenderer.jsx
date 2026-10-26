import MessageBubble from "../../UI/MessageBubble/MessageBubble";
import PlanCard from "../PlanCard/PlanCard";
import QuestionBubble from "../QuestionBubble/QuestionBubble";
import AnalysisCard from "../AnalysisCard/AnalysisCard";
import styles from "./MessageRenderer.module.css";

const MessageRenderer = ({ message, isLatest }) => {
  const isUser = message.role === "user" || message.type === "user";

  if (isUser) {
    return (
      <div className={`${styles.messageWrapper} ${styles.userWrapper}`}>
        <MessageBubble
          role="user"
          text={message.text}
          createdAt={message.createdAt}
          file={message.file}
          date={message.date}
        />
      </div>
    );
  }

  // Polymorphic agent message rendering
  const messageType = message.type || "text";

  let content;
  switch (messageType) {
    case "plan":
      content = <PlanCard message={message} isLatest={isLatest} />;
      break;

    case "question":
      content = <QuestionBubble message={message} />;
      break;

    case "analysis":
      content = <AnalysisCard message={message} />;
      break;

    case "text":
    default:
      content = (
        <MessageBubble
          role="agent"
          text={message.text}
          createdAt={message.createdAt}
        />
      );
      break;
  }

  return (
    <div className={`${styles.messageWrapper} ${styles.agentWrapper}`}>
      {content}
    </div>
  );
};

export default MessageRenderer;
