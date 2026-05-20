export type TelegramIntegrationStatus = {
  is_enabled: boolean;
  bot_token_configured: boolean;
  webhook_secret_configured: boolean;
  webhook_url: string | null;
  bot_username: string | null;
  webhook_last_set_at: string | null;
};

export type TelegramSettingsUpdate = {
  is_enabled?: boolean | null;
  bot_token?: string | null;
  webhook_secret?: string | null;
  webhook_url?: string | null;
  bot_username?: string | null;
};

export type TelegramBinding = {
  id: string;
  department_id: string;
  default_task_project_id: string | null;
  chat_id: number;
  message_thread_id: number | null;
  chat_title: string | null;
  is_active: boolean;
  bot_status: string | null;
  bind_code: string | null;
  bind_code_expires_at: string | null;
  bound_at: string | null;
  disabled_at: string | null;
  created_at: string;
};

export type BindCodeCreateRequest = {
  department_id: string;
  default_task_project_id?: string | null;
};

export type TelegramIdentity = {
  id: string;
  telegram_username: string | null;
  display_name: string | null;
  is_active: boolean;
  linked_at: string | null;
  revoked_at: string | null;
};

export type LinkCodeResponse = {
  link_code: string;
  expires_at: string;
};
