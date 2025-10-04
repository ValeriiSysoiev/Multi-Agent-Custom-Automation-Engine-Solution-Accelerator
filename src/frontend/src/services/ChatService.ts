import { apiClient } from "@/api/apiClient";
import { ChatAnswerModel } from "@/models";

class ChatService {
  static async sendQuestion(
    sessionId: string,
    question: string,
    limit: number = 20
  ): Promise<ChatAnswerModel> {
    const payload = {
      session_id: sessionId,
      question,
      limit,
    };

    const response = await apiClient.post("/chat", payload);
    return response as ChatAnswerModel;
  }
}

export default ChatService;
