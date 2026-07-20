import { requestJson } from "@/services/http/client";

export type SupportTicketCategory = "general" | "bug" | "migration_error";

export interface SupportTicketRequest {
  name: string;
  email: string;
  subject: string;
  message: string;
  category: SupportTicketCategory;
  job_id?: string | null;
}

export interface SupportTicketResponse {
  ticket_id: string;
  created_at: string;
  status: string;
  email_sent: boolean;
}

export async function submitSupportTicket(payload: SupportTicketRequest): Promise<SupportTicketResponse> {
  return requestJson<SupportTicketResponse>("/v1/support/tickets", "Failed to submit support ticket", {
    method: "POST",
    body: payload,
  });
}
