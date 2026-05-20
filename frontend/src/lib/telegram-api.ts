import { ApiError, api } from "@/lib/api";
import type {
  BindCodeCreateRequest,
  LinkCodeResponse,
  TelegramBinding,
  TelegramIdentity,
  TelegramIntegrationStatus,
  TelegramSettingsUpdate,
} from "@/lib/telegram-types";

export async function getTelegramSettings(): Promise<TelegramIntegrationStatus> {
  return api<TelegramIntegrationStatus>("/api/admin/telegram/settings");
}

export async function updateTelegramSettings(
  body: TelegramSettingsUpdate,
): Promise<TelegramIntegrationStatus> {
  return api<TelegramIntegrationStatus>("/api/admin/telegram/settings", {
    method: "PUT",
    body,
  });
}

export async function listTelegramBindings(departmentId: string): Promise<TelegramBinding[]> {
  return api<TelegramBinding[]>(
    `/api/telegram/bindings?department_id=${encodeURIComponent(departmentId)}`,
  );
}

export async function createTelegramBindCode(
  body: BindCodeCreateRequest,
): Promise<TelegramBinding> {
  return api<TelegramBinding>("/api/telegram/bindings", {
    method: "POST",
    body,
  });
}

export async function disableTelegramBinding(bindingId: string): Promise<TelegramBinding> {
  return api<TelegramBinding>(`/api/telegram/bindings/${encodeURIComponent(bindingId)}`, {
    method: "DELETE",
  });
}

export async function generateTelegramLinkCode(): Promise<LinkCodeResponse> {
  return api<LinkCodeResponse>("/api/telegram/identities/link-codes", {
    method: "POST",
  });
}

export async function getMyTelegramIdentity(): Promise<TelegramIdentity | null> {
  try {
    return await api<TelegramIdentity>("/api/telegram/identities/me");
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export async function revokeMyTelegramIdentity(): Promise<void> {
  await api<void>("/api/telegram/identities/me", { method: "DELETE" });
}
