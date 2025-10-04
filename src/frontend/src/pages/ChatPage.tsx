import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Body1,
  Body1Strong,
  Caption1,
  Card,
  CardHeader,
  CardPreview,
  Divider,
  Spinner,
  Tag,
  Tooltip,
  Button,
} from "@fluentui/react-components";
import { ChatBubblesQuestion24Regular } from "@fluentui/react-icons";
import CoralShellColumn from "@/coral/components/Layout/CoralShellColumn";
import CoralShellRow from "@/coral/components/Layout/CoralShellRow";
import Content from "@/coral/components/Content/Content";
import ContentToolbar from "@/coral/components/Content/ContentToolbar";
import ChatInput from "@/coral/modules/ChatInput";
import PlanPanelLeft from "@/components/content/PlanPanelLeft";
import { ChatMessageModel } from "@/models";
import { ChatService, TaskService } from "@/services";
import { NewTaskService } from "@/services/NewTaskService";
import "@/styles/ChatPage.css";
import InlineToaster, { useInlineToaster } from "@/components/toast/InlineToaster";

const ChatPage: React.FC = () => {
  const [sessionId, setSessionId] = useState<string>("");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessageModel[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { showToast } = useInlineToaster();
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setSessionId(TaskService.generateSessionId());
  }, []);

  useEffect(() => {
    if (!messagesEndRef.current) return;
    messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleNewTaskButton = useCallback(() => {
    NewTaskService.handleNewTaskFromHome();
  }, []);

  const addMessage = useCallback((message: ChatMessageModel) => {
    setMessages((prev) => [...prev, message]);
  }, []);

  const handleSend = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed) {
      showToast("Please enter a question before submitting.", "error");
      return;
    }

    const userMessage: ChatMessageModel = {
      id: `user-${Date.now()}`,
      role: "user",
      text: trimmed,
      timestamp: new Date().toISOString(),
    };

    addMessage(userMessage);
    setInput("");
    setIsSubmitting(true);

    try {
      const answer = await ChatService.sendQuestion(sessionId, trimmed);
      const assistantMessage: ChatMessageModel = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        answer,
        timestamp: new Date().toISOString(),
      };
      addMessage(assistantMessage);
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Unable to retrieve chat response.";
      addMessage({
        id: `error-${Date.now()}`,
        role: "assistant",
        error: errorMessage,
        timestamp: new Date().toISOString(),
      });
      showToast(errorMessage, "error");
    } finally {
      setIsSubmitting(false);
    }
  }, [addMessage, input, sessionId, showToast]);

  const renderAssistantMessage = useCallback((message: ChatMessageModel) => {
    if (message.error) {
      return <Body1>{message.error}</Body1>;
    }

    const answer = message.answer;
    if (!answer) return null;

    return (
      <div className="chat-assistant-response">
        <Body1Strong className="chat-assistant-intent">
          Intent: {answer.intent.replace(/_/g, " ")}
        </Body1Strong>
        <Caption1 className="chat-assistant-meta">
          Session: {answer.session_id}
          {answer.run_id ? ` · Run: ${answer.run_id}` : ""}
        </Caption1>
        <Divider appearance="subtle" />
        <div className="chat-assistant-section">
          <Body1Strong>Results</Body1Strong>
          {answer.results.length === 0 ? (
            <Caption1>No matching records.</Caption1>
          ) : (
            answer.results.map((result, index) => (
              <Card key={index} className="chat-result-card">
                <CardHeader
                  header={<Body1Strong>Result {index + 1}</Body1Strong>}
                  description={answer.question}
                />
                <CardPreview>
                  <pre className="chat-result-json">
                    {JSON.stringify(result, null, 2)}
                  </pre>
                </CardPreview>
              </Card>
            ))
          )}
        </div>
        <Divider appearance="subtle" />
        <div className="chat-assistant-section">
          <Body1Strong>Citations</Body1Strong>
          {answer.citations.length === 0 ? (
            <Caption1>No citations returned.</Caption1>
          ) : (
            <ul className="chat-citation-list">
              {answer.citations.map((citation, idx) => (
                <li key={`${citation.type}-${citation.id}-${idx}`}>
                  <Caption1>
                    {citation.type}: {citation.id}
                    {citation.url ? (
                      <>
                        {" "}
                        <a href={citation.url} target="_blank" rel="noreferrer">
                          View
                        </a>
                      </>
                    ) : null}
                  </Caption1>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    );
  }, []);

  const renderMessage = useCallback(
    (message: ChatMessageModel) => {
      const isUser = message.role === "user";
      return (
        <div
          key={message.id}
          className={`chat-message ${isUser ? "chat-message--user" : "chat-message--assistant"}`}
        >
          <div className="chat-message__header">
            <Tag appearance={isUser ? "brand" : "outline"}>
              {isUser ? "You" : "Risk Assistant"}
            </Tag>
            <Caption1>{new Date(message.timestamp).toLocaleTimeString()}</Caption1>
          </div>
          <div className="chat-message__body">
            {isUser ? <Body1>{message.text}</Body1> : renderAssistantMessage(message)}
          </div>
        </div>
      );
    },
    [renderAssistantMessage]
  );

  const isInputDisabled = useMemo(() => isSubmitting, [isSubmitting]);

  return (
    <>
      <CoralShellColumn>
        <CoralShellRow>
          <PlanPanelLeft onNewTaskButton={handleNewTaskButton} />
          <Content>
            <ContentToolbar
              panelTitle="Risk Chat Assistant"
              panelIcon={<ChatBubblesQuestion24Regular />}
            >
              <Tooltip content="Start a fresh session" relationship="label">
                <Button
                  appearance="subtle"
                  onClick={() => {
                  setMessages([]);
                  setSessionId(TaskService.generateSessionId());
                  showToast("Started a new chat session.", "success");
                }}
                disabled={isSubmitting}
              >
                  New session
                </Button>
              </Tooltip>
            </ContentToolbar>

            <div className="chat-page-container">
              <div className="chat-messages-scroll">
                {messages.length === 0 ? (
                  <div className="chat-empty-state">
                    <Body1Strong>Ask about your vulnerability posture</Body1Strong>
                    <Caption1>
                      Try prompts like "Show KEV exposures for Production" or "Give me an executive summary of open risk".
                    </Caption1>
                  </div>
                ) : (
                  messages.map(renderMessage)
                )}
                {isSubmitting && (
                  <div className="chat-message chat-message--assistant">
                    <Spinner label="Processing" />
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              <div className="chat-input-area">
                <ChatInput
                  value={input}
                  onChange={setInput}
                  onEnter={handleSend}
                  disabledChat={isInputDisabled}
                  placeholder="Ask about vulnerabilities, waivers, KEV exposure, and more..."
                >
                  <Button
                    appearance="transparent"
                    onClick={handleSend}
                    disabled={isInputDisabled}
                  >
                    Send
                  </Button>
                </ChatInput>
              </div>
            </div>
          </Content>
        </CoralShellRow>
      </CoralShellColumn>
      <InlineToaster />
    </>
  );
};

export default ChatPage;
